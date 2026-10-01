from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from beatweave.jobs.schemas import Job


class ExportIssue(BaseModel):
    code: str
    message: str
    scene_id: str | None = None


class ExportReadiness(BaseModel):
    ready: bool
    scene_count: int
    duration_seconds: float
    issues: list[ExportIssue]


class VideoCodec(StrEnum):
    H264 = "h264"
    H265 = "h265"


class ExportRequest(BaseModel):
    filename: str = Field(default="beatweave-final.mp4", min_length=1, max_length=180)
    codec: VideoCodec = VideoCodec.H264
    crf: int = Field(default=18, ge=12, le=35)
    frame_rate: int = Field(default=24, ge=1, le=60)
    width: int = Field(default=1920, ge=256, le=3840, multiple_of=2)
    height: int = Field(default=1080, ge=256, le=2160, multiple_of=2)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        name = value.strip()
        if not name.lower().endswith(".mp4"):
            name += ".mp4"
        if name in {".mp4", "..mp4"} or any(character in name for character in '<>:"/\\|?*'):
            raise ValueError("filename must be a safe MP4 filename")
        return name


class ExportJobResponse(BaseModel):
    job: Job
