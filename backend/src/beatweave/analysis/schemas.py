from datetime import UTC, datetime

from pydantic import BaseModel, Field

from beatweave.jobs.schemas import Job, JobType


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


class AnalysisJob(Job):
    """Backward-compatible audio-analysis specialization of the generic job."""

    type: JobType = JobType.AUDIO_ANALYSIS
    project_id: str = "legacy"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
