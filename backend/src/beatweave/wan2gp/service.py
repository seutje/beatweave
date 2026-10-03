import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.media.service import file_sha256
from beatweave.models import ApplicationSettingRecord
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import VideoTake
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.profile import frame_count, write_queue_archive
from beatweave.wan2gp.schemas import (
    VideoQualityMode,
    VideoRenderRequest,
    Wan2GPConfig,
    Wan2GPConfigUpdate,
    Wan2GPStatus,
)

WAN2GP_CONFIG_KEY = "wan2gp_config"


class Wan2GPService:
    def __init__(self, database: Database, media_runner: MediaProcessRunner | None = None) -> None:
        self.database = database
        self.projects = ProjectService(database)
        self.media_runner = media_runner or MediaProcessRunner()

    def config(self) -> Wan2GPConfig:
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, WAN2GP_CONFIG_KEY)
        return (
            Wan2GPConfig.model_validate_json(setting.value)
            if setting is not None
            else Wan2GPConfig()
        )

    def update_config(self, update: Wan2GPConfigUpdate) -> Wan2GPConfig:
        config = Wan2GPConfig.model_validate(update.model_dump())
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, WAN2GP_CONFIG_KEY)
            if setting is None:
                session.add(
                    ApplicationSettingRecord(key=WAN2GP_CONFIG_KEY, value=config.model_dump_json())
                )
            else:
                setting.value = config.model_dump_json()
        return config

    def status(self) -> Wan2GPStatus:
        return Wan2GPAdapter(self.config()).status()

    def start_render(self, request: VideoRenderRequest) -> tuple[Job, str]:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        store = ProjectStore(project.path)
        with store.connection() as connection:
            scene = connection.execute(
                "SELECT id FROM scenes WHERE id = ?", (request.scene_id,)
            ).fetchone()
        if scene is None:
            raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
        for asset_id, role in (
            (request.start_keyframe_asset_id, "start"),
            (request.end_keyframe_asset_id, "end"),
        ):
            if asset_id is None:
                continue
            asset = store.get_asset(asset_id)
            if asset is None or not (asset.mime_type or "").startswith("image/"):
                raise BeatweaveError(
                    "keyframe_asset_missing",
                    f"The selected {role} keyframe image is unavailable.",
                    status_code=404,
                    details={"asset_id": asset_id},
                )
            self._asset_path(store, asset)
        audio_asset = store.get_asset(request.audio_asset_id)
        if audio_asset is None or audio_asset.kind != "audio":
            raise BeatweaveError(
                "scene_audio_missing",
                "The project soundtrack for this scene is unavailable.",
                status_code=404,
                details={"asset_id": request.audio_asset_id},
            )
        self._asset_path(store, audio_asset)
        now = datetime.now(UTC)
        job = Job(
            id=str(uuid4()),
            type=JobType.VIDEO_RENDER,
            state=JobState.QUEUED,
            progress=0,
            project_id=project.id,
            related_entity_type="scene",
            related_entity_id=request.scene_id,
            backend="wan2gp",
            output={"request": request.model_dump(mode="json")},
            created_at=now,
            updated_at=now,
        )
        store.insert_job(job)
        return job, project.path

    def execute(self, context: JobContext) -> dict:
        store = ProjectStore(context.project_path)
        job = store.get_job(context.job_id)
        if job is None:
            raise BeatweaveError("job_not_found", "The render job was not found.", status_code=404)
        existing = store.find_video_take_by_job(context.job_id)
        if existing is not None:
            self._select_take_if_requested(store, job, existing)
            asset = store.get_asset(existing.asset_id)
            return {
                "take_id": existing.id,
                "asset_id": existing.asset_id,
                "relative_path": asset.relative_path if asset else None,
                "reused": True,
            }
        request = VideoRenderRequest.model_validate(job.output.get("request"))
        start_asset = store.get_asset(request.start_keyframe_asset_id)
        end_asset = store.get_asset(request.end_keyframe_asset_id)
        audio_asset = store.get_asset(request.audio_asset_id)
        if (
            start_asset is None
            or (request.end_keyframe_asset_id and end_asset is None)
            or audio_asset is None
        ):
            raise BeatweaveError(
                "render_input_missing", "A media input for this render is unavailable."
            )
        start_path = self._asset_path(store, start_asset)
        end_path = self._asset_path(store, end_asset) if end_asset is not None else None
        audio_source_path = self._asset_path(store, audio_asset)
        work_directory = store.directory / "cache" / "wan2gp" / context.job_id
        output_directory = work_directory / "output"
        queue_path = work_directory / "queue.zip"
        audio_guide_path = work_directory / "scene-audio.wav"
        config = self.config()
        audio_duration = frame_count(request, config) / request.frame_rate
        self.media_runner.extract_audio_segment(
            audio_source_path,
            audio_guide_path,
            start_seconds=request.audio_start_seconds,
            duration_seconds=audio_duration,
        )
        queue_params = write_queue_archive(
            request,
            config,
            start_path,
            end_path,
            audio_guide_path,
            queue_path,
        )
        context.report(
            0.03,
            {
                "queue_path": queue_path.relative_to(store.directory).as_posix(),
                "queue_generated": True,
            },
        )
        result = Wan2GPAdapter(config).execute(queue_path, output_directory, context)
        suffix = result.output_path.suffix.lower() or ".mp4"
        destination_directory = (
            store.directory / "previews"
            if request.quality_mode == VideoQualityMode.PREVIEW
            else store.directory / "renders"
        )
        destination = destination_directory / f"scene-{request.scene_id}-{uuid4()}{suffix}"
        temporary = destination.with_suffix(destination.suffix + ".partial")
        try:
            shutil.copy2(result.output_path, temporary)
            temporary.replace(destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise BeatweaveError(
                "wan2gp_output_copy_failed",
                "The generated video could not be copied into the project.",
            ) from error
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_video",
            relative_path=destination.relative_to(store.directory).as_posix(),
            filename=destination.name,
            mime_type=mimetypes.guess_type(destination.name)[0],
            sha256=file_sha256(destination),
            size_bytes=destination.stat().st_size,
            media_metadata={
                "scene_id": request.scene_id,
                "duration_seconds": request.duration_seconds,
                "frame_rate": request.frame_rate,
                "frame_count": queue_params["video_length"],
                "prompt": request.prompt,
                "backend": "wan2gp",
                "model_profile": request.model_profile,
                "quality_mode": request.quality_mode.value,
                "motion": request.motion.model_dump(mode="json"),
                "audio_reactive_lora": request.audio_reactive_lora.model_dump(mode="json"),
                "audio_asset_id": audio_asset.id,
                "audio_start_seconds": request.audio_start_seconds,
                "audio_duration_seconds": audio_duration,
                "source_asset_ids": [
                    start_asset.id,
                    *([end_asset.id] if end_asset is not None else []),
                    audio_asset.id,
                ],
            },
            created_at=datetime.now(UTC),
        )
        take = VideoTake(
            id=str(uuid4()),
            scene_id=request.scene_id,
            asset_id=asset.id,
            source_job_id=context.job_id,
            prompt=request.prompt,
            backend="wan2gp",
            backend_settings={
                "model_profile": request.model_profile,
                "quality_mode": request.quality_mode.value,
                "resolution": queue_params["resolution"],
                "duration_seconds": request.duration_seconds,
                "frame_rate": request.frame_rate,
                "frame_count": queue_params["video_length"],
                "motion": request.motion.model_dump(mode="json"),
                "audio_reactive_lora": request.audio_reactive_lora.model_dump(mode="json"),
                "audio_conditioning": {
                    "asset_id": audio_asset.id,
                    "start_seconds": request.audio_start_seconds,
                    "duration_seconds": audio_duration,
                    "prompt_type": queue_params["audio_prompt_type"],
                },
                "use_last_frame_conditioning": end_asset is not None,
            },
            source_asset_ids=[
                start_asset.id,
                *([end_asset.id] if end_asset is not None else []),
                audio_asset.id,
            ],
            created_at=asset.created_at,
        )
        try:
            store.register_video_take(asset, take)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        self._select_take_if_requested(store, job, take)
        return {
            "take_id": take.id,
            "asset_id": asset.id,
            "relative_path": asset.relative_path,
            "queue_path": queue_path.relative_to(store.directory).as_posix(),
            "wan2gp_output": result.output_path.name,
        }

    @staticmethod
    def _select_take_if_requested(store: ProjectStore, job: Job, take: VideoTake) -> None:
        if not job.output.get("select_on_complete"):
            return
        with store.connection() as connection:
            connection.execute(
                """
                UPDATE scenes
                SET selected_video_take_id = ?, selected_video_take_stale = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (take.id, take.created_at.isoformat(), take.scene_id),
            )

    @staticmethod
    def _asset_path(store: ProjectStore, asset: AssetMetadata) -> Path:
        path = (store.directory / asset.relative_path).resolve()
        if store.directory not in path.parents or not path.is_file():
            raise BeatweaveError(
                "asset_file_missing",
                "A selected render input file is missing.",
                status_code=404,
                details={"asset_id": asset.id},
            )
        return path
