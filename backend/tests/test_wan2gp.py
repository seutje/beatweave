import json
import os
import shutil
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.profile import build_queue_params, write_queue_archive
from beatweave.wan2gp.schemas import (
    VideoRenderRequest,
    Wan2GPConfig,
    Wan2GPExecutionResult,
)


def create_project_with_scene(
    client: TestClient, tmp_path: Path, *, source_image: Path | None = None
) -> tuple[dict, str, str, str]:
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
    return project, scene_id, asset_ids[0], asset_ids[1]


def render_request(scene_id: str, start_id: str, end_id: str) -> dict:
    return {
        "scene_id": scene_id,
        "start_keyframe_asset_id": start_id,
        "end_keyframe_asset_id": end_id,
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
    request = VideoRenderRequest.model_validate(render_request("scene-1", "asset-1", "asset-2"))
    config = Wan2GPConfig()
    queue_path = tmp_path / "queue.zip"

    params = write_queue_archive(request, config, start, end, queue_path)

    assert params == build_queue_params(request, config)
    assert params["model_type"] == "ltx2_22B_distilled_1_1"
    assert params["image_prompt_type"] == "SE"
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
        }
        manifest = json.loads(archive.read("queue.json"))
    assert manifest == [{"id": 1, "params": params}]
    assert "wan2gp" not in request.model_dump_json().lower()


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
            self.endpoints = {336: FakeEndpoint()}

        def _infer_fn_index(self, *_args):
            return 336

        def new_helper(self, *_args):
            return SimpleNamespace(updates=SimpleQueue())

        def submit(self, *args, api_name):
            calls.append((api_name, args))
            return FakeJob()

        def predict(self, *, api_name):
            calls.append((api_name, ()))
            output = self.download_files / "remote-output.mp4"
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
        project, scene_id, start_id, end_id = create_project_with_scene(client, tmp_path)
        response = client.post("/wan2gp/renders", json=render_request(scene_id, start_id, end_id))
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])

    assert job["state"] == "complete"
    assert job["related_entity_type"] == "scene"
    assert job["related_entity_id"] == scene_id
    store = ProjectStore(project["path"])
    asset = store.get_asset(job["output"]["asset_id"])
    assert asset is not None
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


@pytest.mark.skipif(
    os.environ.get("BEATWEAVE_RUN_WAN2GP_INTEGRATION") != "1",
    reason="Set BEATWEAVE_RUN_WAN2GP_INTEGRATION=1 for a live LTX render",
)
def test_live_wan2gp_render(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    app = create_app(Settings(database_path=database_path))
    with TestClient(app) as client:
        source_image = Path(__file__).parents[2] / "design.png"
        project, scene_id, start_id, end_id = create_project_with_scene(
            client, tmp_path, source_image=source_image
        )
        config = Wan2GPConfig(
            base_url=os.environ.get("BEATWEAVE_WAN2GP_URL", "http://localhost:7860")
        )
        assert client.put("/wan2gp/config", json=config.model_dump(mode="json")).is_success
        assert client.post("/wan2gp/test").json()["profile_ready"] is True
        request = render_request(scene_id, start_id, end_id)
        request["duration_seconds"] = 0.7
        started = client.post("/wan2gp/renders", json=request).json()
        completed = wait_for_job(client, started["job"]["id"], timeout=7200)
        assert completed["state"] == "complete", completed.get("error")
    asset = ProjectStore(project["path"]).get_asset(completed["output"]["asset_id"])
    assert asset is not None
    assert (Path(project["path"]) / asset.relative_path).is_file()
