import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.models import ApplicationSettingRecord, ProjectRecord
from beatweave.project.schemas import (
    CreateProjectRequest,
    Project,
    RecentProject,
    UpdateProjectRequest,
    normalize_project_path,
)
from beatweave.project.store import PROJECT_DIRECTORIES, ProjectStore

logger = logging.getLogger(__name__)
CURRENT_PROJECT_KEY = "current_project_path"


class ProjectService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, request: CreateProjectRequest) -> Project:
        parent = Path(request.parent_directory).expanduser().resolve()
        if not parent.is_dir():
            raise BeatweaveError(
                "parent_directory_missing",
                "The selected parent directory does not exist.",
                status_code=404,
                details={"path": str(parent)},
            )
        project_directory = parent / request.name
        if project_directory.exists():
            raise BeatweaveError(
                "project_path_exists",
                "A file or folder already exists at the requested project path.",
                status_code=409,
                details={"path": str(project_directory)},
            )

        try:
            project_directory.mkdir()
            for directory in PROJECT_DIRECTORIES:
                (project_directory / directory).mkdir()
            now = datetime.now(UTC)
            project = Project(
                id=str(uuid4()),
                name=request.name,
                version=1,
                path=str(project_directory),
                created_at=now,
                updated_at=now,
            )
            store = ProjectStore(project_directory)
            store.initialize()
            store.insert_project(project)
        except Exception:
            database_path = project_directory / "project.db"
            database_path.unlink(missing_ok=True)
            for directory in reversed(PROJECT_DIRECTORIES):
                child = project_directory / directory
                if child.exists():
                    child.rmdir()
            if project_directory.exists():
                project_directory.rmdir()
            raise

        self._remember(project)
        logger.info("Created project %s at %s", project.id, project.path)
        return project

    def open(self, path_value: str) -> Project:
        directory = normalize_project_path(path_value).resolve()
        if not directory.is_dir():
            raise BeatweaveError(
                "project_directory_missing",
                "The selected project directory no longer exists.",
                status_code=404,
                details={"path": str(directory)},
            )
        store = ProjectStore(directory)
        if not store.database_path.is_file():
            return store.read_project()
        store.initialize()
        project = store.read_project()
        self._remember(project)
        return project

    def current(self) -> Project | None:
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, CURRENT_PROJECT_KEY)
        if setting is None:
            return None
        try:
            return self.open(setting.value)
        except BeatweaveError:
            self.close()
            raise

    def close(self) -> None:
        with self.database.session() as session:
            session.execute(
                delete(ApplicationSettingRecord).where(
                    ApplicationSettingRecord.key == CURRENT_PROJECT_KEY
                )
            )

    def update(self, project_id: str, request: UpdateProjectRequest) -> Project:
        project = self.current()
        if project is None or project.id != project_id:
            raise BeatweaveError(
                "project_not_open",
                "Open the project before updating it.",
                status_code=409,
            )
        values: dict[str, object] = {}
        if request.name is not None:
            values["name"] = request.name.strip()
        if request.creative_brief is not None:
            values["creative_brief"] = request.creative_brief
        if request.settings is not None:
            values["settings"] = request.settings
        project = project.model_copy(update={**values, "updated_at": datetime.now(UTC)}, deep=True)
        ProjectStore(Path(project.path)).update_project(project)
        self._remember(project)
        return project

    def recent(self) -> list[RecentProject]:
        with self.database.session() as session:
            records = session.scalars(
                select(ProjectRecord).order_by(ProjectRecord.last_opened_at.desc()).limit(12)
            ).all()
        return [
            RecentProject(
                id=record.id,
                name=record.name,
                path=record.path,
                updated_at=record.last_opened_at,
                exists=Path(record.path).joinpath("project.db").is_file(),
            )
            for record in records
        ]

    def set_audio_asset(self, project: Project, asset_id: str) -> Project:
        updated = project.model_copy(
            update={"audio_asset_id": asset_id, "updated_at": datetime.now(UTC)}
        )
        ProjectStore(Path(updated.path)).update_project(updated)
        self._remember(updated)
        return updated

    def _remember(self, project: Project) -> None:
        opened_at = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(ProjectRecord, project.id)
            if record is None:
                record = ProjectRecord(
                    id=project.id,
                    name=project.name,
                    path=project.path,
                    version=project.version,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    last_opened_at=opened_at,
                )
                session.add(record)
            else:
                record.name = project.name
                record.path = project.path
                record.version = project.version
                record.updated_at = project.updated_at
                record.last_opened_at = opened_at
            setting = session.get(ApplicationSettingRecord, CURRENT_PROJECT_KEY)
            if setting is None:
                session.add(ApplicationSettingRecord(key=CURRENT_PROJECT_KEY, value=project.path))
            else:
                setting.value = project.path
