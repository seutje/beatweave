from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import CancelJobResponse, Job, JobState, RetryJobResponse
from beatweave.jobs.worker import JobManager
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


def current_store(request: Request) -> ProjectStore:
    project = ProjectService(request.app.state.database).current()
    if project is None:
        raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
    return ProjectStore(project.path)


StoreDep = Annotated[ProjectStore, Depends(current_store)]


@router.get("", response_model=list[Job])
def list_jobs(
    store: StoreDep, state: Annotated[list[JobState] | None, Query()] = None
) -> list[Job]:
    return store.list_jobs(states=set(state) if state else None)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, store: StoreDep) -> Job:
    job = store.get_job(job_id)
    if job is None:
        raise BeatweaveError("job_not_found", "The job was not found.", status_code=404)
    return job


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
def cancel_job(job_id: str, request: Request, store: StoreDep) -> CancelJobResponse:
    manager: JobManager = request.app.state.job_manager
    return CancelJobResponse(job=manager.cancel(store.directory, job_id))


@router.post("/{job_id}/retry", response_model=RetryJobResponse)
def retry_job(job_id: str, request: Request, store: StoreDep) -> RetryJobResponse:
    manager: JobManager = request.app.state.job_manager
    return RetryJobResponse(job=manager.retry(store.directory, job_id))
