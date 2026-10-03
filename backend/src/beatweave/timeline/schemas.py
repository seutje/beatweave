from datetime import datetime

from pydantic import BaseModel, Field


class Keyframe(BaseModel):
    id: str
    time: float = Field(ge=0)
    prompt: str = ""
    selected_variant_id: str | None = None
    selected_variant_asset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class Scene(BaseModel):
    id: str
    position: int = Field(ge=0)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    start_beat_index: int | None = Field(default=None, ge=0)
    end_beat_index: int | None = Field(default=None, ge=0)
    start_keyframe_id: str
    end_keyframe_id: str
    concept: str = ""
    image_prompt: str = ""
    video_prompt: str = ""
    visual_energy: float = Field(default=0, ge=0, le=1)
    motion_energy: float = Field(default=0, ge=0, le=1)
    selected_video_take_id: str | None = None
    selected_video_take_stale: bool = False
    approved: bool = False
    use_last_frame_conditioning: bool = True
    created_at: datetime
    updated_at: datetime


class Timeline(BaseModel):
    duration_seconds: float = Field(ge=0)
    scenes: list[Scene]
    keyframes: list[Keyframe]
    can_undo: bool = False
    can_redo: bool = False


class CreateSceneRequest(BaseModel):
    at_time: float | None = Field(default=None, ge=0)
    beat_index: int | None = Field(default=None, ge=0)


class MoveBoundaryRequest(BaseModel):
    time: float = Field(ge=0)
    beat_index: int | None = Field(default=None, ge=0)


class UpdateSceneRequest(BaseModel):
    concept: str | None = Field(default=None, max_length=10_000)
    image_prompt: str | None = Field(default=None, max_length=20_000)
    video_prompt: str | None = Field(default=None, max_length=20_000)
    approved: bool | None = None
    use_last_frame_conditioning: bool | None = None


class SuggestLayoutRequest(BaseModel):
    preferred_length_seconds: float = Field(default=6, ge=1, le=30)
    minimum_length_seconds: float = Field(default=2, ge=0.25, le=30)


class ProposedBoundary(BaseModel):
    time: float = Field(ge=0)
    beat_index: int | None = Field(default=None, ge=0)
    reason: str
    energy_change: float = Field(default=0, ge=0, le=1)


class LayoutProposal(BaseModel):
    duration_seconds: float = Field(gt=0)
    preferred_length_seconds: float = Field(gt=0)
    minimum_length_seconds: float = Field(gt=0)
    maximum_length_seconds: float = Field(gt=0)
    default_preferred_lengths: list[float]
    boundaries: list[ProposedBoundary]


class ApplyLayoutRequest(BaseModel):
    boundaries: list[ProposedBoundary] = Field(min_length=2)
