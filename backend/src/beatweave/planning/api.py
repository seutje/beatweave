from typing import Annotated

from fastapi import APIRouter, Depends, Request

from beatweave.database import Database
from beatweave.llm.service import LLMService
from beatweave.planning.schemas import (
    GenerateVisualPlanRequest,
    RegenerateSceneRequest,
    VisualPlanningResult,
)
from beatweave.planning.visual import VisualPlanningService
from beatweave.project.service import ProjectService

router = APIRouter(prefix="/planning", tags=["planning"])


def service(request: Request) -> VisualPlanningService:
    database: Database = request.app.state.database
    return VisualPlanningService(ProjectService(database), LLMService(database).provider())


PlanningServiceDep = Annotated[VisualPlanningService, Depends(service)]


@router.post("/visual-plan", response_model=VisualPlanningResult)
def generate_visual_plan(
    body: GenerateVisualPlanRequest, planning: PlanningServiceDep
) -> VisualPlanningResult:
    return planning.generate(confirm_overwrite=body.confirm_overwrite)


@router.post("/scenes/{scene_id}/regenerate", response_model=VisualPlanningResult)
def regenerate_scene(
    scene_id: str, body: RegenerateSceneRequest, planning: PlanningServiceDep
) -> VisualPlanningResult:
    return planning.regenerate_scene(scene_id, confirm_overwrite=body.confirm_overwrite)
