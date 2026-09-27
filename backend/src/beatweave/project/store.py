import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beatweave.errors import BeatweaveError
from beatweave.project.schemas import CreativeBrief, Project, ProjectSettings

PROJECT_DATABASE_NAME = "project.db"
PROJECT_DIRECTORIES = (
    "source",
    "references",
    "keyframes",
    "previews",
    "renders",
    "cache",
    "exports",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def migration_1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE project_metadata (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            creative_brief_json TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            audio_asset_id TEXT
        );
        CREATE TABLE assets (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            original_path TEXT,
            filename TEXT NOT NULL,
            mime_type TEXT,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            media_metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX ix_assets_kind ON assets(kind);
        """
    )


PROJECT_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {1: migration_1}
CURRENT_PROJECT_SCHEMA_VERSION = max(PROJECT_MIGRATIONS)


class ProjectStore:
    def __init__(self, project_directory: Path) -> None:
        self.directory = project_directory.resolve()
        self.database_path = self.directory / PROJECT_DATABASE_NAME

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            for version in range(current + 1, CURRENT_PROJECT_SCHEMA_VERSION + 1):
                PROJECT_MIGRATIONS[version](connection)
                connection.execute(f"PRAGMA user_version = {version}")

    def read_project(self) -> Project:
        if not self.database_path.is_file():
            raise BeatweaveError(
                "project_database_missing",
                f"No {PROJECT_DATABASE_NAME} was found in {self.directory}",
                status_code=404,
                details={"path": str(self.directory)},
            )
        try:
            with self.connection() as connection:
                row = connection.execute("SELECT * FROM project_metadata LIMIT 1").fetchone()
        except sqlite3.DatabaseError as error:
            raise BeatweaveError(
                "project_database_invalid",
                "The project database could not be read.",
                status_code=422,
                details={"path": str(self.database_path)},
            ) from error
        if row is None:
            raise BeatweaveError(
                "project_metadata_missing",
                "The project database does not contain project metadata.",
                status_code=422,
            )
        return self._project_from_row(row)

    def insert_project(self, project: Project) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO project_metadata (
                    id, name, version, created_at, updated_at, creative_brief_json,
                    settings_json, audio_asset_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.version,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    project.creative_brief.model_dump_json(),
                    project.settings.model_dump_json(),
                    project.audio_asset_id,
                ),
            )

    def update_project(self, project: Project) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE project_metadata
                SET name = ?, version = ?, updated_at = ?, creative_brief_json = ?,
                    settings_json = ?, audio_asset_id = ?
                WHERE id = ?
                """,
                (
                    project.name,
                    project.version,
                    project.updated_at.isoformat(),
                    project.creative_brief.model_dump_json(),
                    project.settings.model_dump_json(),
                    project.audio_asset_id,
                    project.id,
                ),
            )

    def _project_from_row(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            path=str(self.directory),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            creative_brief=CreativeBrief.model_validate_json(row["creative_brief_json"]),
            settings=ProjectSettings.model_validate_json(row["settings_json"]),
            audio_asset_id=row["audio_asset_id"],
        )

    def asset_row(self, asset_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["media_metadata"] = json.loads(result.pop("media_metadata_json"))
        return result
