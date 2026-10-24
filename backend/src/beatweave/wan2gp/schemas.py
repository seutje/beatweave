from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from beatweave.jobs.schemas import Job


class VideoQualityMode(StrEnum):
    PREVIEW = "preview"
    FINAL = "final"


class VideoQualityProfile(BaseModel):
    resolution: str = Field(pattern=r"^\d+x\d+$")
    inference_steps: int = Field(ge=1, le=100)


class LTX23DistilledProfile(BaseModel):
    name: Literal["ltx-2.3-distilled-1.1"] = "ltx-2.3-distilled-1.1"
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


class MiniMaxH3Profile(BaseModel):
    name: Literal["minimax-h3-fl2va-33b"] = "minimax-h3-fl2va-33b"
    model_type: Literal["minimax_h3_fl2va"] = "minimax_h3_fl2va"
    settings_version: float = 2.76
    preview: VideoQualityProfile = Field(
        default_factory=lambda: VideoQualityProfile(resolution="832x480", inference_steps=20)
    )
    final: VideoQualityProfile = Field(
        default_factory=lambda: VideoQualityProfile(resolution="1920x1088", inference_steps=20)
    )
    default_frame_rate: Literal[24] = 24
    minimum_frames: Literal[107] = 107
    frame_step: Literal[17] = 17
    sample_solver: Literal["euler", "res_multistep", "ralston_2s"] = "euler"
    flow_shift: float = Field(default=12, ge=1, le=25)

    @field_validator("preview", "final")
    @classmethod
    def validate_dimensions(cls, value: VideoQualityProfile) -> VideoQualityProfile:
        width, height = (int(part) for part in value.resolution.split("x"))
        if min(width, height) < 32 or width % 32 or height % 32:
            raise ValueError("H3 video dimensions must be positive multiples of 32")
        if width * height > 2048 * 2048:
            raise ValueError("H3 single-phase resolution budget is at most 2048x2048 pixels")
        return value


class MiniMaxH3PrunedProfile(MiniMaxH3Profile):
    name: Literal["minimax-h3-fl2va-pruned-20b"] = "minimax-h3-fl2va-pruned-20b"
    model_type: Literal["minimax_h3_fl2va_pruned"] = "minimax_h3_fl2va_pruned"


class PDDVideoQualityProfile(VideoQualityProfile):
    inference_steps: Literal[8] = 8


class MiniMaxH3PrunedPDDProfile(MiniMaxH3PrunedProfile):
    name: Literal["minimax-h3-fl2va-pruned-20b-pdd"] = "minimax-h3-fl2va-pruned-20b-pdd"
    model_type: Literal["minimax_h3_fl2va_pruned_pdd"] = "minimax_h3_fl2va_pruned_pdd"
    settings_version: float = 2.81
    preview: PDDVideoQualityProfile = Field(
        default_factory=lambda: PDDVideoQualityProfile(resolution="832x480")
    )
    final: PDDVideoQualityProfile = Field(
        default_factory=lambda: PDDVideoQualityProfile(resolution="1920x1088")
    )
    sample_solver: Literal["euler"] = "euler"


VideoModelProfile = Annotated[
    LTX23DistilledProfile | MiniMaxH3Profile | MiniMaxH3PrunedProfile | MiniMaxH3PrunedPDDProfile,
    Field(discriminator="name"),
]


def default_video_profiles() -> dict[str, VideoModelProfile]:
    return {
        profile.name: profile
        for profile in (
            LTX23DistilledProfile(),
            MiniMaxH3Profile(),
            MiniMaxH3PrunedProfile(),
            MiniMaxH3PrunedPDDProfile(),
        )
    }


DEFAULT_AUDIO_REACTIVE_LORA_URL = (
    "https://huggingface.co/fal/ltx2.3-audio-reactive-lora/resolve/main/"
    "ltx2.3_audio_reactive_lora_v2.safetensors"
)


class AudioReactiveLoraProfile(BaseModel):
    name: str = "ltx-2.3-audio-reactive-v2"
    enabled: bool = True
    filename: str = DEFAULT_AUDIO_REACTIVE_LORA_URL
    default_multiplier: float = Field(default=1, ge=-10, le=10)
    trigger_phrase: str = ""

    @field_validator("filename")
    @classmethod
    def upgrade_default_filename(cls, value: str) -> str:
        # Also covers saved job configurations on retry. Custom locations are preserved.
        if value == "ltx2.3_audio_reactive_lora_v2.safetensors":
            return DEFAULT_AUDIO_REACTIVE_LORA_URL
        return value


class Wan2GPConfig(BaseModel):
    base_url: str = "http://localhost:7860"
    web_password: str | None = Field(default=None, exclude=True, repr=False)
    output_directory: str | None = None
    request_timeout_seconds: float = Field(default=30, ge=1, le=600)
    render_timeout_seconds: float = Field(default=7200, ge=10, le=86400)
    poll_interval_seconds: float = Field(default=0.5, ge=0.1, le=10)
    profile: VideoModelProfile = Field(default_factory=LTX23DistilledProfile)
    # Retain independent quality settings when changing the active renderer.
    profiles: dict[str, VideoModelProfile] = Field(default_factory=default_video_profiles)
    audio_reactive_profile: AudioReactiveLoraProfile = Field(
        default_factory=AudioReactiveLoraProfile
    )

    @computed_field
    @property
    def web_password_configured(self) -> bool:
        return bool(self.web_password)

    @model_validator(mode="after")
    def synchronize_profiles(self) -> "Wan2GPConfig":
        if any(key != profile.name for key, profile in self.profiles.items()):
            raise ValueError("Saved video profile keys must match their profile names")
        self.profiles = {
            **default_video_profiles(),
            **self.profiles,
            self.profile.name: self.profile,
        }
        return self

    def profile_for(self, name: str) -> VideoModelProfile:
        if name == self.profile.name:
            return self.profile
        if name not in self.profiles:
            raise ValueError(f"Unknown video model profile: {name}")
        return self.profiles[name]

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
    end_keyframe_asset_id: str | None = Field(default=None, min_length=1)
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


class VideoRenderJobResponse(BaseModel):
    job: Job


class Wan2GPExecutionResult(BaseModel):
    output_path: Path
    stdout_tail: str = ""
