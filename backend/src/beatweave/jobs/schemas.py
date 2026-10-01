from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobType(StrEnum):
    AUDIO_ANALYSIS = "audio_analysis"
    PROJECT_PLANNING = "project_planning"
    KEYFRAME_RENDER = "keyframe_render"
    VIDEO_RENDER = "video_render"
    PROXY_GENERATION = "proxy_generation"
    FINAL_ASSEMBLY = "final_assembly"


class JobState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATES = {JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED}


class JobError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class Job(BaseModel):
    id: str
    type: JobType
    state: JobState
    progress: float = Field(ge=0, le=1)
    project_id: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    backend: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    error: JobError | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancellation_requested_at: datetime | None = None


class CancelJobResponse(BaseModel):
    job: Job


class RetryJobResponse(BaseModel):
    job: Job
