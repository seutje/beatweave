from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EnergySample(BaseModel):
    time: float = Field(ge=0)
    value: float = Field(ge=0, le=1)
    rms: float = Field(ge=0, le=1)
    spectral_flux: float = Field(ge=0, le=1)
    onset_density: float = Field(ge=0, le=1)


class AnalysisParameters(BaseModel):
    beat_analyzer: str
    beat_model: str
    beat_device: str
    energy_sample_rate: int
    frame_length: int
    hop_length: int
    energy_weights: dict[str, float]
    normalization_percentiles: tuple[float, float]


class AudioAnalysis(BaseModel):
    id: str
    asset_id: str
    source_sha256: str
    bpm_estimate: float | None = Field(default=None, gt=0)
    beats: list[float]
    downbeats: list[float]
    energy_curve: list[EnergySample]
    parameters: AnalysisParameters
    created_at: datetime


JobState = Literal["queued", "running", "complete", "failed"]


class AnalysisJob(BaseModel):
    id: str
    type: Literal["audio_analysis"] = "audio_analysis"
    state: JobState
    progress: float = Field(ge=0, le=1)
    related_entity_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
