import logging
import os
import shutil
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
    ProjectBackupResponse,
    ProjectIntegrityReport,
    RecentProject,
    RelinkAssetResponse,
    UpdateProjectRequest,
    normalize_project_path,
)
from beatweave.project.store import PROJECT_DIRECTORIES, ProjectStore, file_sha256

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
            (project_directory / ".migration-in-progress.json").unlink(missing_ok=True)
            database_path.with_name(f"{database_path.name}-wal").unlink(missing_ok=True)
            database_path.with_name(f"{database_path.name}-shm").unlink(missing_ok=True)
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
            setting = session.get(ApplicationSettingRecord, CURRENT_PROJECT_KEY)
            if setting is not None:
                try:
                    ProjectStore(setting.value).create_backup_if_changed()
                except Exception:
                    logger.warning("Could not create a final project backup", exc_info=True)
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
        previous_asset_id = project.audio_asset_id
        updated = project.model_copy(
            update={"audio_asset_id": asset_id, "updated_at": datetime.now(UTC)}
        )
        store = ProjectStore(Path(updated.path))
        store.update_project(updated)
        if previous_asset_id is not None and previous_asset_id != asset_id:
            with store.connection() as connection:
                connection.execute(
                    """
                    UPDATE scenes
                    SET selected_video_take_stale = 1, updated_at = ?
                    WHERE selected_video_take_id IS NOT NULL
                    """,
                    (updated.updated_at.isoformat(),),
                )
        self._remember(updated)
        return updated

    def integrity(self, *, verify_hashes: bool = False) -> ProjectIntegrityReport:
        project = self._require_current()
        return ProjectStore(project.path).integrity_report(verify_hashes=verify_hashes)

    def backup(self) -> ProjectBackupResponse:
        project = self._require_current()
        path = ProjectStore(project.path).create_backup("manual")
        return ProjectBackupResponse(path=str(path), created_at=datetime.now(UTC))

    def relink_asset(self, asset_id: str, path_value: str) -> RelinkAssetResponse:
        project = self._require_current()
        store = ProjectStore(project.path)
        asset = store.get_asset(asset_id)
        if asset is None:
            raise BeatweaveError("asset_not_found", "The asset was not found.", status_code=404)
        source = Path(path_value).expanduser().resolve()
        if not source.is_file():
            raise BeatweaveError(
                "relink_file_missing",
                "The selected replacement file does not exist.",
                status_code=404,
                details={"path": str(source)},
            )
        actual_hash = file_sha256(source)
        if actual_hash != asset.sha256:
            raise BeatweaveError(
                "relink_hash_mismatch",
                "The selected file is not the same media that was registered by the project.",
                status_code=409,
                details={"expected_sha256": asset.sha256, "actual_sha256": actual_hash},
            )
        destination = (store.directory / asset.relative_path).resolve()
        if store.directory not in destination.parents:
            raise BeatweaveError(
                "asset_path_unsafe",
                "The registered asset path points outside the project.",
                status_code=422,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.relinking")
        try:
            shutil.copy2(source, temporary)
            if file_sha256(temporary) != asset.sha256:
                raise OSError("relinked copy did not preserve the source hash")
            os.replace(temporary, destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise BeatweaveError(
                "asset_relink_failed",
                "The replacement media could not be copied into the project.",
                details={"path": str(destination)},
            ) from error
        with store.connection() as connection:
            connection.execute(
                "UPDATE assets SET original_path = ?, size_bytes = ? WHERE id = ?",
                (str(source), destination.stat().st_size, asset.id),
            )
        updated = store.get_asset(asset.id)
        assert updated is not None
        return RelinkAssetResponse(asset=updated, path=str(destination))

    def _require_current(self) -> Project:
        project = self.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        return project

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
