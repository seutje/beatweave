from datetime import datetime

from pydantic import BaseModel, Field


class Keyframe(BaseModel):
    id: str
    time: float = Field(ge=0)
    prompt: str = ""
    selected_variant_id: str | None = None
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
    created_at: datetime
    updated_at: datetime


class Timeline(BaseModel):
    duration_seconds: float = Field(ge=0)
    scenes: list[Scene]
    keyframes: list[Keyframe]


class CreateSceneRequest(BaseModel):
    at_time: float | None = Field(default=None, ge=0)
    beat_index: int | None = Field(default=None, ge=0)


class MoveBoundaryRequest(BaseModel):
    time: float = Field(ge=0)
    beat_index: int | None = Field(default=None, ge=0)
