from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore


def client_for(database_path: Path) -> TestClient:
    return TestClient(create_app(Settings(database_path=database_path)))


def create_project_with_audio(client: TestClient, parent: Path, duration: float = 12.5) -> Path:
    parent.mkdir()
    response = client.post(
        "/projects", json={"name": "Timeline Test", "parent_directory": str(parent)}
    )
    assert response.status_code == 201
    project = response.json()
    directory = Path(project["path"])
    store = ProjectStore(directory)
    asset = AssetMetadata(
        id="audio-1",
        kind="audio",
        relative_path="source/track.wav",
        filename="track.wav",
        sha256="abc123",
        size_bytes=100,
        media_metadata={
            "duration_seconds": duration,
            "sample_rate": 48_000,
            "channels": 2,
            "codec": "pcm_s16le",
            "format_name": "wav",
        },
        created_at=datetime.now(UTC),
    )
    store.insert_asset(asset)
    stored_project = store.read_project().model_copy(update={"audio_asset_id": asset.id})
    store.update_project(stored_project)
    return directory


def assert_shared_boundary(timeline: dict, boundary_time: float) -> str:
    left, right = timeline["scenes"]
    assert left["end_time"] == boundary_time
    assert right["start_time"] == boundary_time
    assert left["end_keyframe_id"] == right["start_keyframe_id"]
    boundary_id = left["end_keyframe_id"]
    keyframe = next(item for item in timeline["keyframes"] if item["id"] == boundary_id)
    assert keyframe["time"] == boundary_time
    return boundary_id


def test_scene_editing_preserves_shared_keyframe_and_exact_timing(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    with client_for(database_path) as client:
        project_directory = create_project_with_audio(client, tmp_path / "projects")

        initial = client.post("/timeline/scenes", json={})
        assert initial.status_code == 201
        assert initial.json()["scenes"][0]["end_time"] == 12.5

        split = client.post("/timeline/scenes", json={"at_time": 4.125, "beat_index": 7})
        assert split.status_code == 201
        boundary_id = assert_shared_boundary(split.json(), 4.125)

        moved = client.patch(
            f"/timeline/keyframes/{boundary_id}",
            json={"time": 5.375, "beat_index": 9},
        )
        assert moved.status_code == 200
        boundary_id = assert_shared_boundary(moved.json(), 5.375)
        assert moved.json()["scenes"][0]["end_beat_index"] == 9
        assert moved.json()["scenes"][1]["start_beat_index"] == 9

        invalid = client.patch(f"/timeline/keyframes/{boundary_id}", json={"time": 12.5})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_scene_duration"

    with client_for(database_path) as reopened_client:
        opened = reopened_client.post("/projects/open", json={"path": str(project_directory)})
        assert opened.status_code == 200
        restored = reopened_client.get("/timeline")
        assert restored.status_code == 200
        assert_shared_boundary(restored.json(), 5.375)


def test_delete_scene_merges_neighbors_without_orphan_boundary(tmp_path: Path) -> None:
    with client_for(tmp_path / "application.db") as client:
        create_project_with_audio(client, tmp_path / "projects", duration=9)
        client.post("/timeline/scenes", json={})
        split = client.post("/timeline/scenes", json={"at_time": 3}).json()
        deleted = client.delete(f"/timeline/scenes/{split['scenes'][1]['id']}")

        assert deleted.status_code == 200
        timeline = deleted.json()
        assert len(timeline["scenes"]) == 1
        assert len(timeline["keyframes"]) == 2
        assert timeline["scenes"][0]["start_time"] == 0
        assert timeline["scenes"][0]["end_time"] == 9
