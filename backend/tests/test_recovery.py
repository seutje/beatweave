import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.jobs.schemas import Job, JobError, JobState, JobType
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    MIGRATION_MARKER_NAME,
    ProjectStore,
)


def create_project(client: TestClient, tmp_path: Path) -> dict:
    parent = tmp_path / "projects"
    parent.mkdir(exist_ok=True)
    response = client.post("/projects", json={"name": "Recovery", "parent_directory": str(parent)})
    assert response.status_code == 201
    return response.json()


def test_backup_integrity_missing_media_and_exact_relink(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        project = create_project(client, tmp_path)
        store = ProjectStore(project["path"])
        source = tmp_path / "original.bin"
        source.write_bytes(b"durable media")
        managed = store.directory / "renders" / "take.bin"
        managed.write_bytes(source.read_bytes())
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_video",
            relative_path="renders/take.bin",
            filename="take.bin",
            sha256=("eb0e05f25067449da46947d2aafc765781c540940242b7e1d3ecad88da9cf961"),
            size_bytes=13,
            created_at=datetime.now(UTC),
        )
        # Use the implementation hash so this fixture remains obviously exact.
        from beatweave.project.store import file_sha256

        asset.sha256 = file_sha256(source)
        store.insert_asset(asset)

        healthy = client.get("/projects/integrity").json()
        assert healthy["ok"] is True
        backup = client.post("/projects/backup")
        assert backup.status_code == 200
        backup_path = Path(backup.json()["path"])
        assert backup_path.is_file()
        with sqlite3.connect(backup_path) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        managed.write_bytes(b"durable mediX")
        altered = client.get("/projects/integrity?verify_hashes=true").json()
        assert any(issue["code"] == "asset_hash_mismatch" for issue in altered["issues"])
        managed.write_bytes(source.read_bytes())

        managed.unlink()
        damaged = client.get("/projects/integrity").json()
        issue = next(item for item in damaged["issues"] if item["code"] == "asset_file_missing")
        assert issue["asset_id"] == asset.id

        mismatch = tmp_path / "wrong.bin"
        mismatch.write_bytes(b"wrong")
        rejected = client.post(f"/projects/assets/{asset.id}/relink", json={"path": str(mismatch)})
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "relink_hash_mismatch"

        relinked = client.post(f"/projects/assets/{asset.id}/relink", json={"path": str(source)})
        assert relinked.status_code == 200
        assert managed.read_bytes() == b"durable media"
        assert client.get("/projects/integrity").json()["ok"] is True


def test_incomplete_migration_is_detected_and_upgrade_creates_backup(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        project = create_project(client, tmp_path)
        client.post("/projects/close")
    store = ProjectStore(project["path"])
    store.migration_marker_path.write_text(
        json.dumps({"from_version": 8, "target_version": 9}), encoding="utf-8"
    )

    with TestClient(create_app(settings)) as client:
        interrupted = client.post("/projects/open", json={"path": project["path"]})
        assert interrupted.status_code == 409
        assert interrupted.json()["error"]["code"] == "incomplete_project_migration"

    store.migration_marker_path.unlink()
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("DROP TABLE video_takes")
        connection.execute("PRAGMA user_version = 8")

    with TestClient(create_app(settings)) as client:
        migrated = client.post("/projects/open", json={"path": project["path"]})
        assert migrated.status_code == 200
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            CURRENT_PROJECT_SCHEMA_VERSION
        )
    assert list((store.directory / "backups").glob("*pre-migration.db"))
    assert not (store.directory / MIGRATION_MARKER_NAME).exists()


def test_failed_job_retry_preserves_original_and_logs_are_exportable(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        project = create_project(client, tmp_path)
        now = datetime.now(UTC)
        failed = Job(
            id=str(uuid4()),
            type=JobType.AUDIO_ANALYSIS,
            state=JobState.FAILED,
            progress=0.25,
            project_id=project["id"],
            related_entity_type="asset",
            related_entity_id="missing-asset",
            backend="beat-this",
            output={"partial": True},
            error=JobError(code="forced_failure", message="forced render failure"),
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        store = ProjectStore(project["path"])
        store.insert_job(failed)

        response = client.post(f"/jobs/{failed.id}/retry")
        assert response.status_code == 200
        retry = response.json()["job"]
        assert retry["id"] != failed.id
        assert retry["output"]["retry_of_job_id"] == failed.id
        assert store.get_job(failed.id).state == JobState.FAILED

        logs = client.get("/diagnostics/logs")
        assert logs.status_code == 200
        assert logs.json()["entries"]
        exported = client.get("/diagnostics/logs/export")
        assert exported.status_code == 200
        assert "application/x-ndjson" in exported.headers["content-type"]
