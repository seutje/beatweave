from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.jobs.worker import JobManager
from beatweave.keyframes.schemas import (
    GenerateKeyframeRequest,
    GenerateKeyframeResponse,
    KeyframeDetail,
    SelectVariantRequest,
    SelectVariantResponse,
    SetBlackFrameRequest,
)
from beatweave.keyframes.service import KeyframeService

router = APIRouter(prefix="/keyframes", tags=["keyframes"])


def service(request: Request) -> KeyframeService:
    database: Database = request.app.state.database
    return KeyframeService(database)


ServiceDep = Annotated[KeyframeService, Depends(service)]


@router.get("/{keyframe_id}", response_model=KeyframeDetail)
def detail(keyframe_id: str, keyframes: ServiceDep) -> KeyframeDetail:
    return keyframes.detail(keyframe_id)


@router.post(
    "/{keyframe_id}/generate",
    response_model=GenerateKeyframeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate(
    keyframe_id: str, body: GenerateKeyframeRequest, request: Request, keyframes: ServiceDep
) -> GenerateKeyframeResponse:
    job, project_path = keyframes.start_generation(keyframe_id, body)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    manager.submit(project_path, job.id, keyframes.execute)
    return GenerateKeyframeResponse(job=job)


@router.post("/{keyframe_id}/variants/{variant_id}/select", response_model=SelectVariantResponse)
def select_variant(
    keyframe_id: str, variant_id: str, body: SelectVariantRequest, keyframes: ServiceDep
) -> SelectVariantResponse:
    return keyframes.select_variant(keyframe_id, variant_id, body.confirm_stale_renders)


@router.delete("/{keyframe_id}/variants/{variant_id}", response_model=SelectVariantResponse)
def delete_variant(
    keyframe_id: str, variant_id: str, keyframes: ServiceDep
) -> SelectVariantResponse:
    return keyframes.delete_variant(keyframe_id, variant_id)


@router.post("/{keyframe_id}/black", response_model=SelectVariantResponse)
def set_black_frame(
    keyframe_id: str, body: SetBlackFrameRequest, keyframes: ServiceDep
) -> SelectVariantResponse:
    return keyframes.set_black_frame(keyframe_id, body.confirm_stale_renders)
