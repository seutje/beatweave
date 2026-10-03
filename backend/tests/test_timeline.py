from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.analysis.schemas import AnalysisJob
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


def test_scene_approval_can_be_toggled_and_persists(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    with client_for(database_path) as client:
        project_directory = create_project_with_audio(client, tmp_path / "projects")
        scene = client.post("/timeline/scenes", json={}).json()["scenes"][0]

        approved = client.patch(f"/timeline/scenes/{scene['id']}", json={"approved": True})
        assert approved.status_code == 200
        assert approved.json()["scenes"][0]["approved"] is True

    with client_for(database_path) as reopened_client:
        reopened_client.post("/projects/open", json={"path": str(project_directory)})
        restored = reopened_client.get("/timeline").json()["scenes"][0]
        assert restored["approved"] is True
        unapproved = reopened_client.patch(
            f"/timeline/scenes/{restored['id']}", json={"approved": False}
        )
        assert unapproved.json()["scenes"][0]["approved"] is False


def test_last_frame_conditioning_defaults_on_and_persists(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    with client_for(database_path) as client:
        project_directory = create_project_with_audio(client, tmp_path / "projects")
        scene = client.post("/timeline/scenes", json={}).json()["scenes"][0]
        assert scene["use_last_frame_conditioning"] is True

        updated = client.patch(
            f"/timeline/scenes/{scene['id']}",
            json={"use_last_frame_conditioning": False},
        )
        assert updated.status_code == 200
        assert updated.json()["scenes"][0]["use_last_frame_conditioning"] is False

    with client_for(database_path) as reopened:
        reopened.post("/projects/open", json={"path": str(project_directory)})
        scene = reopened.get("/timeline").json()["scenes"][0]
        assert scene["use_last_frame_conditioning"] is False


def test_persisted_undo_redo_and_history_invalidation(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    with client_for(database_path) as client:
        project_directory = create_project_with_audio(client, tmp_path / "projects", duration=10)
        initial = client.post("/timeline/scenes", json={}).json()
        first_scene_id = initial["scenes"][0]["id"]
        split = client.post("/timeline/scenes", json={"at_time": 3}).json()
        boundary_id = split["scenes"][0]["end_keyframe_id"]
        prompted = client.patch(
            f"/timeline/scenes/{first_scene_id}",
            json={"image_prompt": "luminous glass"},
        ).json()
        assert prompted["scenes"][0]["image_prompt"] == "luminous glass"
        moved = client.patch(f"/timeline/keyframes/{boundary_id}", json={"time": 4}).json()
        assert_shared_boundary(moved, 4)
        deleted = client.delete(f"/timeline/scenes/{moved['scenes'][1]['id']}").json()
        assert len(deleted["scenes"]) == 1

        restored_delete = client.post("/timeline/history/undo").json()
        assert_shared_boundary(restored_delete, 4)
        restored_move = client.post("/timeline/history/undo").json()
        assert_shared_boundary(restored_move, 3)
        restored_prompt = client.post("/timeline/history/undo").json()
        assert restored_prompt["scenes"][0]["image_prompt"] == ""

        redone_prompt = client.post("/timeline/history/redo").json()
        assert redone_prompt["scenes"][0]["image_prompt"] == "luminous glass"
        redone_move = client.post("/timeline/history/redo").json()
        assert_shared_boundary(redone_move, 4)
        redone_delete = client.post("/timeline/history/redo").json()
        assert len(redone_delete["scenes"]) == 1

        restored_again = client.post("/timeline/history/undo").json()
        boundary_id = assert_shared_boundary(restored_again, 4)
        divergent = client.patch(f"/timeline/keyframes/{boundary_id}", json={"time": 5}).json()
        assert_shared_boundary(divergent, 5)
        assert divergent["can_redo"] is False
        assert client.post("/timeline/history/redo").status_code == 409

    with client_for(database_path) as reopened:
        reopened.post("/projects/open", json={"path": str(project_directory)})
        timeline = reopened.get("/timeline").json()
        assert_shared_boundary(timeline, 5)
        assert reopened.post("/timeline/history/undo").status_code == 200


def test_job_updates_do_not_pollute_timeline_history(tmp_path: Path) -> None:
    with client_for(tmp_path / "application.db") as client:
        project_directory = create_project_with_audio(client, tmp_path / "projects")
        client.post("/timeline/scenes", json={})
        store = ProjectStore(project_directory)
        with store.connection() as connection:
            before = connection.execute("SELECT count(*) FROM timeline_edit_history").fetchone()[0]

        store.insert_analysis_job(
            AnalysisJob(
                id="unrelated-job",
                state="queued",
                progress=0,
                related_entity_id="audio-1",
                created_at=datetime.now(UTC),
            )
        )

        with store.connection() as connection:
            after = connection.execute("SELECT count(*) FROM timeline_edit_history").fetchone()[0]
        assert after == before
