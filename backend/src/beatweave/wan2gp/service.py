import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.service import file_sha256
from beatweave.models import ApplicationSettingRecord
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.profile import write_queue_archive
from beatweave.wan2gp.schemas import (
    VideoRenderRequest,
    Wan2GPConfig,
    Wan2GPConfigUpdate,
    Wan2GPStatus,
)

WAN2GP_CONFIG_KEY = "wan2gp_config"


class Wan2GPService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.projects = ProjectService(database)

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
            asset = store.get_asset(asset_id)
            if asset is None or asset.kind != "generated_image":
                raise BeatweaveError(
                    "keyframe_asset_missing",
                    f"The selected {role} keyframe image is unavailable.",
                    status_code=404,
                    details={"asset_id": asset_id},
                )
            self._asset_path(store, asset)
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
        request = VideoRenderRequest.model_validate(job.output.get("request"))
        start_asset = store.get_asset(request.start_keyframe_asset_id)
        end_asset = store.get_asset(request.end_keyframe_asset_id)
        if start_asset is None or end_asset is None:
            raise BeatweaveError(
                "keyframe_asset_missing", "A keyframe image for this render is unavailable."
            )
        start_path = self._asset_path(store, start_asset)
        end_path = self._asset_path(store, end_asset)
        work_directory = store.directory / "cache" / "wan2gp" / context.job_id
        output_directory = work_directory / "output"
        queue_path = work_directory / "queue.zip"
        config = self.config()
        queue_params = write_queue_archive(request, config, start_path, end_path, queue_path)
        context.report(
            0.03,
            {
                "queue_path": queue_path.relative_to(store.directory).as_posix(),
                "queue_generated": True,
            },
        )
        result = Wan2GPAdapter(config).execute(queue_path, output_directory, context)
        suffix = result.output_path.suffix.lower() or ".mp4"
        destination = store.directory / "renders" / f"scene-{request.scene_id}-{uuid4()}{suffix}"
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
                "source_asset_ids": [start_asset.id, end_asset.id],
            },
            created_at=datetime.now(UTC),
        )
        try:
            store.insert_asset(asset)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {
            "asset_id": asset.id,
            "relative_path": asset.relative_path,
            "queue_path": queue_path.relative_to(store.directory).as_posix(),
            "wan2gp_output": result.output_path.name,
        }

    @staticmethod
    def _asset_path(store: ProjectStore, asset: AssetMetadata) -> Path:
        path = (store.directory / asset.relative_path).resolve()
        if store.directory not in path.parents or not path.is_file():
            raise BeatweaveError(
                "asset_file_missing",
                "A selected keyframe image file is missing.",
                status_code=404,
                details={"asset_id": asset.id},
            )
        return path
