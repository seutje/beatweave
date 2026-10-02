from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from beatweave.comfyui.schemas import ImageQualityMode, ReferenceConditioningMode
from beatweave.jobs.schemas import Job
from beatweave.project.schemas import AssetMetadata
from beatweave.timeline.schemas import Keyframe, Timeline


class KeyframeVariant(BaseModel):
    id: str
    keyframe_id: str
    asset_id: str
    source_job_id: str
    prompt: str
    negative_prompt: str = ""
    backend: str
    backend_settings: dict[str, Any] = Field(default_factory=dict)
    source_asset_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class KeyframeVariantView(KeyframeVariant):
    asset: AssetMetadata
    asset_path: str


class KeyframeDetail(BaseModel):
    keyframe: Keyframe
    variants: list[KeyframeVariantView]
    render_jobs: list[Job]
    adjacent_scene_ids: list[str]
    affected_render_scene_ids: list[str]


class GenerateKeyframeRequest(BaseModel):
    prompt: str | None = Field(default=None, min_length=1, max_length=16000)
    negative_prompt: str = Field(default="", max_length=8000)
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)
    steps: int | None = Field(default=None, ge=1, le=100)
    cfg: float | None = Field(default=None, ge=0, le=100)
    include_global_style_references: bool = True
    include_previous_keyframe: bool = True
    additional_reference_asset_ids: list[str] = Field(default_factory=list, max_length=15)
    reference_mode: ReferenceConditioningMode = ReferenceConditioningMode.SEMANTIC
    quality_mode: ImageQualityMode = ImageQualityMode.PREVIEW

    @model_validator(mode="after")
    def validate_dimensions(self) -> "GenerateKeyframeRequest":
        if (self.width is not None and self.width % 8) or (
            self.height is not None and self.height % 8
        ):
            raise ValueError("width and height must be multiples of 8")
        if (self.width is None) != (self.height is None):
            raise ValueError("width and height overrides must be supplied together")
        return self


class GenerateKeyframeResponse(BaseModel):
    job: Job


class SelectVariantRequest(BaseModel):
    confirm_stale_renders: bool = False


class SetBlackFrameRequest(BaseModel):
    confirm_stale_renders: bool = False


class SelectVariantResponse(BaseModel):
    detail: KeyframeDetail
    timeline: Timeline
    stale_scene_ids: list[str]
