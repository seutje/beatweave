import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.jobs.events import EventBroker
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobManager
from beatweave.main import create_app
from beatweave.project.store import ProjectStore, migration_7


class RecordingEvents(EventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.published.append((event_type, payload))
        super().publish(event_type, payload)


def test_job_migration_preserves_existing_analysis_jobs() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE project_metadata (id TEXT PRIMARY KEY);
        INSERT INTO project_metadata (id) VALUES ('project-1');
        CREATE TABLE analysis_jobs (
            id TEXT PRIMARY KEY, type TEXT, state TEXT, progress REAL,
            related_entity_id TEXT, output_json TEXT, error_json TEXT,
            created_at TEXT, started_at TEXT, completed_at TEXT
        );
        INSERT INTO analysis_jobs VALUES (
            'job-1', 'audio_analysis', 'failed', 0.5, 'asset-1',
            '{"partial": true}', '{"code": "old_failure", "message": "kept"}',
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00',
            '2026-01-01T00:00:02+00:00'
        );
        """
    )

    migration_7(connection)
    row = connection.execute("SELECT * FROM jobs WHERE id = 'job-1'").fetchone()

    assert row["project_id"] == "project-1"
    assert row["related_entity_type"] == "asset"
    assert row["output_json"] == '{"partial": true}'
    assert row["error_json"] == '{"code": "old_failure", "message": "kept"}'


def create_project(tmp_path: Path) -> tuple[Path, str]:
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    parent = tmp_path / "projects"
    parent.mkdir()
    with TestClient(app) as client:
        project = client.post(
            "/projects", json={"name": "Jobs Project", "parent_directory": str(parent)}
        ).json()
    return Path(project["path"]), project["id"]


def make_job(project_id: str, state: JobState = JobState.QUEUED) -> Job:
    now = datetime.now(UTC)
    return Job(
        id=str(uuid4()),
        type=JobType.PROXY_GENERATION,
        state=state,
        progress=0.4 if state == JobState.RUNNING else 0,
        project_id=project_id,
        related_entity_type="asset",
        related_entity_id="asset-1",
        backend="test-backend",
        output={"partial_path": "cache/partial.bin"} if state == JobState.RUNNING else {},
        created_at=now,
        updated_at=now,
        started_at=now if state == JobState.RUNNING else None,
    )


def wait_for_state(store: ProjectStore, job_id: str, state: JobState) -> Job:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = store.get_job(job_id)
        if job is not None and job.state == state:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {state.value}")


def test_worker_persists_transitions_metadata_and_events(tmp_path: Path) -> None:
    project_path, project_id = create_project(tmp_path)
    store = ProjectStore(project_path)
    job = make_job(project_id)
    store.insert_job(job)
    events = RecordingEvents()
    manager = JobManager(events)

    def handler(context):
        assert store.get_job(job.id).state == JobState.RUNNING
        context.report(0.6, {"preview": "cache/preview.mp4"})
        return {"asset_id": "output-1"}

    manager.register(JobType.PROXY_GENERATION, lambda _: handler)
    manager.start()
    try:
        manager.publish_created(job)
        manager.submit(project_path, job.id)
        completed = wait_for_state(store, job.id, JobState.COMPLETE)
    finally:
        manager.stop()

    assert completed.progress == 1
    assert completed.backend == "test-backend"
    assert completed.related_entity_id == "asset-1"
    assert completed.output == {
        "preview": "cache/preview.mp4",
        "asset_id": "output-1",
    }
    assert completed.started_at is not None
    assert completed.completed_at is not None
    assert [event_type for event_type, _ in events.published] == [
        "job-created",
        "job-progress",
        "job-progress",
        "job-progress",
        "job-complete",
    ]


def test_failure_and_cancellation_details_remain_inspectable(tmp_path: Path) -> None:
    project_path, project_id = create_project(tmp_path)
    store = ProjectStore(project_path)
    failed_job = make_job(project_id)
    cancelled_job = make_job(project_id)
    store.insert_job(failed_job)
    store.insert_job(cancelled_job)
    events = RecordingEvents()
    manager = JobManager(events)

    def fail(_):
        raise RuntimeError("synthetic render failure")

    manager.register(JobType.PROXY_GENERATION, lambda _: fail)
    cancelled = manager.cancel(project_path, cancelled_job.id)
    assert cancelled.state == JobState.CANCELLED
    assert cancelled.cancellation_requested_at is not None

    manager.start()
    try:
        manager.submit(project_path, failed_job.id)
        failed = wait_for_state(store, failed_job.id, JobState.FAILED)
    finally:
        manager.stop()

    assert failed.error is not None
    assert failed.error.code == "job_failed"
    assert failed.error.message == "synthetic render failure"
    assert store.get_job(failed_job.id).error == failed.error
    assert any(event_type == "job-failed" for event_type, _ in events.published)


def test_running_job_honors_cooperative_cancellation(tmp_path: Path) -> None:
    project_path, project_id = create_project(tmp_path)
    store = ProjectStore(project_path)
    job = make_job(project_id)
    store.insert_job(job)
    entered = Event()
    release = Event()
    manager = JobManager(RecordingEvents())

    def handler(context):
        entered.set()
        assert release.wait(timeout=3)
        context.check_cancelled()
        return {"unexpected": True}

    manager.register(JobType.PROXY_GENERATION, lambda _: handler)
    manager.start()
    try:
        manager.submit(project_path, job.id)
        assert entered.wait(timeout=3)
        requested = manager.cancel(project_path, job.id)
        assert requested.cancellation_requested_at is not None
        release.set()
        cancelled = wait_for_state(store, job.id, JobState.CANCELLED)
    finally:
        release.set()
        manager.stop()

    assert cancelled.output == {}
    assert cancelled.completed_at is not None


def test_reconcile_requeues_interrupted_jobs_and_preserves_partial_output(
    tmp_path: Path,
) -> None:
    project_path, project_id = create_project(tmp_path)
    store = ProjectStore(project_path)
    interrupted = make_job(project_id, JobState.RUNNING)
    store.insert_job(interrupted)
    manager = JobManager(RecordingEvents())
    manager.register(
        JobType.PROXY_GENERATION,
        lambda _: lambda context: {"asset_id": "recovered-output"},
    )
    manager.start()
    try:
        recovered = manager.reconcile(project_path)
        assert recovered[0].output["recovered_after_restart"] is True
        completed = wait_for_state(store, interrupted.id, JobState.COMPLETE)
    finally:
        manager.stop()

    assert completed.output == {
        "partial_path": "cache/partial.bin",
        "recovered_after_restart": True,
        "asset_id": "recovered-output",
    }


def test_jobs_api_lists_and_returns_persisted_jobs(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    app = create_app(Settings(database_path=database_path))
    parent = tmp_path / "projects"
    parent.mkdir()
    with TestClient(app) as client:
        project = client.post(
            "/projects", json={"name": "API Jobs", "parent_directory": str(parent)}
        ).json()
        store = ProjectStore(Path(project["path"]))
        job = make_job(project["id"])
        store.insert_job(job)

        listed = client.get("/jobs", params={"state": "queued"})
        fetched = client.get(f"/jobs/{job.id}")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [job.id]
    assert fetched.json()["backend"] == "test-backend"
