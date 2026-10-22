import io
import json
import os
import shutil
import time
import wave
import zipfile
from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import JobState
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.profile import build_queue_params, write_queue_archive
from beatweave.wan2gp.schemas import (
    MiniMaxH3Profile,
    MiniMaxH3PrunedPDDProfile,
    MiniMaxH3PrunedProfile,
    VideoRenderRequest,
    Wan2GPConfig,
    Wan2GPExecutionResult,
)
from beatweave.wan2gp.service import Wan2GPService


def completed_job(value):
    future = Future()
    future.set_result(value)
    return future


class ImmediateExecutor:
    def submit(self, function, *args, **kwargs):
        return completed_job(function(*args, **kwargs))


def create_project_with_scene(
    client: TestClient, tmp_path: Path, *, source_image: Path | None = None
) -> tuple[dict, str, str, str, str]:
    parent = tmp_path / "projects"
    parent.mkdir(exist_ok=True)
    project = client.post(
        "/projects", json={"name": "Wan Test", "parent_directory": str(parent)}
    ).json()
    store = ProjectStore(project["path"])
    asset_ids = []
    for index in range(2):
        path = store.directory / "keyframes" / f"boundary-{index}.png"
        if source_image is None:
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([index]))
        else:
            shutil.copy2(source_image, path)
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_image",
            relative_path=path.relative_to(store.directory).as_posix(),
            filename=path.name,
            mime_type="image/png",
            sha256=f"hash-{index}",
            size_bytes=path.stat().st_size,
            created_at=datetime.now(UTC),
        )
        store.insert_asset(asset)
        asset_ids.append(asset.id)
    audio_path = store.directory / "source" / "soundtrack.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 16_000)
    audio_asset = AssetMetadata(
        id=str(uuid4()),
        kind="audio",
        relative_path=audio_path.relative_to(store.directory).as_posix(),
        filename=audio_path.name,
        mime_type="audio/wav",
        sha256="audio-hash",
        size_bytes=audio_path.stat().st_size,
        media_metadata={"duration_seconds": 2.0},
        created_at=datetime.now(UTC),
    )
    store.insert_asset(audio_asset)
    scene_id = str(uuid4())
    start_id, end_id = str(uuid4()), str(uuid4())
    now = datetime.now(UTC).isoformat()
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [(start_id, 0, now, now), (end_id, 1, now, now)],
        )
        connection.execute(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_keyframe_id, end_keyframe_id,
                video_prompt, created_at, updated_at
            ) VALUES (?, 0, 0, 1, ?, ?, 'canonical scene prompt', ?, ?)
            """,
            (scene_id, start_id, end_id, now, now),
        )
    return project, scene_id, asset_ids[0], asset_ids[1], audio_asset.id


def render_request(scene_id: str, start_id: str, end_id: str, audio_id: str) -> dict:
    return {
        "scene_id": scene_id,
        "start_keyframe_asset_id": start_id,
        "end_keyframe_asset_id": end_id,
        "audio_asset_id": audio_id,
        "audio_start_seconds": 0,
        "prompt": "Prismatic ribbons pulse and sweep toward the final composition.",
        "duration_seconds": 1,
        "frame_rate": 24,
        "model_profile": "ltx-2.3-distilled-1.1",
        "motion": {"amplitude": 1.25, "seed": 42},
        "audio_reactive_lora": {
            "enabled": True,
            "multiplier": 0.8,
            "trigger": "follow the soundtrack rhythm",
        },
        "quality_mode": "preview",
    }


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("render job did not finish")


def test_canonical_request_maps_to_valid_wan2gp_queue_zip(tmp_path: Path) -> None:
    start = tmp_path / "start.png"
    end = tmp_path / "end.png"
    start.write_bytes(b"start")
    end.write_bytes(b"end")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    request = VideoRenderRequest.model_validate(
        render_request("scene-1", "asset-1", "asset-2", "audio-1")
    )
    config = Wan2GPConfig()
    queue_path = tmp_path / "queue.zip"

    params = write_queue_archive(request, config, start, end, audio, queue_path)

    assert params == build_queue_params(request, config)
    assert params["model_type"] == "ltx2_22B_distilled_1_1"
    assert params["image_prompt_type"] == "SE"
    assert params["audio_prompt_type"] == "A"
    assert params["audio_guide"] == "task1_audio_guide_0.wav"
    assert params["video_length"] == 25
    assert params["resolution"] == "768x448"
    assert params["activated_loras"] == ["ltx2.3_audio_reactive_lora_v2.safetensors"]
    assert params["loras_multipliers"] == "0.8"
    assert params["prompt"].startswith("follow the soundtrack rhythm")
    with zipfile.ZipFile(queue_path) as archive:
        assert set(archive.namelist()) == {
            "queue.json",
            "task1_image_start_0.png",
            "task1_image_end_0.png",
            "task1_audio_guide_0.wav",
        }
        manifest = json.loads(archive.read("queue.json"))
    assert manifest == [{"id": 1, "params": params}]
    assert "wan2gp" not in request.model_dump_json().lower()


def test_start_only_request_omits_last_frame_from_queue(tmp_path: Path) -> None:
    start = tmp_path / "start.png"
    start.write_bytes(b"start")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    body = render_request("scene-1", "asset-1", "asset-2", "audio-1")
    body["end_keyframe_asset_id"] = None
    request = VideoRenderRequest.model_validate(body)
    queue_path = tmp_path / "queue.zip"

    params = write_queue_archive(request, Wan2GPConfig(), start, None, audio, queue_path)

    assert params["image_prompt_type"] == "S"
    assert params["image_end"] is None
    with zipfile.ZipFile(queue_path) as archive:
        assert "task1_image_end_0.png" not in archive.namelist()


@pytest.mark.parametrize("profile_type", [MiniMaxH3Profile, MiniMaxH3PrunedProfile])
@pytest.mark.parametrize("last_frame", [True, False])
def test_h3_queue_uses_native_soundtrack_without_ltx_lora(
    tmp_path: Path, profile_type, last_frame: bool
) -> None:
    profile = profile_type()
    config = Wan2GPConfig(profile=profile)
    body = render_request("scene", "start", "end", "audio")
    body.update(model_profile=profile.name, duration_seconds=5)
    if not last_frame:
        body["end_keyframe_asset_id"] = None
    request = VideoRenderRequest.model_validate(body)
    start, end, audio = (tmp_path / name for name in ("start.png", "end.png", "audio.wav"))
    for path in (start, end, audio):
        path.write_bytes(b"input")
    queue = tmp_path / "queue.zip"
    params = write_queue_archive(request, config, start, end if last_frame else None, audio, queue)
    assert params["model_type"] == profile.model_type
    assert params["base_model_type"] == profile.model_type
    assert params["video_length"] == 124
    assert (params["video_length"] - 5) % 17 == 0
    assert params["image_prompt_type"] == ("SE" if last_frame else "S")
    assert params["audio_prompt_type"] == "A"
    assert params["activated_loras"] == []
    assert params["loras_multipliers"] == ""
    assert params["prompt"] == body["prompt"]
    assert "motion_amplitude" not in params
    assert params["sample_solver"] == "euler"
    assert params["flow_shift"] == 12
    assert params["num_inference_steps"] == 20
    assert params["sliding_window_size"] == 362
    with zipfile.ZipFile(queue) as archive:
        assert archive.read("task1_audio_guide_0.wav") == b"input"
        assert ("task1_image_end_0.png" in archive.namelist()) == last_frame
    final = build_queue_params(request.model_copy(update={"quality_mode": "final"}), config)
    assert final["resolution"] == "1920x1088"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"duration_seconds": 1}, "wan2gp_scene_too_short"),
        ({"frame_rate": 30}, "wan2gp_frame_rate_invalid"),
        ({"model_profile": "unknown"}, "wan2gp_profile_unknown"),
    ],
)
def test_h3_rejects_unsupported_requests(changes: dict, code: str) -> None:
    profile = MiniMaxH3Profile()
    body = render_request("scene", "start", "end", "audio")
    body.update(model_profile=profile.name, duration_seconds=5)
    body.update(changes)
    with pytest.raises(BeatweaveError) as error:
        build_queue_params(VideoRenderRequest.model_validate(body), Wan2GPConfig(profile=profile))
    assert error.value.code == code


@pytest.mark.parametrize("quality_mode", ["preview", "final"])
def test_pruned_pdd_queue_matches_provided_eight_step_profile(quality_mode: str) -> None:
    profile = MiniMaxH3PrunedPDDProfile()
    body = render_request("scene", "start", "end", "audio")
    body.update(model_profile=profile.name, duration_seconds=175 / 24, quality_mode=quality_mode)
    params = build_queue_params(
        VideoRenderRequest.model_validate(body), Wan2GPConfig(profile=profile)
    )
    expected = {
        "model_type": "minimax_h3_fl2va_pruned_pdd",
        "base_model_type": "minimax_h3_fl2va_pruned",
        "settings_version": 2.81,
        "num_inference_steps": 8,
        "sample_solver": "euler",
        "flow_shift": 12,
        "guidance_scale": 1,
        "guidance_phases": 1,
        "video_length": 175,
        "image_prompt_type": "SE",
        "audio_prompt_type": "A",
        "activated_loras": [],
    }
    assert {key: params[key] for key in expected} == expected


def test_pruned_pdd_settings_persist_independently_and_reject_invalid_sampling(
    tmp_path: Path,
) -> None:
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        config = client.get("/wan2gp/config").json()
        default_name = "minimax-h3-fl2va-pruned-20b"
        pdd_name = "minimax-h3-fl2va-pruned-20b-pdd"
        config["profile"] = config["profiles"][default_name]
        config["profile"]["preview"]["inference_steps"] = 25
        config["profile"]["sample_solver"] = "res_multistep"
        config = client.put("/wan2gp/config", json=config).json()
        config["profile"] = config["profiles"][pdd_name]
        config["profile"]["preview"]["resolution"] = "960x544"
        assert client.put("/wan2gp/config", json=config).is_success
    with TestClient(create_app(settings)) as client:
        config = client.get("/wan2gp/config").json()
        assert config["profile"]["name"] == pdd_name
        assert config["profile"]["preview"]["inference_steps"] == 8
        assert config["profile"]["preview"]["resolution"] == "960x544"
        assert config["profiles"][default_name]["preview"]["inference_steps"] == 25
        assert config["profiles"][default_name]["sample_solver"] == "res_multistep"
        invalid = json.loads(json.dumps(config))
        invalid["profile"]["preview"]["inference_steps"] = 20
        assert client.put("/wan2gp/config", json=invalid).status_code == 422
        invalid = json.loads(json.dumps(config))
        invalid["profile"]["sample_solver"] = "res_multistep"
        assert client.put("/wan2gp/config", json=invalid).status_code == 422
        assert client.get("/wan2gp/config").json() == config


def test_renderer_profiles_survive_legacy_config_and_reopen(tmp_path: Path) -> None:
    legacy = Wan2GPConfig().model_dump(mode="json")
    legacy.pop("profiles")
    legacy["profile"]["preview"]["inference_steps"] = 7
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        config = client.put("/wan2gp/config", json=legacy).json()
        assert len(config["profiles"]) == 4
        assert config["profiles"]["ltx-2.3-distilled-1.1"]["preview"]["inference_steps"] == 7
        config["profile"] = config["profiles"]["minimax-h3-fl2va-pruned-20b"]
        config["profile"]["preview"]["inference_steps"] = 24
        assert client.put("/wan2gp/config", json=config).is_success
    with TestClient(create_app(settings)) as client:
        config = client.get("/wan2gp/config").json()
        assert config["profile"]["name"] == "minimax-h3-fl2va-pruned-20b"
        assert config["profile"]["preview"]["inference_steps"] == 24
        config["profile"] = config["profiles"]["ltx-2.3-distilled-1.1"]
        assert (
            client.put("/wan2gp/config", json=config).json()["profile"]["preview"][
                "inference_steps"
            ]
            == 7
        )
        config["profile"] = config["profiles"]["minimax-h3-fl2va-33b"]
        config["profile"]["final"]["resolution"] = "1920x1080"
        assert client.put("/wan2gp/config", json=config).status_code == 422


def test_queued_renderer_snapshot_survives_switch_and_retry(tmp_path: Path, monkeypatch) -> None:
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene, start, end, audio = create_project_with_scene(client, tmp_path)
        service = Wan2GPService(app.state.database)
        body = render_request(scene, start, end, audio)
        job, _ = service.start_render(VideoRenderRequest.model_validate(body))
        frozen = job.output["renderer_config"]
        config = client.get("/wan2gp/config").json()
        config["profile"] = config["profiles"]["minimax-h3-fl2va-33b"]
        assert client.put("/wan2gp/config", json=config).is_success
        params = build_queue_params(
            VideoRenderRequest.model_validate(job.output["request"]),
            Wan2GPConfig.model_validate(frozen),
        )
        assert params["model_type"] == "ltx2_22B_distilled_1_1"
        store = ProjectStore(project["path"])
        job.state = JobState.FAILED
        store.update_job(job)
        monkeypatch.setattr(app.state.job_manager, "submit", lambda *_args: None)
        retried = app.state.job_manager.retry(project["path"], job.id)
        assert retried.output["renderer_config"] == frozen
        assert retried.output["request"] == job.output["request"]


def test_config_persists_and_offline_service_is_safe(tmp_path: Path) -> None:
    def offline(*_args, **_kwargs):
        raise OSError("connection refused")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("beatweave.wan2gp.adapter.urlopen", offline)
        database_path = tmp_path / "application.db"
        config = Wan2GPConfig(base_url="http://127.0.0.1:9199")
        with TestClient(create_app(Settings(database_path=database_path))) as client:
            assert client.put("/wan2gp/config", json=config.model_dump(mode="json")).is_success
            status = client.post("/wan2gp/test").json()
            assert status["available"] is False
            assert "offline" in status["message"].lower()
            assert client.get("/health").is_success
        with TestClient(create_app(Settings(database_path=database_path))) as reopened:
            assert reopened.get("/wan2gp/config").json()["base_url"] == ("http://127.0.0.1:9199")


def test_adapter_uses_stateful_gradio_queue_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, tuple]] = []

    class FakeJob:
        def done(self):
            return True

        def result(self):
            return None

    class FakeClient:
        def __init__(self, *_args, download_files, **_kwargs):
            self.download_files = Path(download_files)
            self.output_directory = Path(download_files)
            self.session_hash = "test-session"
            self.endpoints = {336: FakeEndpoint()}
            self.executor = ImmediateExecutor()

        def _infer_fn_index(self, *_args):
            return 336

        def new_helper(self, *_args):
            return SimpleNamespace(updates=SimpleQueue())

        def submit(self, *args, api_name):
            if api_name != "/process_tasks_1":
                return completed_job(self.predict(api_name=api_name))
            calls.append((api_name, args))
            return FakeJob()

        def predict(self, *, api_name):
            calls.append((api_name, ()))
            assert self.download_files is False
            output = self.output_directory / "remote-output.mp4"
            output.write_bytes(b"video")
            return (0, [{"video": {"path": str(output)}}])

        def close(self):
            calls.append(("close", ()))

    class FakeEndpoint:
        dependency = {"targets": [[791, "upload"]]}

        def make_end_to_end_fn(self, _helper):
            def invoke(*args, **kwargs):
                calls.append(("/load_queue_action", (*args, kwargs)))
                return {"value": "One queued task"}

            return invoke

    class FakeContext:
        def check_cancelled(self):
            return None

        def report(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", FakeClient)
    monkeypatch.setattr("beatweave.wan2gp.adapter.handle_file", lambda path: str(path))
    queue = tmp_path / "queue.zip"
    queue.write_bytes(b"queue")

    result = Wan2GPAdapter(Wan2GPConfig()).execute(queue, tmp_path / "outputs", FakeContext())

    assert result.output_path.read_bytes() == b"video"
    assert [name for name, _args in calls] == [
        "/load_queue_action",
        "/process_tasks_1",
        "/finalize_generation_with_state",
        "close",
    ]


def test_render_associates_output_with_scene_and_preserves_canonical_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_execute(_self, _queue_path, output_directory, _context):
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "generated.mp4"
        output.write_bytes(b"synthetic-video")
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene_id, start_id, end_id, audio_id = create_project_with_scene(client, tmp_path)
        response = client.post(
            "/wan2gp/renders", json=render_request(scene_id, start_id, end_id, audio_id)
        )
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])

    assert job["state"] == "complete"
    assert job["related_entity_type"] == "scene"
    assert job["related_entity_id"] == scene_id
    store = ProjectStore(project["path"])
    asset = store.get_asset(job["output"]["asset_id"])
    assert asset is not None
    take = store.get_video_take(job["output"]["take_id"])
    assert take is not None
    assert take.asset_id == asset.id
    assert asset.filename.startswith("scene_01_")
    assert asset.kind == "generated_video"
    assert asset.media_metadata["scene_id"] == scene_id
    assert (store.directory / asset.relative_path).read_bytes() == b"synthetic-video"
    with store.connection() as connection:
        scene = dict(
            connection.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
        )
    assert scene["video_prompt"] == "canonical scene prompt"
    assert "queue" not in scene
    queue_path = store.directory / job["output"]["queue_path"]
    assert queue_path.is_file()
    with zipfile.ZipFile(queue_path) as archive:
        manifest = json.loads(archive.read("queue.json"))
        assert manifest[0]["params"]["output_filename"] == f"beatweave_scene_01_{job['id']}"
        assert manifest[0]["params"]["audio_prompt_type"] == "A"
        with wave.open(io.BytesIO(archive.read("task1_audio_guide_0.wav"))) as audio:
            assert audio.getnchannels() == 2
            assert audio.getframerate() == 48_000
            assert audio.getnframes() == 50_000


@pytest.mark.skipif(
    os.environ.get("BEATWEAVE_RUN_WAN2GP_INTEGRATION") != "1",
    reason="Set BEATWEAVE_RUN_WAN2GP_INTEGRATION=1 for a live LTX render",
)
def test_live_wan2gp_render(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    app = create_app(Settings(database_path=database_path))
    with TestClient(app) as client:
        source_image = Path(__file__).parents[2] / "design.png"
        project, scene_id, start_id, end_id, audio_id = create_project_with_scene(
            client, tmp_path, source_image=source_image
        )
        config = Wan2GPConfig(
            base_url=os.environ.get("BEATWEAVE_WAN2GP_URL", "http://localhost:7860")
        )
        assert client.put("/wan2gp/config", json=config.model_dump(mode="json")).is_success
        assert client.post("/wan2gp/test").json()["profile_ready"] is True
        request = render_request(scene_id, start_id, end_id, audio_id)
        request["duration_seconds"] = 0.7
        started = client.post("/wan2gp/renders", json=request).json()
        completed = wait_for_job(client, started["job"]["id"], timeout=7200)
        assert completed["state"] == "complete", completed.get("error")
    asset = ProjectStore(project["path"]).get_asset(completed["output"]["asset_id"])
    assert asset is not None
    assert (Path(project["path"]) / asset.relative_path).is_file()


@pytest.mark.parametrize("finish_after_restart", [False, True])
def test_recovery_monitors_original_session_without_resubmitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish_after_restart: bool
) -> None:
    expected = "beatweave_scene_02_unique-job"
    saved = {
        "wan2gp_session_hash": "original-session",
        "wan2gp_submission_started": True,
        "wan2gp_output_filename": expected,
        "recovered_after_restart": True,
    }
    output_directory = tmp_path / "downloads"
    output_directory.mkdir()
    unrelated = output_directory / "other-scene.mp4"
    unrelated.write_bytes(b"unrelated")
    output = output_directory / f"{expected}.mp4"
    if not finish_after_restart:
        output.write_bytes(b"finished-original-render")
    calls = []

    class Endpoint:
        def download_files(self, value):
            return (value,)

    class RecoveryClient:
        def __init__(self, *_args, **_kwargs):
            self.session_hash = "new-session"
            self.download_files = output_directory
            self.endpoints = {1: Endpoint()}

        def _infer_fn_index(self, *_args):
            return 1

        def predict(self, *, api_name):
            assert api_name == "/refresh_gallery"
            assert self.session_hash == "original-session"
            calls.append(api_name)
            if finish_after_restart and len(calls) == 1:
                return [str(unrelated)]
            output.write_bytes(b"finished-original-render")
            return [str(unrelated), {"video": {"path": str(output)}}]

        def submit(self, *, api_name):
            return completed_job(self.predict(api_name=api_name))

        def close(self):
            pass

    class Context:
        project_path = tmp_path
        job_id = "unique-job"

        def report(self, _progress, metadata=None):
            saved.update(metadata or {})

        def check_cancelled(self):
            pass

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", RecoveryClient)
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.ProjectStore",
        lambda _: SimpleNamespace(get_job=lambda _: SimpleNamespace(output=saved)),
    )
    monkeypatch.setattr("beatweave.wan2gp.adapter.time.sleep", lambda _: None)
    result = Wan2GPAdapter(Wan2GPConfig()).execute(
        tmp_path / "queue.zip", output_directory, Context()
    )
    assert result.output_path == output
    assert saved["wan2gp_download_complete"] is True
    assert len(calls) == (2 if finish_after_restart else 1)


def test_recovery_reuses_completed_download_without_contacting_wan2gp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "finished.mp4"
    output.write_bytes(b"completed-download")
    unrelated = tmp_path / "another-take.mp4"
    unrelated.write_bytes(b"another-take")
    saved = {"wan2gp_download_complete": True, "wan2gp_downloaded_path": str(output)}
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.ProjectStore",
        lambda _: SimpleNamespace(get_job=lambda _: SimpleNamespace(output=saved)),
    )
    context = SimpleNamespace(project_path=tmp_path, job_id="job")
    result = Wan2GPAdapter(Wan2GPConfig(base_url="http://localhost:1")).execute(
        tmp_path / "queue.zip", tmp_path, context
    )
    assert result.output_path == output


def test_recovery_finds_job_output_after_renderer_session_is_lost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beatweave.media.process import MediaProcessRunner

    output = tmp_path / "beatweave_scene_01_original-job.mp4"
    runner = MediaProcessRunner()
    runner.run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=1",
            "-c:v",
            "libx264",
            str(output),
        ]
    )
    saved = {
        "wan2gp_output_filename": output.stem,
        "wan2gp_submission_started": True,
        "recovered_after_restart": True,
    }
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.ProjectStore",
        lambda _: SimpleNamespace(get_job=lambda _: SimpleNamespace(output=saved)),
    )
    result = Wan2GPAdapter(
        Wan2GPConfig(
            base_url="http://localhost:1",
            output_directory=str(tmp_path),
        ),
        runner,
    ).execute(
        tmp_path / "queue.zip",
        tmp_path / "downloads",
        SimpleNamespace(project_path=tmp_path, job_id="original-job"),
    )
    assert result.output_path == output


def test_startup_registers_finished_render_without_resubmission(
    tmp_path: Path,
) -> None:
    from beatweave.jobs.schemas import JobState
    from beatweave.media.process import MediaProcessRunner
    from beatweave.wan2gp.schemas import Wan2GPConfigUpdate
    from beatweave.wan2gp.service import Wan2GPService

    database_path = tmp_path / "application.db"
    app = create_app(Settings(database_path=database_path))
    output_directory = tmp_path / "wan-outputs"
    output_directory.mkdir()
    with TestClient(app) as client:
        project, scene_id, start_id, end_id, audio_id = create_project_with_scene(client, tmp_path)
        service = Wan2GPService(app.state.database)
        service.update_config(
            Wan2GPConfigUpdate(
                base_url="http://localhost:1",
                output_directory=str(output_directory),
            )
        )
        job, _ = service.start_render(
            VideoRenderRequest.model_validate(render_request(scene_id, start_id, end_id, audio_id))
        )
        job.state = JobState.RUNNING
        job.output.update(
            {
                "wan2gp_session_hash": "lost-session",
                "wan2gp_submission_started": True,
                "wan2gp_output_filename": f"beatweave_scene_01_{job.id}",
                "select_on_complete": True,
            }
        )
        ProjectStore(project["path"]).update_job(job)
    # Wan2GP finishes while Beatweave is closed.
    finished = output_directory / f"beatweave_scene_01_{job.id}.mp4"
    MediaProcessRunner().run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=1",
            "-c:v",
            "libx264",
            str(finished),
        ]
    )
    with TestClient(create_app(Settings(database_path=database_path))) as restarted:
        recovered = wait_for_job(restarted, job.id)
        assert recovered["state"] == "complete", recovered.get("error")
        detail = restarted.get(f"/scenes/{scene_id}/takes").json()
        assert len(detail["takes"]) == 1
        assert detail["selected_take_id"] == recovered["output"]["take_id"]
        assert finished.is_file()
        assert len(restarted.get("/jobs").json()) == 1
