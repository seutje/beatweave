import json
import math
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.main import create_app
from beatweave.media.process import MediaProcessRunner
from beatweave.media.timing import timeline_frame_count
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import RenderSceneRequest
from beatweave.video_takes.service import VideoTakeService
from beatweave.wan2gp.profile import build_queue_params
from beatweave.wan2gp.schemas import VideoRenderRequest, Wan2GPConfig, Wan2GPExecutionResult
from test_video_takes import create_renderable_scene, wait_for_job


@pytest.mark.parametrize("profile", list(Wan2GPConfig().profiles))
@pytest.mark.parametrize("duration", [0.2, 1, 1.3, 4.46, 5.2, 175 / 24, 12.5])
def test_all_renderers_leave_a_spare_frame_at_supported_lengths(profile: str, duration: float):
    config = Wan2GPConfig()
    request = VideoRenderRequest(
        scene_id="scene",
        start_keyframe_asset_id="start",
        audio_asset_id="audio",
        audio_start_seconds=0,
        prompt="Motion",
        duration_seconds=duration,
        model_profile=profile,
    )
    count = build_queue_params(request, config)["video_length"]
    assert count >= math.ceil(duration * 24) + 1
    if profile.startswith("minimax"):
        assert count >= 107
        assert (count - 107) % 17 == 0
    else:
        assert count >= 17
        assert (count - 17) % 8 == 0


def create_chain(client: TestClient, tmp_path: Path):
    project, first = create_renderable_scene(client, tmp_path)
    store = ProjectStore(project["path"])
    second, end = str(uuid4()), str(uuid4())
    now = datetime.now(UTC).isoformat()
    with store.connection() as connection:
        shared = connection.execute("SELECT end_keyframe_id FROM scenes").fetchone()[0]
        connection.execute("UPDATE scenes SET use_last_frame_conditioning = 0")
        # A rendered continuation does not require a planned start-image selection.
        connection.execute(
            "UPDATE keyframes SET selected_variant_id = NULL WHERE id = ?", (shared,)
        )
        connection.execute(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, 2, ?, ?)",
            (end, now, now),
        )
        connection.execute(
            """
            INSERT INTO scenes (id, position, start_time, end_time, start_keyframe_id,
                end_keyframe_id, video_prompt, use_last_frame_conditioning, created_at, updated_at)
            VALUES (?, 1, 1, 2, ?, ?, 'Original motion prompt', 0, ?, ?)
            """,
            (second, shared, end, now, now),
        )
    return project, first, second, shared


def make_video(path: Path, frames: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    MediaProcessRunner().run_ffmpeg(
        [
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=24",
            "-vf",
            "drawbox=c=lime:t=fill:enable='eq(n,24)',drawbox=c=blue:t=fill:enable='gte(n,25)'",
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-crf",
            "0",
            str(path),
        ]
    )


@pytest.mark.parametrize("profile", ["ltx-2.3-distilled-1.1", "minimax-h3-fl2va-pruned-20b-pdd"])
def test_batch_chain_uses_frame_after_cut_and_recovers_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
):
    queues = []
    starts = []

    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            params = json.loads(archive.read("queue.json"))[0]["params"]
            queues.append(params)
            starts.append(archive.read("task1_image_start_0.png"))
        output = output_directory / "render.mp4"
        make_video(output, params["video_length"])
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    settings = Settings(database_path=tmp_path / "application.db")
    app = create_app(settings)
    with TestClient(app) as client:
        project, first, second, shared = create_chain(client, tmp_path)
        config = client.get("/wan2gp/config").json()
        config["profile"] = config["profiles"][profile]
        assert client.put("/wan2gp/config", json=config).is_success
        service = VideoTakeService(app.state.database)
        first_job, _ = service.start_render(first, RenderSceneRequest(select_on_complete=True))
        second_job, _ = service.start_render(second, RenderSceneRequest(select_on_complete=True))
        source = second_job.output["request"]["continuation"]
        assert source["job_id"] == first_job.id
        assert source["keyframe_id"] == shared
        assert second_job.output["request"]["start_keyframe_asset_id"] is None

    with TestClient(create_app(settings)) as client:
        first_result = wait_for_job(client, first_job.id)
        result = wait_for_job(client, second_job.id)
        assert first_result["state"] == "complete", first_result
        assert result["state"] == "complete", result
        detail = client.get(f"/scenes/{second}/takes").json()
        assert detail["selected_take_stale"] is False
        take = detail["takes"][0]
        source = take["backend_settings"]["start_frame_source"]
        assert source["take_id"] == first_result["output"]["take_id"]
        assert source["frame_index"] == 24  # kept 0..23, continue from 24
        assert source["asset_id"] == take["source_asset_ids"][0]
        assert client.get("/exports/readiness").json()["ready"] is True
        store = ProjectStore(project["path"])
        with store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM keyframes").fetchone()[0] == 3
            assert (
                connection.execute(
                    "SELECT selected_variant_id FROM keyframes WHERE id = ?", (shared,)
                ).fetchone()[0]
                is None
            )

        # The uploaded image is the green spare frame, not the red last kept
        # frame, blue end of the full source, or the original planned keyframe.
        png = tmp_path / "uploaded.png"
        png.write_bytes(starts[1])
        pixel = MediaProcessRunner().run_ffmpeg(
            [
                "-v",
                "error",
                "-i",
                str(png),
                "-vf",
                "scale=1:1",
                "-frames:v",
                "1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ]
        )
        assert pixel[1] > 240 and pixel[0] < 10 and pixel[2] < 10
        assert len(queues) == 2
        assert all(queue["video_length"] > 24 for queue in queues)

        # Switching the predecessor invalidates only dependent takes. Keeping
        # the original source selected makes the existing chain current again.
        response = client.post(f"/scenes/{first}/renders", json={"quality_mode": "preview"})
        alternative = wait_for_job(client, response.json()["job"]["id"])
        assert alternative["state"] == "complete", alternative
        alternate_id = alternative["output"]["take_id"]
        client.post(f"/scenes/{first}/takes/{alternate_id}/select")
        assert client.get("/exports/readiness").json()["ready"] is False
        assert client.get(f"/scenes/{second}/takes").json()["selected_take_stale"] is True
        original_id = first_result["output"]["take_id"]
        client.post(f"/scenes/{first}/takes/{original_id}/select")
        assert client.get("/exports/readiness").json()["ready"] is True


@pytest.mark.parametrize("failure", ["failed", "short", "cancelled"])
def test_missing_predecessor_frame_never_falls_back_to_planned_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
):
    calls = []

    def fake_execute(_self, _queue_path, output_directory, _context):
        calls.append(True)
        if failure == "failed":
            raise BeatweaveError("synthetic_failure", "Render failed")
        output = output_directory / "short.mp4"
        make_video(output, 24)
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    settings = Settings(database_path=tmp_path / "application.db")
    app = create_app(settings)
    with TestClient(app) as client:
        _, first, second, _ = create_chain(client, tmp_path)
        service = VideoTakeService(app.state.database)
        first_job, path = service.start_render(first, RenderSceneRequest(select_on_complete=True))
        second_job, _ = service.start_render(second, RenderSceneRequest(select_on_complete=True))
        if failure == "cancelled":
            app.state.job_manager.cancel(path, first_job.id)
    with TestClient(create_app(settings)) as client:
        result = wait_for_job(client, second_job.id)
        assert result["state"] == "failed", result
        assert result["error"]["code"] == (
            "video_continuation_frame_missing"
            if failure == "short"
            else "video_continuation_dependency_failed"
        )
        assert len(calls) == (0 if failure == "cancelled" else 1)
        assert client.get(f"/scenes/{second}/takes").json()["takes"] == []


def test_fractional_scene_cuts_do_not_accumulate_rounding_error():
    cuts = [index * 0.31 for index in range(101)]
    counts = [
        timeline_frame_count(start, end, 24) for start, end in zip(cuts, cuts[1:], strict=False)
    ]
    assert sum(counts) == 744
    assert sum(round((end - start) * 24) for start, end in zip(cuts, cuts[1:], strict=False)) == 700


def test_export_rejects_short_media_instead_of_shifting_following_scenes(tmp_path: Path):
    source = tmp_path / "short.mp4"
    make_video(source, 20)
    with pytest.raises(BeatweaveError) as error:
        MediaProcessRunner().normalize_video_clip(
            source,
            tmp_path / "normalized.mp4",
            duration_seconds=1,
            frame_count=24,
            frame_rate=24,
            width=256,
            height=256,
            codec="libx264",
            crf=18,
        )
    assert error.value.code == "export_clip_too_short"
