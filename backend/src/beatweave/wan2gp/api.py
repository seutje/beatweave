from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.jobs.worker import JobManager
from beatweave.media.process import MediaProcessRunner
from beatweave.wan2gp.schemas import (
    VideoRenderJobResponse,
    VideoRenderRequest,
    Wan2GPConfig,
    Wan2GPConfigUpdate,
    Wan2GPStatus,
)
from beatweave.wan2gp.service import Wan2GPService

router = APIRouter(prefix="/wan2gp", tags=["wan2gp"])


def service(request: Request) -> Wan2GPService:
    database: Database = request.app.state.database
    settings = request.app.state.settings
    return Wan2GPService(
        database,
        MediaProcessRunner(settings.ffmpeg_path, settings.ffprobe_path),
    )


Wan2GPServiceDep = Annotated[Wan2GPService, Depends(service)]


@router.get("/config", response_model=Wan2GPConfig)
def get_config(wan2gp: Wan2GPServiceDep) -> Wan2GPConfig:
    return wan2gp.config()


@router.put("/config", response_model=Wan2GPConfig)
def update_config(body: Wan2GPConfigUpdate, wan2gp: Wan2GPServiceDep) -> Wan2GPConfig:
    return wan2gp.update_config(body)


@router.post("/test", response_model=Wan2GPStatus)
def test_installation(wan2gp: Wan2GPServiceDep) -> Wan2GPStatus:
    return wan2gp.status()


@router.post(
    "/renders", response_model=VideoRenderJobResponse, status_code=status.HTTP_202_ACCEPTED
)
def render_video(
    body: VideoRenderRequest,
    request: Request,
    wan2gp: Wan2GPServiceDep,
) -> VideoRenderJobResponse:
    job, project_path = wan2gp.start_render(body)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    manager.submit(project_path, job.id, wan2gp.execute)
    return VideoRenderJobResponse(job=job)
