from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

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
    width: int = Field(default=1920, ge=256, le=2048)
    height: int = Field(default=1080, ge=256, le=2048)
    seed: int = Field(default=0, ge=0, le=18446744073709551615)
    steps: int | None = Field(default=None, ge=1, le=100)
    cfg: float | None = Field(default=None, ge=0, le=100)
    include_global_style_references: bool = True
    additional_reference_asset_ids: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "GenerateKeyframeRequest":
        if self.width % 8 or self.height % 8:
            raise ValueError("width and height must be multiples of 8")
        return self


class GenerateKeyframeResponse(BaseModel):
    job: Job


class SelectVariantRequest(BaseModel):
    confirm_stale_renders: bool = False


class SelectVariantResponse(BaseModel):
    detail: KeyframeDetail
    timeline: Timeline
    stale_scene_ids: list[str]
