from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from beatweave.jobs.schemas import Job


class VideoQualityMode(StrEnum):
    PREVIEW = "preview"
    FINAL = "final"


class VideoQualityProfile(BaseModel):
    resolution: str = Field(pattern=r"^\d+x\d+$")
    inference_steps: int = Field(ge=1, le=100)


class LTX23DistilledProfile(BaseModel):
    name: str = "ltx-2.3-distilled-1.1"
    model_type: str = "ltx2_22B_distilled_1_1"
    settings_version: float = 2.73
    preview: VideoQualityProfile = Field(
        default_factory=lambda: VideoQualityProfile(resolution="768x448", inference_steps=6)
    )
    final: VideoQualityProfile = Field(
        default_factory=lambda: VideoQualityProfile(resolution="1920x1088", inference_steps=8)
    )
    default_frame_rate: int = Field(default=24, ge=1, le=60)
    minimum_frames: int = Field(default=17, ge=1)
    frame_step: int = Field(default=8, ge=1)


class AudioReactiveLoraProfile(BaseModel):
    name: str = "ltx-2.3-audio-reactive-v2"
    filename: str = "ltx2.3_audio_reactive_lora_v2.safetensors"
    default_multiplier: float = Field(default=1, ge=-10, le=10)
    trigger_phrase: str = ""


class Wan2GPConfig(BaseModel):
    base_url: str = "http://localhost:7860"
    request_timeout_seconds: float = Field(default=30, ge=1, le=600)
    render_timeout_seconds: float = Field(default=7200, ge=10, le=86400)
    poll_interval_seconds: float = Field(default=0.5, ge=0.1, le=10)
    profile: LTX23DistilledProfile = Field(default_factory=LTX23DistilledProfile)
    audio_reactive_profile: AudioReactiveLoraProfile = Field(
        default_factory=AudioReactiveLoraProfile
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an HTTP or HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, a query, or a fragment")
        return normalized


class Wan2GPConfigUpdate(Wan2GPConfig):
    pass


class Wan2GPStatus(BaseModel):
    available: bool
    profile_ready: bool = False
    message: str
    version: str | None = None
    api_endpoints: list[str] = Field(default_factory=list)


class MotionParameters(BaseModel):
    amplitude: float = Field(default=1, ge=0, le=4)
    seed: int = Field(default=-1, ge=-1, le=2**63 - 1)


class AudioReactiveLoraParameters(BaseModel):
    enabled: bool = True
    multiplier: float | None = Field(default=None, ge=-10, le=10)
    trigger: str | None = Field(default=None, max_length=500)


class VideoRenderRequest(BaseModel):
    scene_id: str = Field(min_length=1)
    start_keyframe_asset_id: str = Field(min_length=1)
    end_keyframe_asset_id: str = Field(min_length=1)
    audio_asset_id: str = Field(min_length=1)
    audio_start_seconds: float = Field(ge=0)
    prompt: str = Field(min_length=1, max_length=20000)
    duration_seconds: float = Field(gt=0, le=120)
    frame_rate: int = Field(default=24, ge=1, le=60)
    model_profile: str = "ltx-2.3-distilled-1.1"
    motion: MotionParameters = Field(default_factory=MotionParameters)
    audio_reactive_lora: AudioReactiveLoraParameters = Field(
        default_factory=AudioReactiveLoraParameters
    )
    quality_mode: VideoQualityMode = VideoQualityMode.PREVIEW

    @model_validator(mode="after")
    def distinct_boundary_assets(self) -> "VideoRenderRequest":
        if self.start_keyframe_asset_id == self.end_keyframe_asset_id:
            raise ValueError("start and end keyframe assets must be different")
        return self


class VideoRenderJobResponse(BaseModel):
    job: Job


class Wan2GPExecutionResult(BaseModel):
    output_path: Path
    stdout_tail: str = ""
