import logging
import queue
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beatweave.errors import BeatweaveError
from beatweave.jobs.events import EventBroker
from beatweave.jobs.schemas import TERMINAL_JOB_STATES, Job, JobError, JobState, JobType
from beatweave.project.store import ProjectStore

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, manager: "JobManager", project_path: Path, job_id: str) -> None:
        self.manager = manager
        self.project_path = project_path
        self.job_id = job_id

    def report(self, progress: float, output: dict[str, Any] | None = None) -> Job:
        self.check_cancelled()
        return self.manager._transition(
            self.project_path,
            self.job_id,
            JobState.RUNNING,
            progress=progress,
            output=output,
            event_type="job-progress",
        )

    def check_cancelled(self) -> None:
        job = ProjectStore(self.project_path).get_job(self.job_id)
        if job is None or job.cancellation_requested_at is not None:
            raise JobCancelled


JobHandler = Callable[[JobContext], dict[str, Any] | None]


class JobManager:
    def __init__(self, events: EventBroker) -> None:
        self.events = events
        self._handlers: dict[JobType, Callable[[Path], JobHandler]] = {}
        self._overrides: dict[tuple[str, str], JobHandler] = {}
        self._pending: queue.Queue[tuple[Path, str] | None] = queue.Queue()
        self._scheduled: set[tuple[str, str]] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def register(self, job_type: JobType, factory: Callable[[Path], JobHandler]) -> None:
        self._handlers[job_type] = factory

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._work, name="beatweave-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._pending.put(None)
        self._thread.join(timeout=10)
        self._thread = None

    def submit(
        self, project_path: str | Path, job_id: str, handler: JobHandler | None = None
    ) -> None:
        path = Path(project_path).resolve()
        key = (str(path), job_id)
        with self._lock:
            if key in self._scheduled:
                return
            if handler is not None:
                self._overrides[key] = handler
            self._scheduled.add(key)
        self._pending.put((path, job_id))

    def publish_created(self, job: Job) -> None:
        self.events.publish("job-created", job.model_dump(mode="json"))
        if job.state == JobState.COMPLETE:
            self.events.publish("job-complete", job.model_dump(mode="json"))

    def reconcile(self, project_path: str | Path) -> list[Job]:
        path = Path(project_path).resolve()
        store = ProjectStore(path)
        recovered: list[Job] = []
        for job in store.list_jobs(states={JobState.QUEUED, JobState.PREPARING, JobState.RUNNING}):
            if job.state in {JobState.PREPARING, JobState.RUNNING}:
                recovery = {**job.output, "recovered_after_restart": True}
                job = self._transition(
                    path,
                    job.id,
                    JobState.QUEUED,
                    progress=job.progress,
                    output=recovery,
                    clear_started=True,
                    event_type="job-progress",
                )
            recovered.append(job)
            self.submit(path, job.id)
        return recovered

    def cancel(self, project_path: str | Path, job_id: str) -> Job:
        path = Path(project_path).resolve()
        store = ProjectStore(path)
        job = store.get_job(job_id)
        if job is None:
            raise BeatweaveError("job_not_found", "The job was not found.", status_code=404)
        if job.state in TERMINAL_JOB_STATES:
            return job
        now = datetime.now(UTC)
        job.cancellation_requested_at = now
        job.updated_at = now
        if job.state == JobState.QUEUED:
            job.state = JobState.CANCELLED
            job.completed_at = now
        store.update_job(job)
        event_type = "job-complete" if job.state == JobState.CANCELLED else "job-progress"
        self.events.publish(event_type, job.model_dump(mode="json"))
        return job

    def _work(self) -> None:
        while True:
            item = self._pending.get()
            if item is None:
                return
            path, job_id = item
            key = (str(path), job_id)
            try:
                self._execute(path, job_id, self._overrides.pop(key, None))
            finally:
                with self._lock:
                    self._scheduled.discard(key)

    def _execute(self, path: Path, job_id: str, handler: JobHandler | None) -> None:
        store = ProjectStore(path)
        job = store.get_job(job_id)
        if job is None or job.state in TERMINAL_JOB_STATES:
            return
        try:
            if job.cancellation_requested_at is not None:
                raise JobCancelled
            self._transition(path, job_id, JobState.PREPARING, progress=job.progress)
            resolved = handler
            if resolved is None:
                factory = self._handlers.get(job.type)
                if factory is None:
                    raise BeatweaveError(
                        "job_handler_missing", f"No handler is registered for {job.type.value}."
                    )
                resolved = factory(path)
            self._transition(path, job_id, JobState.RUNNING, progress=max(job.progress, 0.01))
            output = resolved(JobContext(self, path, job_id)) or {}
            self._transition(
                path,
                job_id,
                JobState.COMPLETE,
                progress=1,
                output=output,
                completed=True,
                event_type="job-complete",
            )
        except JobCancelled:
            self._transition(
                path,
                job_id,
                JobState.CANCELLED,
                completed=True,
                event_type="job-complete",
            )
        except Exception as error:
            logger.exception("Job %s failed", job_id)
            details = getattr(error, "details", None)
            self._transition(
                path,
                job_id,
                JobState.FAILED,
                error={
                    "code": getattr(error, "code", "job_failed"),
                    "message": getattr(error, "message", str(error)),
                    "details": details,
                },
                completed=True,
                event_type="job-failed",
            )

    def _transition(
        self,
        project_path: Path,
        job_id: str,
        state: JobState,
        *,
        progress: float | None = None,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        completed: bool = False,
        clear_started: bool = False,
        event_type: str = "job-progress",
    ) -> Job:
        store = ProjectStore(project_path)
        job = store.get_job(job_id)
        if job is None:
            raise JobCancelled
        now = datetime.now(UTC)
        job.state = state
        job.updated_at = now
        if progress is not None:
            job.progress = progress
        if output is not None:
            job.output = {**job.output, **output}
        if error is not None:
            job.error = JobError.model_validate(error)
        if state == JobState.RUNNING and job.started_at is None:
            job.started_at = now
        if clear_started:
            job.started_at = None
        if completed:
            job.completed_at = now
        store.update_job(job)
        self.events.publish(event_type, job.model_dump(mode="json"))
        return job
