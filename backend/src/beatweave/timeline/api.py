from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.project.service import ProjectService
from beatweave.timeline.schemas import CreateSceneRequest, MoveBoundaryRequest, Timeline
from beatweave.timeline.service import TimelineService

router = APIRouter(prefix="/timeline", tags=["timeline"])


def service(request: Request) -> TimelineService:
    database: Database = request.app.state.database
    return TimelineService(ProjectService(database))


TimelineServiceDep = Annotated[TimelineService, Depends(service)]


@router.get("", response_model=Timeline)
def current_timeline(timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.current()


@router.post("/scenes", response_model=Timeline, status_code=status.HTTP_201_CREATED)
def create_scene(body: CreateSceneRequest, timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.create_scene(body.at_time, body.beat_index)


@router.delete("/scenes/{scene_id}", response_model=Timeline)
def delete_scene(scene_id: str, timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.delete_scene(scene_id)


@router.patch("/keyframes/{keyframe_id}", response_model=Timeline)
def move_boundary(
    keyframe_id: str,
    body: MoveBoundaryRequest,
    timeline_service: TimelineServiceDep,
) -> Timeline:
    return timeline_service.move_boundary(keyframe_id, body.time, body.beat_index)
