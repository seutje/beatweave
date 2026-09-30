from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.comfyui.schemas import (
    ComfyUIConfig,
    ComfyUIConfigUpdate,
    ComfyUIStatus,
    ImageRenderJobResponse,
    ImageRenderRequest,
)
from beatweave.comfyui.service import ComfyUIService
from beatweave.database import Database
from beatweave.jobs.worker import JobManager

router = APIRouter(prefix="/comfyui", tags=["comfyui"])


def service(request: Request) -> ComfyUIService:
    database: Database = request.app.state.database
    return ComfyUIService(database)


ComfyUIServiceDep = Annotated[ComfyUIService, Depends(service)]


@router.get("/config", response_model=ComfyUIConfig)
def get_config(comfyui: ComfyUIServiceDep) -> ComfyUIConfig:
    return comfyui.config()


@router.put("/config", response_model=ComfyUIConfig)
def update_config(body: ComfyUIConfigUpdate, comfyui: ComfyUIServiceDep) -> ComfyUIConfig:
    return comfyui.update_config(body)


@router.post("/test", response_model=ComfyUIStatus)
def test_connection(comfyui: ComfyUIServiceDep) -> ComfyUIStatus:
    return comfyui.status()


@router.post(
    "/renders", response_model=ImageRenderJobResponse, status_code=status.HTTP_202_ACCEPTED
)
def render_image(
    body: ImageRenderRequest,
    request: Request,
    comfyui: ComfyUIServiceDep,
) -> ImageRenderJobResponse:
    job, project_path = comfyui.start_render(body)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    manager.submit(project_path, job.id, comfyui.execute)
    return ImageRenderJobResponse(job=job)
