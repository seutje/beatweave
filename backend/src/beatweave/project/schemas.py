from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreativeBrief(BaseModel):
    concept: str = ""
    style: str = ""
    motifs: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    narrative_arc: str = ""
    negative_guidance: str = ""
    visual_trajectory: list["VisualTrajectoryStage"] = Field(default_factory=list)


class VisualTrajectoryStage(BaseModel):
    position: float = Field(ge=0, le=1)
    description: str = Field(min_length=1, max_length=2_000)
    intensity: float = Field(ge=0, le=1)


class ProjectSettings(BaseModel):
    max_clip_length_seconds: float = Field(default=10.0, gt=0, le=120)


class AssetMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    relative_path: str
    original_path: str | None = None
    filename: str
    mime_type: str | None = None
    sha256: str
    size_bytes: int = Field(ge=0)
    media_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Project(BaseModel):
    id: str
    name: str
    version: int = Field(ge=1)
    path: str
    created_at: datetime
    updated_at: datetime
    creative_brief: CreativeBrief = Field(default_factory=CreativeBrief)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    audio_asset_id: str | None = None


class RecentProject(BaseModel):
    id: str
    name: str
    path: str
    updated_at: datetime
    exists: bool


class ProjectIntegrityIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    asset_id: str | None = None
    path: str | None = None


class ProjectIntegrityReport(BaseModel):
    ok: bool
    checked_at: datetime
    schema_version: int
    expected_schema_version: int
    database_result: str
    asset_count: int
    issues: list[ProjectIntegrityIssue] = Field(default_factory=list)


class ProjectBackupResponse(BaseModel):
    path: str
    created_at: datetime


class RelinkAssetRequest(BaseModel):
    path: str = Field(min_length=1)


class RelinkAssetResponse(BaseModel):
    asset: AssetMetadata
    path: str


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_directory: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Project name cannot be blank")
        if any(character in name for character in '<>:"/\\|?*'):
            raise ValueError("Project name contains characters that are invalid on Windows")
        if name.endswith((".", " ")):
            raise ValueError("Project name cannot end with a period or space")
        return name


class OpenProjectRequest(BaseModel):
    path: str = Field(min_length=1)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    creative_brief: CreativeBrief | None = None
    settings: ProjectSettings | None = None

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return CreateProjectRequest.clean_name(value)


class CloseProjectResponse(BaseModel):
    status: Literal["closed"] = "closed"


def normalize_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.parent if path.name.lower() == "project.db" else path
