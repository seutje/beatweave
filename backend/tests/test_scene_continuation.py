import shutil
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.main import create_app
from beatweave.media.process import MediaProcessRunner
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.profile import frame_count
from beatweave.wan2gp.schemas import VideoRenderRequest, Wan2GPConfig, Wan2GPExecutionResult
from test_video_takes import create_renderable_scene, wait_for_job


def boundary_video(path: Path) -> Path:
    MediaProcessRunner().run_ffmpeg(
        [
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=32x32:r=24:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=32x32:r=24:d=0.25",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0",
            "-c:v",
            "libx264",
            "-crf",
            "0",
            str(path),
        ]
    )
    return path


def setup_scenes(client, tmp_path):
    project, first_id = create_renderable_scene(client, tmp_path)
    split = client.post("/timeline/scenes", json={"at_time": 0.5})
    assert split.is_success
    second_id = split.json()["scenes"][1]["id"]
    for scene_id in (first_id, second_id):
        assert client.patch(
            f"/timeline/scenes/{scene_id}",
            json={
                "video_prompt": "Move",
                "use_last_frame_conditioning": False,
            },
        ).is_success
    return project, first_id, second_id


def test_extracts_first_invisible_frame_and_rejects_missing_frame(tmp_path):
    runner = MediaProcessRunner()
    video = boundary_video(tmp_path / "boundary.mp4")
    image = tmp_path / "frame.png"
    for cut in (0.5, 0.501):
        image.write_bytes(runner.first_frame_after_cut(video, cut))
        pixels = runner.run_ffmpeg(
            [
                "-v",
                "error",
                "-i",
                str(image),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )
        assert pixels[2] > 240 and pixels[0] < 10  # blue, never last visible red
    with pytest.raises(BeatweaveError, match="no frame after"):
        runner.first_frame_after_cut(video, 0.75)


def test_queued_chain_resolves_after_previous_render_and_persists(tmp_path, monkeypatch):
    source = boundary_video(tmp_path / "source.mp4")
    expected = MediaProcessRunner().first_frame_after_cut(source, 0.5)
    entered, release = threading.Event(), threading.Event()
    starts = []

    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            starts.append(archive.read("task1_image_start_0.png"))
        if len(starts) == 1:
            entered.set()
            assert release.wait(10)
        else:
            assert starts[-1] == expected
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "rendered.mp4"
        shutil.copyfile(source, output)
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    settings = Settings(database_path=tmp_path / "app.db")
    with TestClient(create_app(settings)) as client:
        project, first, second = setup_scenes(client, tmp_path)
        toggle = client.patch(f"/timeline/scenes/{second}", json={"use_previous_scene_frame": True})
        assert toggle.is_success
        assert (
            client.post("/timeline/history/undo").json()["scenes"][1]["use_previous_scene_frame"]
            is False
        )
        assert (
            client.post("/timeline/history/redo").json()["scenes"][1]["use_previous_scene_frame"]
            is True
        )
        assert (
            client.patch(
                f"/timeline/scenes/{first}", json={"use_previous_scene_frame": True}
            ).status_code
            == 422
        )
        assert client.get(f"/scenes/{second}/previous-frame").status_code == 422
        store = ProjectStore(project["path"])
        a = client.post(f"/scenes/{first}/renders", json={"select_on_complete": True}).json()["job"]
        try:
            assert entered.wait(5)
            response = client.post(
                f"/scenes/{second}/renders",
                json={
                    "select_on_complete": True,
                    "previous_render_job_id": a["id"],
                },
            )
            assert response.status_code == 202
            b = response.json()["job"]
            assert b["output"]["request"]["start_keyframe_asset_id"] is None
            assert a["output"]["request"]["retain_continuation_frame"] is True
        finally:
            release.set()
        assert wait_for_job(client, a["id"])["state"] == "complete"
        completed = wait_for_job(client, b["id"])
        assert completed["state"] == "complete", completed
        frame = client.get(f"/scenes/{second}/previous-frame").json()
        assert client.get(f"/scenes/{second}/previous-frame").json()["id"] == frame["id"]
        assert completed["output"]["request"]["start_keyframe_asset_id"] == frame["id"]
        detail = client.get(f"/scenes/{second}/takes").json()
        assert detail["selected_take_stale"] is False
        assert detail["takes"][0]["source_asset_ids"][0] == frame["id"]
        assert store.get_asset(frame["id"]) is not None
        assert len(starts) == 2
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get("/timeline").json()["scenes"][1]["use_previous_scene_frame"] is True
        assert reopened.get(f"/scenes/{second}/previous-frame").json()["id"] == frame["id"]
        assert reopened.patch(
            f"/timeline/scenes/{second}", json={"use_previous_scene_frame": False}
        ).is_success
        assert reopened.get(f"/scenes/{second}/takes").json()["selected_take_stale"] is True


def test_missing_previous_take_fails_job_without_submission(tmp_path, monkeypatch):
    submitted = []
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.Wan2GPAdapter.execute", lambda *args: submitted.append(args)
    )
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, _, second = setup_scenes(client, tmp_path)
        assert client.patch(
            f"/timeline/scenes/{second}", json={"use_previous_scene_frame": True}
        ).is_success
        response = client.post(f"/scenes/{second}/renders", json={})
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])
        assert job["state"] == "failed"
        assert job["error"]["code"] == "previous_scene_take_required"
        assert submitted == []


def test_retry_reuses_frozen_frame_after_previous_selection_changes(tmp_path, monkeypatch):
    source = boundary_video(tmp_path / "source.mp4")
    calls = []

    def fake_execute(_self, queue_path, output_directory, _context):
        calls.append(queue_path)
        if len(calls) == 1:
            raise BeatweaveError("test_failure", "Simulated remote failure")
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "rendered.mp4"
        shutil.copyfile(source, output)
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, first, second = setup_scenes(client, tmp_path)
        assert client.post(f"/scenes/{first}/takes/import", json={"path": str(source)}).is_success
        assert client.patch(
            f"/timeline/scenes/{second}", json={"use_previous_scene_frame": True}
        ).is_success
        response = client.post(f"/scenes/{second}/renders", json={})
        failed = wait_for_job(client, response.json()["job"]["id"])
        assert failed["state"] == "failed"
        frozen_id = failed["output"]["request"]["start_keyframe_asset_id"]
        assert frozen_id
        assert client.post(f"/scenes/{first}/takes/import", json={"path": str(source)}).is_success
        assert client.get(f"/scenes/{second}/previous-frame").json()["id"] != frozen_id
        retried = client.post(f"/jobs/{failed['id']}/retry")
        assert retried.is_success
        completed = wait_for_job(client, retried.json()["job"]["id"])
        assert completed["state"] == "complete", completed
        assert completed["output"]["request"]["start_keyframe_asset_id"] == frozen_id


@pytest.mark.parametrize("duration", [0.5, 1, 1.01, 5, 5.34])
def test_chained_render_includes_real_frame_at_or_after_cut(duration):
    import math

    request = VideoRenderRequest(
        scene_id="scene",
        start_keyframe_asset_id="image",
        audio_asset_id="audio",
        audio_start_seconds=0,
        prompt="Move",
        duration_seconds=duration,
        retain_continuation_frame=True,
    )
    count = frame_count(request, Wan2GPConfig())
    assert count >= math.ceil(duration * request.frame_rate - 1e-9) + 1


def test_migration_defaults_off_and_preserves_shared_keyframes(tmp_path):
    settings = Settings(database_path=tmp_path / "app.db")
    with TestClient(create_app(settings)) as client:
        project, first, second = setup_scenes(client, tmp_path)
        before = client.get("/timeline").json()
    store = ProjectStore(project["path"])
    with store.connection() as connection:
        connection.execute("ALTER TABLE scenes DROP COLUMN use_previous_scene_frame")
        connection.execute("PRAGMA user_version = 12")
    with TestClient(create_app(settings)) as client:
        after = client.get("/timeline").json()
        assert [s["id"] for s in after["scenes"]] == [first, second]
        assert all(s["use_previous_scene_frame"] is False for s in after["scenes"])
        assert after["keyframes"] == before["keyframes"]
        assert after["scenes"][0]["end_keyframe_id"] == after["scenes"][1]["start_keyframe_id"]


def test_failed_batch_predecessor_does_not_fall_back_to_older_take(tmp_path, monkeypatch):
    source = boundary_video(tmp_path / "source.mp4")
    calls = []

    def fail(*args):
        calls.append(args)
        raise BeatweaveError("test_failure", "Simulated remote failure")

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fail)
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, first, second = setup_scenes(client, tmp_path)
        old = client.post(f"/scenes/{first}/takes/import", json={"path": str(source)}).json()
        assert client.patch(
            f"/timeline/scenes/{second}", json={"use_previous_scene_frame": True}
        ).is_success
        a = client.post(f"/scenes/{first}/renders", json={"select_on_complete": True}).json()["job"]
        assert wait_for_job(client, a["id"])["state"] == "failed"
        b = client.post(
            f"/scenes/{second}/renders", json={"previous_render_job_id": a["id"]}
        ).json()["job"]
        failed = wait_for_job(client, b["id"])
        assert failed["state"] == "failed"
        assert failed["error"]["code"] == "previous_render_incomplete"
        assert len(calls) == 1
        assert (
            client.get(f"/scenes/{first}/takes").json()["selected_take_id"]
            == old["selected_take_id"]
        )
