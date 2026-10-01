from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.exports.schemas import ExportJobResponse, ExportReadiness, ExportRequest
from beatweave.exports.service import ExportService
from beatweave.jobs.worker import JobManager
from beatweave.media.process import MediaProcessRunner

router = APIRouter(prefix="/exports", tags=["exports"])


def service(request: Request) -> ExportService:
    database: Database = request.app.state.database
    settings = request.app.state.settings
    return ExportService(database, MediaProcessRunner(settings.ffmpeg_path, settings.ffprobe_path))


ServiceDep = Annotated[ExportService, Depends(service)]


@router.get("/readiness", response_model=ExportReadiness)
def readiness(exports: ServiceDep) -> ExportReadiness:
    return exports.readiness()


@router.post("", response_model=ExportJobResponse, status_code=status.HTTP_202_ACCEPTED)
def start_export(
    body: ExportRequest,
    request: Request,
    exports: ServiceDep,
) -> ExportJobResponse:
    job, project_path = exports.start(body)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    manager.submit(project_path, job.id)
    return ExportJobResponse(job=job)
