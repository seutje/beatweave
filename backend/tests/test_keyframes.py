import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from beatweave.comfyui.schemas import ImageRenderRequest
from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore


def create_project_with_timeline(client: TestClient, parent: Path) -> tuple[Path, dict]:
    parent.mkdir()
    project = client.post(
        "/projects", json={"name": "Keyframe Test", "parent_directory": str(parent)}
    ).json()
    directory = Path(project["path"])
    store = ProjectStore(directory)
    audio = AssetMetadata(
        id="audio-1",
        kind="audio",
        relative_path="source/track.wav",
        filename="track.wav",
        sha256="audio-hash",
        size_bytes=10,
        media_metadata={
            "duration_seconds": 10,
            "sample_rate": 48_000,
            "channels": 2,
            "codec": "pcm_s16le",
            "format_name": "wav",
        },
        created_at=datetime.now(UTC),
    )
    store.insert_asset(audio)
    store.update_project(store.read_project().model_copy(update={"audio_asset_id": audio.id}))
    client.post("/timeline/scenes", json={})
    timeline = client.post("/timeline/scenes", json={"at_time": 5}).json()
    return directory, timeline


def wait_for_job(client: TestClient, job_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("keyframe job did not finish")


def install_fake_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    def render(_self, context) -> dict:
        store = ProjectStore(context.project_path)
        job = store.get_job(context.job_id)
        request = ImageRenderRequest.model_validate(job.output["request"])
        asset_id = str(uuid4())
        path = store.directory / "keyframes" / f"{asset_id}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nrender")
        asset = AssetMetadata(
            id=asset_id,
            kind="generated_image",
            relative_path=path.relative_to(store.directory).as_posix(),
            filename=path.name,
            mime_type="image/png",
            sha256=asset_id.replace("-", ""),
            size_bytes=path.stat().st_size,
            media_metadata={"prompt": request.prompt},
            created_at=datetime.now(UTC),
        )
        store.insert_asset(asset)
        return {"asset_id": asset.id, "relative_path": asset.relative_path}

    monkeypatch.setattr("beatweave.comfyui.service.ComfyUIService.execute", render)


def generate(
    client: TestClient,
    keyframe_id: str,
    prompt: str,
    additional: list[str] | None = None,
    **overrides: object,
) -> dict:
    body = {"prompt": prompt, "additional_reference_asset_ids": additional or []}
    body.update(overrides)
    response = client.post(
        f"/keyframes/{keyframe_id}/generate",
        json=body,
    )
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["job"]["id"])
    assert job["state"] == "complete", job
    return client.get(f"/keyframes/{keyframe_id}").json()


def test_chained_variants_shared_selection_and_stale_render_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_renderer(monkeypatch)
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        directory, timeline = create_project_with_timeline(client, tmp_path / "projects")
        first_id = timeline["keyframes"][0]["id"]
        boundary_id = timeline["scenes"][0]["end_keyframe_id"]
        store = ProjectStore(directory)
        reference_ids = []
        for name in ("style", "extra"):
            path = directory / "references" / f"{name}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nreference")
            asset = AssetMetadata(
                id=f"{name}-reference",
                kind="style_reference",
                relative_path=path.relative_to(directory).as_posix(),
                filename=path.name,
                mime_type="image/png",
                sha256=f"{name}-hash",
                size_bytes=path.stat().st_size,
                created_at=datetime.now(UTC),
            )
            store.insert_asset(asset)
            reference_ids.append(asset.id)
        store.add_style_reference(reference_ids[0])

        first = generate(client, first_id, "Opening frame")
        first_asset_id = first["variants"][0]["asset_id"]
        assert first["variants"][0]["backend_settings"]["width"] == 1024
        assert first["variants"][0]["backend_settings"]["height"] == 576
        assert first["variants"][0]["backend_settings"]["quality_mode"] == "preview"
        assert first["variants"][0]["backend_settings"]["reference_mode"] == "semantic"
        assert first["variants"][0]["source_asset_ids"] == [reference_ids[0]]
        boundary_first = generate(client, boundary_id, "Shared boundary frame", [reference_ids[1]])
        assert boundary_first["variants"][0]["source_asset_ids"] == [
            first_asset_id,
            *reference_ids,
        ]
        assert boundary_first["variants"][0]["prompt"].startswith(
            "Use <image1>, the previous keyframe,"
        )
        assert "Reference images <image2> onward" in boundary_first["variants"][0]["prompt"]
        assert (
            "Target starting-frame image: Shared boundary frame"
            in boundary_first["variants"][0]["prompt"]
        )
        selected_first = boundary_first["keyframe"]["selected_variant_id"]

        boundary_second = generate(client, boundary_id, "Alternative boundary frame")
        assert len(boundary_second["variants"]) == 2
        assert boundary_second["keyframe"]["selected_variant_id"] == selected_first
        alternative = next(
            item for item in boundary_second["variants"] if item["id"] != selected_first
        )

        switched = client.post(
            f"/keyframes/{boundary_id}/variants/{alternative['id']}/select",
            json={"confirm_stale_renders": False},
        )
        assert switched.status_code == 200
        shared = switched.json()["timeline"]
        assert shared["scenes"][0]["end_keyframe_id"] == boundary_id
        assert shared["scenes"][1]["start_keyframe_id"] == boundary_id
        assert (
            next(item for item in shared["keyframes"] if item["id"] == boundary_id)[
                "selected_variant_id"
            ]
            == alternative["id"]
        )
        assert len(client.get(f"/keyframes/{boundary_id}").json()["variants"]) == 2

        with store.connection() as connection:
            connection.execute(
                "UPDATE scenes SET selected_video_take_id = 'existing-take' "
                "WHERE start_keyframe_id = ? OR end_keyframe_id = ?",
                (boundary_id, boundary_id),
            )
        warning = client.post(
            f"/keyframes/{boundary_id}/variants/{selected_first}/select",
            json={"confirm_stale_renders": False},
        )
        assert warning.status_code == 409
        assert warning.json()["error"]["code"] == "keyframe_variant_affects_renders"

        confirmed = client.post(
            f"/keyframes/{boundary_id}/variants/{selected_first}/select",
            json={"confirm_stale_renders": True},
        )
        assert confirmed.status_code == 200
        assert len(confirmed.json()["stale_scene_ids"]) == 2
        assert all(
            scene["selected_video_take_stale"] for scene in confirmed.json()["timeline"]["scenes"]
        )
        assert all(
            scene["selected_video_take_id"] == "existing-take"
            for scene in confirmed.json()["timeline"]["scenes"]
        )


def test_generation_randomizes_seed_unless_locked_and_can_skip_previous_keyframe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_renderer(monkeypatch)
    seeds = iter((101, 202))
    monkeypatch.setattr("beatweave.keyframes.service.randbelow", lambda _limit: next(seeds))
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        _directory, timeline = create_project_with_timeline(client, tmp_path / "projects")
        first_id = timeline["keyframes"][0]["id"]
        boundary_id = timeline["scenes"][0]["end_keyframe_id"]

        first = generate(client, first_id, "Opening frame")
        assert first["variants"][0]["backend_settings"]["seed"] == 101

        unchained = generate(
            client,
            boundary_id,
            "New composition",
            include_global_style_references=False,
            include_previous_keyframe=False,
        )
        assert unchained["variants"][0]["backend_settings"]["seed"] == 202
        assert unchained["variants"][0]["source_asset_ids"] == []
        assert unchained["variants"][0]["prompt"] == "New composition"

        locked = generate(
            client,
            boundary_id,
            "Locked composition",
            include_global_style_references=False,
            include_previous_keyframe=False,
            seed=777,
        )
        assert locked["variants"][0]["backend_settings"]["seed"] == 777


def test_shared_boundary_uses_previous_motion_and_can_be_set_to_black(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_renderer(monkeypatch)
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        directory, timeline = create_project_with_timeline(client, tmp_path / "projects")
        boundary_id = timeline["scenes"][0]["end_keyframe_id"]
        first_scene_id = timeline["scenes"][0]["id"]
        second_scene_id = timeline["scenes"][1]["id"]
        client.patch(
            f"/timeline/scenes/{first_scene_id}",
            json={"video_prompt": "spiral outward and dissolve into sparks"},
        )
        client.patch(
            f"/timeline/scenes/{second_scene_id}",
            json={"image_prompt": "a quiet amber field"},
        )

        rendered = generate(
            client,
            boundary_id,
            "a quiet amber field",
            include_previous_keyframe=False,
            include_global_style_references=False,
        )
        prompt = rendered["variants"][0]["prompt"]
        assert "Previous scene motion: spiral outward and dissolve into sparks" in prompt
        assert "Target starting-frame image: a quiet amber field" in prompt

        black = client.post(
            f"/keyframes/{boundary_id}/black",
            json={"confirm_stale_renders": False},
        )
        assert black.status_code == 200
        detail = black.json()["detail"]
        selected = next(
            item
            for item in detail["variants"]
            if item["id"] == detail["keyframe"]["selected_variant_id"]
        )
        assert selected["backend"] == "builtin"
        assert selected["backend_settings"]["kind"] == "black_frame"
        assert selected["asset"]["media_metadata"]["source"] == "black_frame"
        path = directory / selected["asset"]["relative_path"]
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
