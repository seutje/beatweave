from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.project.service import ProjectService
from beatweave.timeline.schemas import (
    ApplyLayoutRequest,
    CreateSceneRequest,
    LayoutProposal,
    MoveBoundaryRequest,
    SuggestLayoutRequest,
    Timeline,
    UpdateSceneRequest,
)
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


@router.patch("/scenes/{scene_id}", response_model=Timeline)
def update_scene(
    scene_id: str, body: UpdateSceneRequest, timeline_service: TimelineServiceDep
) -> Timeline:
    return timeline_service.update_scene(
        scene_id,
        concept=body.concept,
        image_prompt=body.image_prompt,
        video_prompt=body.video_prompt,
        approved=body.approved,
    )


@router.patch("/keyframes/{keyframe_id}", response_model=Timeline)
def move_boundary(
    keyframe_id: str,
    body: MoveBoundaryRequest,
    timeline_service: TimelineServiceDep,
) -> Timeline:
    return timeline_service.move_boundary(keyframe_id, body.time, body.beat_index)


@router.post("/layout/suggest", response_model=LayoutProposal)
def suggest_layout(
    body: SuggestLayoutRequest, timeline_service: TimelineServiceDep
) -> LayoutProposal:
    return timeline_service.suggest_layout(
        body.preferred_length_seconds, body.minimum_length_seconds
    )


@router.post("/layout/apply", response_model=Timeline)
def apply_layout(body: ApplyLayoutRequest, timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.apply_layout(body.boundaries)


@router.post("/layout/undo", response_model=Timeline)
def undo_layout(timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.undo_layout()


@router.post("/history/undo", response_model=Timeline)
def undo(timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.undo()


@router.post("/history/redo", response_model=Timeline)
def redo(timeline_service: TimelineServiceDep) -> Timeline:
    return timeline_service.redo()
