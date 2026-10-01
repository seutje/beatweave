from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from beatweave.jobs.schemas import Job


class QwenWorkflowProfile(BaseModel):
    name: str = "qwen-image-2.1"
    diffusion_model: str = "qwen_image_2.1_int8_convrot.safetensors"
    text_encoder: str = "qwen3vl_8b_int8_convrot.safetensors"
    vae: str = "qwen_image_2.1_vae_bf16.safetensors"
    weight_dtype: str = "default"
    cache_device: str = "auto"
    cache_dtype: str = "default"
    default_steps: int = Field(default=25, ge=1, le=100)
    default_cfg: float = Field(default=1, ge=0, le=100)
    sampler: str = "euler"
    scheduler: str = "simple"


class ComfyUIConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8188"
    request_timeout_seconds: float = Field(default=30, ge=1, le=600)
    render_timeout_seconds: float = Field(default=900, ge=10, le=7200)
    poll_interval_seconds: float = Field(default=0.5, ge=0.1, le=10)
    profile: QwenWorkflowProfile = Field(default_factory=QwenWorkflowProfile)

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


class ComfyUIConfigUpdate(ComfyUIConfig):
    pass


class ComfyUIStatus(BaseModel):
    available: bool
    profile_ready: bool = False
    message: str
    version: str | None = None
    device: str | None = None


class ImageRenderRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    negative_prompt: str = Field(default="", max_length=8000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int = Field(default=0, ge=0, le=18446744073709551615)
    steps: int | None = Field(default=None, ge=1, le=100)
    cfg: float | None = Field(default=None, ge=0, le=100)
    output_name: str = Field(default="beatweave-test", min_length=1, max_length=100)
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ImageRenderRequest":
        if self.width % 8 or self.height % 8:
            raise ValueError("width and height must be multiples of 8")
        return self

    @field_validator("output_name")
    @classmethod
    def validate_output_name(cls, value: str) -> str:
        cleaned = "".join(
            character for character in value.strip() if character.isalnum() or character in "-_"
        )
        if not cleaned:
            raise ValueError("output_name must contain a letter or number")
        return cleaned


class ImageRenderJobResponse(BaseModel):
    job: Job


class ComfyUIOutput(BaseModel):
    filename: str
    subfolder: str = ""
    type: str = "output"


class ComfyUIHistoryEntry(BaseModel):
    outputs: dict[str, Any] = Field(default_factory=dict)
    status: dict[str, Any] = Field(default_factory=dict)
