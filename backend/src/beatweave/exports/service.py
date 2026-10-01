import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.exports.schemas import ExportIssue, ExportReadiness, ExportRequest, VideoCodec
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.media.service import file_sha256
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore


class ExportService:
    def __init__(self, database: Database, media_runner: MediaProcessRunner) -> None:
        self.database = database
        self.projects = ProjectService(database)
        self.media_runner = media_runner

    def readiness(self) -> ExportReadiness:
        store = self._store()
        return self._readiness(store)

    def _readiness(self, store: ProjectStore) -> ExportReadiness:
        rows = self._selected_rows(store)
        issues: list[ExportIssue] = []
        for row in rows:
            scene_id = row["scene_id"]
            if not row["selected_video_take_id"]:
                issues.append(
                    ExportIssue(
                        code="selected_take_missing",
                        scene_id=scene_id,
                        message=f"Scene {row['position'] + 1} has no selected video take.",
                    )
                )
                continue
            if not row["take_id"] or not row["relative_path"]:
                issues.append(
                    ExportIssue(
                        code="selected_take_record_missing",
                        scene_id=scene_id,
                        message=f"Scene {row['position'] + 1}'s selected take is missing.",
                    )
                )
                continue
            if row["selected_video_take_stale"]:
                issues.append(
                    ExportIssue(
                        code="selected_take_stale",
                        scene_id=scene_id,
                        message=f"Scene {row['position'] + 1}'s selected take is stale.",
                    )
                )
            path = (store.directory / row["relative_path"]).resolve()
            if store.directory not in path.parents or not path.is_file():
                issues.append(
                    ExportIssue(
                        code="selected_take_file_missing",
                        scene_id=scene_id,
                        message=f"Scene {row['position'] + 1}'s video file is missing.",
                    )
                )
            settings = json.loads(row["backend_settings_json"] or "{}")
            scene_duration = float(row["end_time"]) - float(row["start_time"])
            take_duration = float(settings.get("duration_seconds", scene_duration))
            if abs(take_duration - scene_duration) > 0.05:
                issues.append(
                    ExportIssue(
                        code="selected_take_duration_mismatch",
                        scene_id=scene_id,
                        message=(
                            f"Scene {row['position'] + 1}'s take duration does not match "
                            "the timeline."
                        ),
                    )
                )
        project = store.read_project()
        audio = store.get_asset(project.audio_asset_id) if project.audio_asset_id else None
        if audio is None:
            issues.append(ExportIssue(code="audio_missing", message="Project audio is missing."))
        elif not (store.directory / audio.relative_path).is_file():
            issues.append(
                ExportIssue(code="audio_file_missing", message="Project audio file is missing.")
            )
        duration = float(rows[-1]["end_time"]) if rows else 0
        return ExportReadiness(
            ready=bool(rows) and not issues,
            scene_count=len(rows),
            duration_seconds=duration,
            issues=issues,
        )

    def start(self, request: ExportRequest) -> tuple[Job, str]:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        readiness = self.readiness()
        if not readiness.ready:
            raise BeatweaveError(
                "export_not_ready",
                "The selected sequence is not ready to export.",
                status_code=409,
                details=readiness.model_dump(mode="json"),
            )
        now = datetime.now(UTC)
        job = Job(
            id=str(uuid4()),
            type=JobType.FINAL_ASSEMBLY,
            state=JobState.QUEUED,
            progress=0,
            project_id=project.id,
            related_entity_type="project",
            related_entity_id=project.id,
            backend="ffmpeg",
            output={"request": request.model_dump(mode="json")},
            created_at=now,
            updated_at=now,
        )
        ProjectStore(project.path).insert_job(job)
        return job, project.path

    def execute(self, context: JobContext) -> dict:
        store = ProjectStore(context.project_path)
        job = store.get_job(context.job_id)
        if job is None:
            raise BeatweaveError("job_not_found", "The export job was not found.", status_code=404)
        request = ExportRequest.model_validate(job.output["request"])
        readiness = self._readiness(store)
        if not readiness.ready:
            raise BeatweaveError(
                "export_not_ready",
                "The selected sequence changed and is no longer ready to export.",
                details=readiness.model_dump(mode="json"),
            )
        rows = self._selected_rows(store)
        work = store.directory / "cache" / "exports" / context.job_id
        work.mkdir(parents=True, exist_ok=True)
        normalized: list[Path] = []
        codec = "libx264" if request.codec == VideoCodec.H264 else "libx265"
        for index, row in enumerate(rows):
            context.check_cancelled()
            source = (store.directory / row["relative_path"]).resolve()
            output = work / f"clip-{index:04d}.mp4"
            self.media_runner.normalize_video_clip(
                source,
                output,
                duration_seconds=float(row["end_time"]) - float(row["start_time"]),
                width=request.width,
                height=request.height,
                frame_rate=request.frame_rate,
                codec=codec,
                crf=request.crf,
            )
            normalized.append(output)
            context.report(0.1 + 0.65 * ((index + 1) / len(rows)))
        joined = work / "joined.mp4"
        self.media_runner.concatenate_video_clips(normalized, joined)
        context.report(0.85)
        project = store.read_project()
        audio = store.get_asset(project.audio_asset_id or "")
        if audio is None:
            raise BeatweaveError("audio_missing", "Project audio is missing.")
        audio_path = (store.directory / audio.relative_path).resolve()
        destination = store.directory / "exports" / request.filename
        if destination.exists():
            raise BeatweaveError(
                "export_destination_exists",
                "An export with this filename already exists. Choose another filename.",
                status_code=409,
            )
        temporary = destination.with_suffix(".partial.mp4")
        self.media_runner.mux_audio(
            joined,
            audio_path,
            temporary,
            duration_seconds=readiness.duration_seconds,
        )
        temporary.replace(destination)
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="exported_video",
            relative_path=destination.relative_to(store.directory).as_posix(),
            filename=destination.name,
            mime_type=mimetypes.guess_type(destination.name)[0],
            sha256=file_sha256(destination),
            size_bytes=destination.stat().st_size,
            media_metadata={
                "duration_seconds": readiness.duration_seconds,
                "scene_count": readiness.scene_count,
                "codec": request.codec.value,
                "crf": request.crf,
                "width": request.width,
                "height": request.height,
                "frame_rate": request.frame_rate,
            },
            created_at=datetime.now(UTC),
        )
        store.insert_asset(asset)
        return {"asset_id": asset.id, "relative_path": asset.relative_path}

    def _store(self) -> ProjectStore:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        return ProjectStore(project.path)

    @staticmethod
    def _selected_rows(store: ProjectStore):
        with store.connection() as connection:
            return connection.execute(
                """
                SELECT scenes.id AS scene_id, scenes.position, scenes.start_time,
                    scenes.end_time, scenes.selected_video_take_id,
                    scenes.selected_video_take_stale, video_takes.id AS take_id,
                    video_takes.backend_settings_json, assets.relative_path
                FROM scenes
                LEFT JOIN video_takes
                    ON video_takes.id = scenes.selected_video_take_id
                LEFT JOIN assets ON assets.id = video_takes.asset_id
                ORDER BY scenes.position
                """
            ).fetchall()
