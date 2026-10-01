from datetime import datetime

from pydantic import BaseModel, Field

from beatweave.project.schemas import AssetMetadata, Project


class MediaMetadata(BaseModel):
    duration_seconds: float = Field(gt=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    codec: str
    format_name: str
    bit_rate: int | None = Field(default=None, ge=0)


class WaveformData(BaseModel):
    source_sha256: str
    sample_rate: int
    duration_seconds: float
    peaks: list[float]
    generated_at: datetime


class ImportAudioRequest(BaseModel):
    path: str = Field(min_length=1)


class ImportReferenceRequest(BaseModel):
    path: str = Field(min_length=1)


class AudioImportResponse(BaseModel):
    project: Project
    asset: AssetMetadata
    waveform: WaveformData


class CurrentAudioResponse(AudioImportResponse):
    pass


class AssetLocationResponse(BaseModel):
    path: str
