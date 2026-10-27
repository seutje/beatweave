import json
import time
import wave
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.keyframes.schemas import KeyframeVariant
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata, Project
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import RenderSceneRequest
from beatweave.video_takes.service import VideoTakeService
from beatweave.wan2gp.schemas import Wan2GPExecutionResult


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("render job did not finish")


def create_renderable_scene(client: TestClient, tmp_path: Path) -> tuple[dict, str]:
    parent = tmp_path / "projects"
    parent.mkdir()
    project_data = client.post(
        "/projects", json={"name": "Takes Test", "parent_directory": str(parent)}
    ).json()
    store = ProjectStore(project_data["path"])
    now = datetime.now(UTC)

    audio_path = store.directory / "source" / "audio.wav"
    with wave.open(str(audio_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 16_000)
    audio = AssetMetadata(
        id=str(uuid4()),
        kind="audio",
        relative_path=audio_path.relative_to(store.directory).as_posix(),
        filename=audio_path.name,
        mime_type="audio/wav",
        sha256="audio-hash",
        size_bytes=audio_path.stat().st_size,
        media_metadata={"duration_seconds": 2.0},
        created_at=now,
    )
    store.insert_asset(audio)
    project = Project.model_validate(project_data).model_copy(update={"audio_asset_id": audio.id})
    store.update_project(project)

    asset_ids: list[str] = []
    for index in range(2):
        path = store.directory / "keyframes" / f"boundary-{index}.png"
        path.write_bytes(b"image" + bytes([index]))
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_image",
            relative_path=path.relative_to(store.directory).as_posix(),
            filename=path.name,
            mime_type="image/png",
            sha256=f"image-hash-{index}",
            size_bytes=path.stat().st_size,
            created_at=now,
        )
        store.insert_asset(asset)
        asset_ids.append(asset.id)

    scene_id = str(uuid4())
    keyframe_ids = [str(uuid4()), str(uuid4())]
    variant_ids = [str(uuid4()), str(uuid4())]
    now_iso = now.isoformat()
    with store.connection() as connection:
        connection.executemany(
            """
            INSERT INTO keyframes (
                id, time, selected_variant_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (keyframe_ids[0], 0, variant_ids[0], now_iso, now_iso),
                (keyframe_ids[1], 1, variant_ids[1], now_iso, now_iso),
            ],
        )
        connection.execute(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_keyframe_id, end_keyframe_id,
                video_prompt, motion_energy, created_at, updated_at
            ) VALUES (?, 0, 0, 1, ?, ?, 'Original motion prompt', 0.5, ?, ?)
            """,
            (scene_id, keyframe_ids[0], keyframe_ids[1], now_iso, now_iso),
        )
    for index in range(2):
        store.insert_keyframe_variant(
            KeyframeVariant(
                id=variant_ids[index],
                keyframe_id=keyframe_ids[index],
                asset_id=asset_ids[index],
                source_job_id=f"keyframe-job-{index}",
                prompt=f"Boundary {index}",
                backend="test",
                created_at=now,
            )
        )
    return project_data, scene_id


@pytest.mark.parametrize("enabled", [False, True])
def test_ltx_lora_setting_persists_and_preview_promotion_keeps_it(
    tmp_path: Path, monkeypatch, enabled: bool
) -> None:
    queues = []

    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            queues.append(json.loads(archive.read("queue.json"))[0]["params"])
            assert "task1_audio_guide_0.wav" in archive.namelist()
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "generated.mp4"
        output.write_bytes(b"video")
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        project, scene = create_renderable_scene(client, tmp_path)
        config = client.get("/wan2gp/config").json()
        config["audio_reactive_profile"]["enabled"] = enabled
        config["audio_reactive_profile"]["default_multiplier"] = 1.2
        assert client.patch(f"/timeline/scenes/{scene}", json={"motion_energy": 0.75}).is_success
        assert client.put("/wan2gp/config", json=config).is_success
    with TestClient(create_app(settings)) as client:
        config = client.get("/wan2gp/config").json()
        assert config["audio_reactive_profile"]["enabled"] is enabled
        response = client.post(f"/scenes/{scene}/renders", json={"quality_mode": "preview"})
        preview_job = wait_for_job(client, response.json()["job"]["id"])
        assert preview_job["state"] == "complete", preview_job
        preview = client.get(f"/scenes/{scene}/takes").json()["takes"][0]
        assert preview["backend_settings"]["audio_reactive_lora"]["enabled"] is enabled
        config["audio_reactive_profile"]["enabled"] = not enabled
        config["audio_reactive_profile"]["default_multiplier"] = 0.4
        assert client.put("/wan2gp/config", json=config).is_success
        response = client.post(
            f"/scenes/{scene}/renders",
            json={"quality_mode": "final", "source_take_id": preview["id"]},
        )
        final = wait_for_job(client, response.json()["job"]["id"])
        assert final["state"] == "complete", final
        for queue in queues:
            assert bool(queue["activated_loras"]) is enabled
            if enabled:
                assert float(queue["loras_multipliers"]) == pytest.approx(1.8)
            assert queue["audio_prompt_type"] == "A"
        assert len(queues) == 2
        assert queues[1]["resolution"] == "1920x1088"


@pytest.mark.parametrize("energy, factor", [(0, 0.5), (0.25, 0.75), (0.5, 1), (0.75, 1.5), (1, 2)])
def test_scene_motion_energy_scales_saved_lora_strength(tmp_path, monkeypatch, energy, factor):
    queues = []

    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            queues.append(json.loads(archive.read("queue.json"))[0]["params"])
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "generated.mp4"
        output.write_bytes(b"video")
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        _, scene = create_renderable_scene(client, tmp_path)
        config = client.get("/wan2gp/config").json()
        config["audio_reactive_profile"]["default_multiplier"] = 8
        assert client.put("/wan2gp/config", json=config).is_success
        assert client.patch(f"/timeline/scenes/{scene}", json={"motion_energy": energy}).is_success
        response = client.post(f"/scenes/{scene}/renders", json={"quality_mode": "preview"})
        assert response.status_code == 202, response.json()
        job = wait_for_job(client, response.json()["job"]["id"])
        assert job["state"] == "complete", job
        assert float(queues[0]["loras_multipliers"]) == 8 * factor
        take = client.get(f"/scenes/{scene}/takes").json()["takes"][0]
        assert take["backend_settings"]["audio_reactive_lora"]["multiplier"] == 8 * factor
        assert not take["stale"]
        client.patch(f"/timeline/scenes/{scene}", json={"visual_energy": 0.9})
        assert not client.get(f"/scenes/{scene}/takes").json()["selected_take_stale"]
        client.patch(f"/timeline/scenes/{scene}", json={"motion_energy": 0.1})
        detail = client.get(f"/scenes/{scene}/takes").json()
        assert detail["selected_take_stale"]
        assert detail["selected_take_id"] == take["id"]
        assert detail["takes"][0]["backend_settings"] == take["backend_settings"]


@pytest.mark.parametrize(
    "name",
    [
        "minimax-h3-fl2va-33b",
        "minimax-h3-fl2va-pruned-20b",
        "minimax-h3-fl2va-pruned-20b-pdd",
    ],
)
def test_h3_takes_and_preview_promotion_keep_renderer_after_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    queues = []

    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            queues.append(json.loads(archive.read("queue.json"))[0]["params"])
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "generated.mp4"
        output.write_bytes(b"video")
        return Wan2GPExecutionResult(output_path=output)

    def fake_audio(_self, _source, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"audio")

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    monkeypatch.setattr(
        "beatweave.media.process.MediaProcessRunner.extract_audio_segment", fake_audio
    )
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene = create_renderable_scene(client, tmp_path)
        store = ProjectStore(project["path"])
        with store.connection() as connection:
            connection.execute("UPDATE scenes SET end_time = 5 WHERE id = ?", (scene,))
            connection.execute("UPDATE keyframes SET time = 5 WHERE time = 1")
        config = client.get("/wan2gp/config").json()
        config["profile"] = config["profiles"][name]
        assert client.put("/wan2gp/config", json=config).is_success
        response = client.post(f"/scenes/{scene}/renders", json={"quality_mode": "preview"})
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])
        assert job["state"] == "complete", job
        preview = client.get(f"/scenes/{scene}/takes").json()["takes"][0]
        assert preview["backend_settings"]["model_profile"] == name
        assert preview["backend_settings"]["audio_reactive_lora"]["enabled"] is False
        assert preview["backend_settings"]["audio_conditioning"]["prompt_type"] == "A"
        assert preview["backend_settings"]["inference_steps"] == (
            8 if name.endswith("-pdd") else 20
        )
        config = client.get("/wan2gp/config").json()
        config["profile"] = config["profiles"]["ltx-2.3-distilled-1.1"]
        assert client.put("/wan2gp/config", json=config).is_success
        response = client.post(
            f"/scenes/{scene}/renders",
            json={"quality_mode": "final", "source_take_id": preview["id"]},
        )
        assert response.status_code == 202
        final = wait_for_job(client, response.json()["job"]["id"])
        assert final["state"] == "complete", final
        assert queues[0]["model_type"] == queues[1]["model_type"]
        assert queues[1]["resolution"] == "1920x1088"
        assert queues[1]["activated_loras"] == []
        takes = client.get(f"/scenes/{scene}/takes").json()
        assert len(takes["takes"]) == 2
        assert takes["selected_take_id"] == preview["id"]


def test_take_lifecycle_preserves_selected_take_when_new_render_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    render_number = 0

    def fake_execute(_self, _queue_path, output_directory, _context):
        nonlocal render_number
        render_number += 1
        if render_number == 3:
            raise BeatweaveError("synthetic_failure", "The third render failed.")
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / f"generated-{render_number}.mp4"
        output.write_bytes(f"video-{render_number}".encode())
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene_id = create_renderable_scene(client, tmp_path)

        preview_response = client.post(
            f"/scenes/{scene_id}/renders", json={"quality_mode": "preview"}
        )
        assert preview_response.status_code == 202
        preview_job = wait_for_job(client, preview_response.json()["job"]["id"])
        assert preview_job["state"] == "complete"
        preview_take_id = preview_job["output"]["take_id"]

        final_response = client.post(
            f"/scenes/{scene_id}/renders",
            json={"quality_mode": "final", "source_take_id": preview_take_id},
        )
        assert final_response.status_code == 202
        final_job = wait_for_job(client, final_response.json()["job"]["id"])
        assert final_job["state"] == "complete"
        final_take_id = final_job["output"]["take_id"]

        detail = client.get(f"/scenes/{scene_id}/takes").json()
        assert len(detail["takes"]) == 2
        assert detail["selected_take_id"] == preview_take_id
        timeline_video = client.get("/scenes/takes").json()
        assert [item["scene_id"] for item in timeline_video["scenes"]] == [scene_id]
        assert timeline_video["scenes"][0]["selected_take_id"] == preview_take_id
        take_by_id = {take["id"]: take for take in detail["takes"]}
        assert take_by_id[preview_take_id]["backend_settings"]["resolution"] == "768x448"
        assert take_by_id[final_take_id]["backend_settings"]["resolution"] == "1920x1088"
        assert take_by_id[preview_take_id]["asset"]["relative_path"].startswith("previews/")
        assert take_by_id[final_take_id]["asset"]["relative_path"].startswith("renders/")
        assert (
            take_by_id[final_take_id]["backend_settings"]["motion"]
            == take_by_id[preview_take_id]["backend_settings"]["motion"]
        )
        conditioning = take_by_id[final_take_id]["backend_settings"]["audio_conditioning"]
        assert (
            conditioning["asset_id"] == ProjectStore(project["path"]).read_project().audio_asset_id
        )
        assert conditioning["start_seconds"] == 0
        assert conditioning["prompt_type"] == "A"

        changed_config = client.get("/wan2gp/config").json()
        changed_config["profile"]["preview"]["resolution"] = "640x384"
        assert client.put("/wan2gp/config", json=changed_config).is_success
        unchanged = client.get(f"/scenes/{scene_id}/takes").json()
        unchanged_by_id = {take["id"]: take for take in unchanged["takes"]}
        assert unchanged_by_id[preview_take_id]["backend_settings"]["resolution"] == "768x448"

        selected = client.post(f"/scenes/{scene_id}/takes/{final_take_id}/select").json()["detail"]
        assert selected["selected_take_id"] == final_take_id

        edited = client.patch(
            f"/timeline/scenes/{scene_id}", json={"video_prompt": "A revised motion prompt"}
        )
        assert edited.status_code == 200
        assert edited.json()["scenes"][0]["selected_video_take_stale"] is True
        assert client.get(f"/scenes/{scene_id}/takes").json()["selected_take_stale"] is True

        failed_response = client.post(
            f"/scenes/{scene_id}/renders", json={"quality_mode": "preview"}
        )
        failed_job = wait_for_job(client, failed_response.json()["job"]["id"])
        assert failed_job["state"] == "failed"
        assert failed_job["error"]["code"] == "synthetic_failure"
        after_failure = client.get(f"/scenes/{scene_id}/takes").json()
        assert len(after_failure["takes"]) == 2
        assert after_failure["selected_take_id"] == final_take_id

        final_asset_path = Path(take_by_id[final_take_id]["asset_path"])
        deleted = client.delete(f"/scenes/{scene_id}/takes/{final_take_id}")
        assert deleted.status_code == 200
        assert deleted.json()["selected_take_id"] == preview_take_id
        assert not final_asset_path.exists()

    store = ProjectStore(project["path"])
    assert len(store.list_video_takes(scene_id)) == 1


def test_scene_renders_with_the_same_imported_image_at_both_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_execute(_self, _queue_path, output_directory, _context):
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "same-boundary-image.mp4"
        output.write_bytes(b"synthetic-video")
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene_id = create_renderable_scene(client, tmp_path)
        store = ProjectStore(project["path"])
        source = tmp_path / "same-image.png"
        source.write_bytes(b"image")
        with store.connection() as connection:
            keyframe_ids = [
                row["id"]
                for row in connection.execute("SELECT id FROM keyframes ORDER BY time").fetchall()
            ]

        selected_variant_ids = []
        selected_asset_ids = []
        for keyframe_id in keyframe_ids:
            imported = client.post(f"/keyframes/{keyframe_id}/import", json={"path": str(source)})
            assert imported.status_code == 200
            selected_variant_id = imported.json()["detail"]["keyframe"]["selected_variant_id"]
            selected_variant_ids.append(selected_variant_id)
            selected_asset_ids.append(store.get_keyframe_variant(selected_variant_id).asset_id)

        with store.connection() as connection:
            connection.execute(
                "UPDATE keyframe_variants SET asset_id = ? WHERE id = ?",
                (selected_asset_ids[0], selected_variant_ids[1]),
            )

        response = client.post(f"/scenes/{scene_id}/renders", json={"quality_mode": "preview"})
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])

    assert job["state"] == "complete"
    take = ProjectStore(project["path"]).get_video_take(job["output"]["take_id"])
    assert take is not None
    assert take.source_asset_ids[0] == take.source_asset_ids[1]


def test_scene_can_render_without_last_frame_conditioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_execute(_self, queue_path, output_directory, _context):
        with zipfile.ZipFile(queue_path) as archive:
            assert "task1_image_end_0.png" not in archive.namelist()
            params = json.loads(archive.read("queue.json"))[0]["params"]
            assert params["image_prompt_type"] == "S"
            assert params["image_end"] is None
            assert params["guidance_phases"] == 2
            assert params["sliding_window_size"] == 481
            assert params["sliding_window_overlap"] == 17
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / "start-only.mp4"
        output.write_bytes(b"synthetic-video")
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, scene_id = create_renderable_scene(client, tmp_path)
        updated = client.patch(
            f"/timeline/scenes/{scene_id}",
            json={"use_last_frame_conditioning": False},
        )
        assert updated.status_code == 200
        response = client.post(f"/scenes/{scene_id}/renders", json={"quality_mode": "preview"})
        job = wait_for_job(client, response.json()["job"]["id"])

    assert job["state"] == "complete"
    take = ProjectStore(project["path"]).get_video_take(job["output"]["take_id"])
    assert take is not None
    assert take.backend_settings["use_last_frame_conditioning"] is False
    assert len(take.source_asset_ids) == 2


def test_recovered_batch_render_selects_completed_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    render_number = 0

    def fake_execute(_self, _queue_path, output_directory, _context):
        nonlocal render_number
        render_number += 1
        output_directory.mkdir(parents=True, exist_ok=True)
        output = output_directory / f"recovered-{render_number}.mp4"
        output.write_bytes(f"video-{render_number}".encode())
        return Wan2GPExecutionResult(output_path=output)

    monkeypatch.setattr("beatweave.wan2gp.adapter.Wan2GPAdapter.execute", fake_execute)
    settings = Settings(database_path=tmp_path / "application.db")
    app = create_app(settings)
    with TestClient(app) as client:
        project, scene_id = create_renderable_scene(client, tmp_path)
        preview_response = client.post(
            f"/scenes/{scene_id}/renders", json={"quality_mode": "preview"}
        )
        preview_job = wait_for_job(client, preview_response.json()["job"]["id"])
        preview_take_id = preview_job["output"]["take_id"]

        pending, _ = VideoTakeService(app.state.database).start_render(
            scene_id,
            RenderSceneRequest(quality_mode="final", select_on_complete=True),
        )
        assert pending.output["select_on_complete"] is True
        assert ProjectStore(project["path"]).get_job(pending.id).state.value == "queued"

    with TestClient(create_app(settings)) as reopened:
        recovered = wait_for_job(reopened, pending.id)
        assert recovered["state"] == "complete"
        assert recovered["output"]["take_id"] != preview_take_id
        detail = reopened.get(f"/scenes/{scene_id}/takes").json()
        assert detail["selected_take_id"] == recovered["output"]["take_id"]
        assert len(detail["takes"]) == 2


def test_manual_video_import_creates_and_selects_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "beatweave.media.process.MediaProcessRunner.probe_video",
        lambda _self, _path: {
            "duration_seconds": 1.0,
            "width": 1920,
            "height": 1080,
            "codec": "h264",
            "format_name": "mov,mp4",
        },
    )
    source = tmp_path / "chosen clip.mp4"
    source.write_bytes(b"manual-video")
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        project, scene_id = create_renderable_scene(client, tmp_path)

        response = client.post(
            f"/scenes/{scene_id}/takes/import",
            json={"path": str(source)},
        )

        assert response.status_code == 200
        detail = response.json()
        take = detail["takes"][0]
        assert detail["selected_take_id"] == take["id"]
        assert take["backend"] == "manual"
        assert take["stale"] is False
        assert take["asset"]["kind"] == "imported_video"
        assert take["asset"]["original_path"] == str(source.resolve())
        assert Path(take["asset_path"]).read_bytes() == source.read_bytes()
        assert Path(take["asset_path"]).is_relative_to(Path(project["path"]))
