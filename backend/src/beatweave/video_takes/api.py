from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.jobs.worker import JobManager
from beatweave.video_takes.schemas import (
    RenderSceneRequest,
    RenderSceneResponse,
    SceneVideoTakes,
    SelectVideoTakeResponse,
)
from beatweave.video_takes.service import VideoTakeService

router = APIRouter(prefix="/scenes", tags=["video-takes"])


def service(request: Request) -> VideoTakeService:
    database: Database = request.app.state.database
    return VideoTakeService(database)


ServiceDep = Annotated[VideoTakeService, Depends(service)]


@router.get("/{scene_id}/takes", response_model=SceneVideoTakes)
def detail(scene_id: str, video_takes: ServiceDep) -> SceneVideoTakes:
    return video_takes.detail(scene_id)


@router.post(
    "/{scene_id}/renders",
    response_model=RenderSceneResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def render(
    scene_id: str,
    body: RenderSceneRequest,
    request: Request,
    video_takes: ServiceDep,
) -> RenderSceneResponse:
    job, project_path = video_takes.start_render(scene_id, body)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    manager.submit(project_path, job.id)
    return RenderSceneResponse(job=job)


@router.post("/{scene_id}/takes/{take_id}/select", response_model=SelectVideoTakeResponse)
def select(scene_id: str, take_id: str, video_takes: ServiceDep) -> SelectVideoTakeResponse:
    return SelectVideoTakeResponse(detail=video_takes.select(scene_id, take_id))


@router.delete("/{scene_id}/takes/{take_id}", response_model=SceneVideoTakes)
def delete(scene_id: str, take_id: str, video_takes: ServiceDep) -> SceneVideoTakes:
    return video_takes.delete(scene_id, take_id)
