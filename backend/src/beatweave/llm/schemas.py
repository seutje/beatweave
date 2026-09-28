from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMProviderConfig(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:8b"
    timeout_seconds: float = Field(default=30, ge=1, le=600)
    api_key: str | None = Field(default=None, exclude=True)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment")
        if parsed.port == 11434 and parsed.path in {"", "/"}:
            normalized = f"{normalized.rstrip('/')}/v1"
        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model must not be empty")
        return normalized


class LLMProviderConfigUpdate(LLMProviderConfig):
    api_key: str | None = None


class LLMProviderConfigView(BaseModel):
    provider: Literal["openai_compatible"]
    base_url: str
    model: str
    timeout_seconds: float
    api_key_configured: bool


class ProviderAvailability(BaseModel):
    available: bool
    message: str


class StructuredGenerationRequest(BaseModel):
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=32768)


class StructuredGenerationResponse[StructuredOutput: BaseModel](BaseModel):
    output: StructuredOutput
    model: str
    repaired: bool = False


class VisualTrajectoryStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: float = Field(ge=0, le=1)
    description: str = Field(min_length=1, max_length=2000)
    intensity: float = Field(ge=0, le=1)


class VisualPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(min_length=1, max_length=4000)
    style: str = Field(min_length=1, max_length=4000)
    motifs: list[str] = Field(default_factory=list, max_length=30)
    palette: list[str] = Field(default_factory=list, max_length=30)
    narrative_arc: str = Field(min_length=1, max_length=8000)
    negative_guidance: str = Field(default="", max_length=4000)
    visual_trajectory: list[VisualTrajectoryStage] = Field(min_length=1, max_length=50)


class ScenePlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(min_length=1)
    concept: str = Field(min_length=1, max_length=4000)
    image_prompt: str = Field(min_length=1, max_length=8000)
    video_prompt: str = Field(min_length=1, max_length=8000)
    visual_energy: float = Field(ge=0, le=1)
    motion_energy: float = Field(ge=0, le=1)


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenes: list[ScenePlanItem] = Field(min_length=1)
