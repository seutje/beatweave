from pydantic import BaseModel, Field

from beatweave.project.schemas import CreativeBrief, Project
from beatweave.timeline.schemas import Timeline


class TrackAnalysisSummary(BaseModel):
    duration_seconds: float
    bpm_estimate: float | None
    beat_count: int
    downbeat_count: int
    average_energy: float = Field(ge=0, le=1)
    peak_energy: float = Field(ge=0, le=1)


class ScenePlanningContext(BaseModel):
    scene_id: str
    position: int
    start_time: float
    end_time: float
    duration_seconds: float
    average_energy: float = Field(ge=0, le=1)
    peak_energy: float = Field(ge=0, le=1)


class StyleReferenceSummary(BaseModel):
    filename: str
    mime_type: str | None
    size_bytes: int


class VisualPlanningContext(BaseModel):
    creative_brief: CreativeBrief
    track: TrackAnalysisSummary
    scenes: list[ScenePlanningContext]
    style_references: list[StyleReferenceSummary]


class GenerateVisualPlanRequest(BaseModel):
    confirm_overwrite: bool = False


class RegenerateSceneRequest(BaseModel):
    confirm_overwrite: bool = False


class VisualPlanningResult(BaseModel):
    project: Project
    timeline: Timeline
