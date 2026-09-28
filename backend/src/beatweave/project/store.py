import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beatweave.analysis.schemas import AnalysisJob, AudioAnalysis
from beatweave.errors import BeatweaveError
from beatweave.project.schemas import AssetMetadata, CreativeBrief, Project, ProjectSettings

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


def migration_2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE audio_analyses (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            bpm_estimate REAL,
            beats_json TEXT NOT NULL,
            downbeats_json TEXT NOT NULL,
            energy_curve_json TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(asset_id) REFERENCES assets(id)
        );
        CREATE INDEX ix_audio_analyses_source_sha256
            ON audio_analyses(source_sha256, created_at);
        CREATE TABLE analysis_jobs (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            state TEXT NOT NULL,
            progress REAL NOT NULL,
            related_entity_id TEXT NOT NULL,
            output_json TEXT NOT NULL DEFAULT '{}',
            error_json TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE INDEX ix_analysis_jobs_created_at ON analysis_jobs(created_at);
        """
    )


def migration_3(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE keyframes (
            id TEXT PRIMARY KEY,
            time REAL NOT NULL CHECK(time >= 0),
            prompt TEXT NOT NULL DEFAULT '',
            selected_variant_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE scenes (
            id TEXT PRIMARY KEY,
            position INTEGER NOT NULL UNIQUE CHECK(position >= 0),
            start_time REAL NOT NULL CHECK(start_time >= 0),
            end_time REAL NOT NULL CHECK(end_time > start_time),
            start_beat_index INTEGER,
            end_beat_index INTEGER,
            start_keyframe_id TEXT NOT NULL,
            end_keyframe_id TEXT NOT NULL,
            concept TEXT NOT NULL DEFAULT '',
            image_prompt TEXT NOT NULL DEFAULT '',
            video_prompt TEXT NOT NULL DEFAULT '',
            visual_energy REAL NOT NULL DEFAULT 0 CHECK(visual_energy BETWEEN 0 AND 1),
            motion_energy REAL NOT NULL DEFAULT 0 CHECK(motion_energy BETWEEN 0 AND 1),
            selected_video_take_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(start_keyframe_id) REFERENCES keyframes(id),
            FOREIGN KEY(end_keyframe_id) REFERENCES keyframes(id),
            CHECK(start_keyframe_id != end_keyframe_id)
        );
        CREATE INDEX ix_scenes_keyframes
            ON scenes(start_keyframe_id, end_keyframe_id);
        """
    )


def migration_4(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE timeline_layout_history (
            id TEXT PRIMARY KEY,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX ix_timeline_layout_history_created_at
            ON timeline_layout_history(created_at);
        """
    )


def migration_5(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE timeline_edit_history (
            id TEXT PRIMARY KEY,
            sequence INTEGER NOT NULL UNIQUE CHECK(sequence > 0),
            operation TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            applied INTEGER NOT NULL DEFAULT 1 CHECK(applied IN (0, 1)),
            created_at TEXT NOT NULL
        );
        CREATE INDEX ix_timeline_edit_history_applied_sequence
            ON timeline_edit_history(applied, sequence);
        """
    )
    legacy = connection.execute(
        "SELECT * FROM timeline_layout_history ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if legacy is not None:
        current = {
            "scenes": [
                dict(row) for row in connection.execute("SELECT * FROM scenes ORDER BY position")
            ],
            "keyframes": [
                dict(row) for row in connection.execute("SELECT * FROM keyframes ORDER BY time")
            ],
        }
        connection.execute(
            """
            INSERT INTO timeline_edit_history (
                id, sequence, operation, before_json, after_json, applied, created_at
            ) VALUES (?, 1, 'apply_layout', ?, ?, 1, ?)
            """,
            (legacy["id"], legacy["snapshot_json"], json.dumps(current), legacy["created_at"]),
        )
        connection.execute("DELETE FROM timeline_layout_history")


def migration_6(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE style_references (
            asset_id TEXT PRIMARY KEY,
            position INTEGER NOT NULL CHECK(position >= 0),
            created_at TEXT NOT NULL,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX ix_style_references_position ON style_references(position);
        """
    )


PROJECT_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: migration_1,
    2: migration_2,
    3: migration_3,
    4: migration_4,
    5: migration_5,
    6: migration_6,
}
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

    def get_asset(self, asset_id: str) -> AssetMetadata | None:
        row = self.asset_row(asset_id)
        return AssetMetadata.model_validate(row) if row is not None else None

    def find_asset_by_hash(self, sha256: str, kind: str) -> AssetMetadata | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE sha256 = ? AND kind = ? LIMIT 1",
                (sha256, kind),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["media_metadata"] = json.loads(result.pop("media_metadata_json"))
        return AssetMetadata.model_validate(result)

    def insert_asset(self, asset: AssetMetadata) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    id, kind, relative_path, original_path, filename, mime_type, sha256,
                    size_bytes, media_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.id,
                    asset.kind,
                    asset.relative_path,
                    asset.original_path,
                    asset.filename,
                    asset.mime_type,
                    asset.sha256,
                    asset.size_bytes,
                    json.dumps(asset.media_metadata),
                    asset.created_at.isoformat(),
                ),
            )

    def list_style_references(self) -> list[AssetMetadata]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT assets.* FROM style_references
                JOIN assets ON assets.id = style_references.asset_id
                ORDER BY style_references.position
                """
            ).fetchall()
        result = []
        for row in rows:
            values = dict(row)
            values["media_metadata"] = json.loads(values.pop("media_metadata_json"))
            result.append(AssetMetadata.model_validate(values))
        return result

    def add_style_reference(self, asset_id: str) -> None:
        with self.connection() as connection:
            position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM style_references"
            ).fetchone()[0]
            connection.execute(
                """
                INSERT OR IGNORE INTO style_references (asset_id, position, created_at)
                VALUES (?, ?, ?)
                """,
                (asset_id, position, utc_now_iso()),
            )

    def remove_style_reference(self, asset_id: str) -> AssetMetadata | None:
        asset = self.get_asset(asset_id)
        if asset is None or asset.kind != "style_reference":
            return None
        with self.connection() as connection:
            removed = connection.execute(
                "DELETE FROM style_references WHERE asset_id = ?", (asset_id,)
            ).rowcount
            if not removed:
                return None
            connection.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            rows = connection.execute(
                "SELECT asset_id FROM style_references ORDER BY position"
            ).fetchall()
            for position, row in enumerate(rows):
                connection.execute(
                    "UPDATE style_references SET position = ? WHERE asset_id = ?",
                    (position, row["asset_id"]),
                )
        return asset

    def insert_analysis(self, analysis: AudioAnalysis) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO audio_analyses (
                    id, asset_id, source_sha256, bpm_estimate, beats_json,
                    downbeats_json, energy_curve_json, parameters_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.id,
                    analysis.asset_id,
                    analysis.source_sha256,
                    analysis.bpm_estimate,
                    json.dumps(analysis.beats),
                    json.dumps(analysis.downbeats),
                    json.dumps(
                        [sample.model_dump(mode="json") for sample in analysis.energy_curve]
                    ),
                    analysis.parameters.model_dump_json(),
                    analysis.created_at.isoformat(),
                ),
            )

    def find_analysis_by_hash(self, source_sha256: str) -> AudioAnalysis | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM audio_analyses
                WHERE source_sha256 = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (source_sha256,),
            ).fetchone()
        return self._analysis_from_row(row) if row is not None else None

    def insert_analysis_job(self, job: AnalysisJob) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO analysis_jobs (
                    id, type, state, progress, related_entity_id, output_json,
                    error_json, created_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._job_values(job),
            )

    def update_analysis_job(self, job: AnalysisJob) -> None:
        values = self._job_values(job)
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE analysis_jobs
                SET type = ?, state = ?, progress = ?, related_entity_id = ?,
                    output_json = ?, error_json = ?, created_at = ?, started_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (*values[1:], values[0]),
            )

    def get_analysis_job(self, job_id: str) -> AnalysisJob | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return AnalysisJob(
            id=row["id"],
            type=row["type"],
            state=row["state"],
            progress=row["progress"],
            related_entity_id=row["related_entity_id"],
            output=json.loads(row["output_json"]),
            error=json.loads(row["error_json"]) if row["error_json"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(datetime.fromisoformat(row["started_at"]) if row["started_at"] else None),
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
        )

    @staticmethod
    def _job_values(job: AnalysisJob) -> tuple[Any, ...]:
        return (
            job.id,
            job.type,
            job.state,
            job.progress,
            job.related_entity_id,
            json.dumps(job.output),
            json.dumps(job.error) if job.error is not None else None,
            job.created_at.isoformat(),
            job.started_at.isoformat() if job.started_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
        )

    @staticmethod
    def _analysis_from_row(row: sqlite3.Row) -> AudioAnalysis:
        return AudioAnalysis.model_validate(
            {
                "id": row["id"],
                "asset_id": row["asset_id"],
                "source_sha256": row["source_sha256"],
                "bpm_estimate": row["bpm_estimate"],
                "beats": json.loads(row["beats_json"]),
                "downbeats": json.loads(row["downbeats_json"]),
                "energy_curve": json.loads(row["energy_curve_json"]),
                "parameters": json.loads(row["parameters_json"]),
                "created_at": row["created_at"],
            }
        )
