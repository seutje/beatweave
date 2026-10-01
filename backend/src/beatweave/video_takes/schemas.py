from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from beatweave.jobs.schemas import Job
from beatweave.project.schemas import AssetMetadata
from beatweave.wan2gp.schemas import VideoQualityMode


class VideoTake(BaseModel):
    id: str
    scene_id: str
    asset_id: str
    source_job_id: str
    prompt: str
    backend: str
    backend_settings: dict[str, Any] = Field(default_factory=dict)
    source_asset_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class VideoTakeView(VideoTake):
    asset: AssetMetadata
    asset_path: str
    selected: bool = False
    stale: bool = False


class SceneVideoTakes(BaseModel):
    scene_id: str
    selected_take_id: str | None = None
    selected_take_stale: bool = False
    takes: list[VideoTakeView]
    render_jobs: list[Job]


class RenderSceneRequest(BaseModel):
    quality_mode: VideoQualityMode = VideoQualityMode.PREVIEW


class RenderSceneResponse(BaseModel):
    job: Job


class SelectVideoTakeResponse(BaseModel):
    detail: SceneVideoTakes
