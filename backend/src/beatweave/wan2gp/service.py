import hashlib
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.media.service import file_sha256
from beatweave.media.timing import timeline_frame_count
from beatweave.models import ApplicationSettingRecord
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import VideoTake
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.profile import build_queue_params, frame_count, write_queue_archive
from beatweave.wan2gp.schemas import (
    LTX23DistilledProfile,
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
        config = (
            Wan2GPConfig.model_validate_json(setting.value)
            if setting is not None
            else Wan2GPConfig()
        )
        config.web_password = self._password_for(config.base_url)
        return config

    @staticmethod
    def _password_key(base_url: str) -> str:
        return "wan2gp_web_password:" + hashlib.sha256(base_url.encode("utf-8")).hexdigest()

    def _password_for(self, base_url: str) -> str | None:
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, self._password_key(base_url))
            return setting.value if setting is not None else None

    def update_config(self, update: Wan2GPConfigUpdate) -> Wan2GPConfig:
        config = Wan2GPConfig.model_validate(update.model_dump())
        password = (
            self._password_for(config.base_url)
            if update.web_password is None
            else update.web_password or None
        )
        config.web_password = password
        with self.database.session() as session:
            key = self._password_key(config.base_url)
            credential = session.get(ApplicationSettingRecord, key)
            if credential is not None:
                if password is None:
                    session.delete(credential)
                else:
                    credential.value = password
            elif password is not None:
                session.add(ApplicationSettingRecord(key=key, value=password))
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
        config = self.config()
        # Validate before persisting a job and freeze the selected model/quality.
        build_queue_params(request, config)
        if not isinstance(config.profile_for(request.model_profile), LTX23DistilledProfile):
            request = request.model_copy(
                update={
                    "audio_reactive_lora": request.audio_reactive_lora.model_copy(
                        update={"enabled": False, "trigger": None, "multiplier": None}
                    )
                }
            )
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        store = ProjectStore(project.path)
        with store.connection() as connection:
            scene = connection.execute(
                "SELECT id, position FROM scenes WHERE id = ?", (request.scene_id,)
            ).fetchone()
        if scene is None:
            raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
        for asset_id, role in (
            (request.start_keyframe_asset_id, "start"),
            (request.end_keyframe_asset_id, "end"),
        ):
            if asset_id is None or (role == "start" and request.continuation is not None):
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
            output={
                "request": request.model_dump(mode="json"),
                "renderer_config": config.model_dump(mode="json"),
                "scene_number": scene["position"] + 1,
                "wan2gp_submission_started": False,
            },
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
        start_asset, start_frame_source = self._resolve_start_frame(store, request)
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
        # Older jobs predate renderer snapshots; resolve their named profile from
        # the saved profile collection rather than using today's active model.
        config = (
            Wan2GPConfig.model_validate(job.output["renderer_config"])
            if job.output.get("renderer_config")
            else self.config()
        )
        # Credentials belong to the server, never the project/job snapshot.
        config.web_password = self._password_for(config.base_url)
        scene_number = job.output.get("scene_number")
        if scene_number is None:
            with store.connection() as connection:
                scene = connection.execute(
                    "SELECT position FROM scenes WHERE id = ?", (request.scene_id,)
                ).fetchone()
            scene_number = scene["position"] + 1 if scene else 1
        output_filename = job.output.get(
            "wan2gp_output_filename",
            f"beatweave-{request.scene_id}"
            if job.output.get("recovered_after_restart") and job.output.get("queue_generated")
            else f"bw_scene_{scene_number:02d}_{job.id.replace('-', '')}",
        )
        # Creating a local ZIP is not a remote submission. Compact job names
        # also identify jobs from versions that saved sessions before upload but
        # could fail during Client initialization before saving any session.
        modern_name = f"bw_scene_{scene_number:02d}_{job.id.replace('-', '')}"
        known_not_submitted = job.output.get("wan2gp_submission_started") is False or (
            output_filename == modern_name
            and not job.output.get("wan2gp_session_hash")
            and not job.output.get("wan2gp_submission_started")
        )
        legacy_submission = bool(
            not known_not_submitted
            and (
                job.output.get("wan2gp_legacy_submission")
                or (
                    job.output.get("recovered_after_restart")
                    and job.output.get("queue_generated")
                    and not job.output.get("wan2gp_session_hash")
                )
            )
        )
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
            output_filename=output_filename,
        )
        context.report(
            0.03,
            {
                "queue_path": queue_path.relative_to(store.directory).as_posix(),
                "queue_generated": True,
                "wan2gp_output_filename": output_filename,
                "wan2gp_legacy_submission": legacy_submission,
                **(
                    {"wan2gp_submission_started": False}
                    if not legacy_submission and not job.output.get("wan2gp_submission_started")
                    else {}
                ),
            },
        )
        result = Wan2GPAdapter(config, self.media_runner).execute(
            queue_path, output_directory, context
        )
        latest = store.get_job(context.job_id)
        remote_directory = latest.output.get("wan2gp_remote_output_directory") if latest else None
        if remote_directory:
            current_config = self.config()
            if current_config.base_url == config.base_url and not current_config.output_directory:
                current_config.output_directory = remote_directory
                self.update_config(Wan2GPConfigUpdate.model_validate(current_config.model_dump()))
        suffix = result.output_path.suffix.lower() or ".mp4"
        destination_directory = (
            store.directory / "previews"
            if request.quality_mode == VideoQualityMode.PREVIEW
            else store.directory / "renders"
        )
        destination = destination_directory / f"scene_{scene_number:02d}_{job.id}{suffix}"
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
                "render_duration_seconds": audio_duration,
                "timeline_frame_count": timeline_frame_count(
                    request.audio_start_seconds,
                    request.audio_start_seconds + request.duration_seconds,
                    request.frame_rate,
                ),
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
                "model_type": queue_params["model_type"],
                "inference_steps": queue_params["num_inference_steps"],
                "profile": config.profile_for(request.model_profile).model_dump(mode="json"),
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
                "start_frame_source": start_frame_source,
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

    def _resolve_start_frame(
        self, store: ProjectStore, request: VideoRenderRequest
    ) -> tuple[AssetMetadata | None, dict | None]:
        source = request.continuation
        if source is None:
            return store.get_asset(request.start_keyframe_asset_id), None
        take = (
            store.find_video_take_by_job(source.job_id)
            if source.job_id
            else store.get_video_take(source.take_id)
        )
        if source.job_id:
            dependency = store.get_job(source.job_id)
            if dependency is None or dependency.state != JobState.COMPLETE:
                raise BeatweaveError(
                    "video_continuation_dependency_failed",
                    "The previous scene render did not complete. Finish it before this scene.",
                    details={"job_id": source.job_id},
                )
        if take is None or take.scene_id != source.scene_id:
            raise BeatweaveError(
                "video_continuation_take_missing",
                "The previous scene's source take is unavailable. Queue this scene again.",
            )
        with store.connection() as connection:
            previous = connection.execute(
                "SELECT * FROM scenes WHERE id = ?", (source.scene_id,)
            ).fetchone()
            current = connection.execute(
                "SELECT * FROM scenes WHERE id = ?", (request.scene_id,)
            ).fetchone()
        if (
            previous is None
            or current is None
            or previous["end_keyframe_id"] != source.keyframe_id
            or current["start_keyframe_id"] != source.keyframe_id
            or previous["position"] + 1 != current["position"]
            or abs(float(previous["end_time"]) - source.boundary_seconds) > 0.000_001
            or abs(float(current["start_time"]) - source.boundary_seconds) > 0.000_001
            or abs(
                float(take.backend_settings.get("duration_seconds", -1))
                - (float(previous["end_time"]) - float(previous["start_time"]))
            )
            > 0.000_001
        ):
            raise BeatweaveError(
                "video_continuation_timing_changed",
                "The previous scene boundary changed. Render it again and requeue this scene.",
            )
        video_asset = store.get_asset(take.asset_id)
        if video_asset is None:
            raise BeatweaveError(
                "video_continuation_take_missing", "The previous scene's video is unavailable."
            )
        video_path = self._asset_path(store, video_asset)
        rate = int(take.backend_settings.get("frame_rate", request.frame_rate))
        frame_index = timeline_frame_count(
            float(previous["start_time"]), float(previous["end_time"]), rate
        )
        # One derived image per take/cut, associated with the existing shared
        # boundary. Planned image variants and their selections remain intact.
        asset_id = str(uuid5(NAMESPACE_URL, f"{take.id}:{source.keyframe_id}:{rate}:{frame_index}"))
        asset = store.get_asset(asset_id)
        if asset is None:
            destination = store.directory / "keyframes" / f"continuation_{asset_id}.png"
            self.media_runner.extract_video_frame(
                video_path, destination, frame_index=frame_index, frame_rate=rate
            )
            asset = AssetMetadata(
                id=asset_id,
                kind="generated_image",
                relative_path=destination.relative_to(store.directory).as_posix(),
                filename=destination.name,
                mime_type="image/png",
                sha256=file_sha256(destination),
                size_bytes=destination.stat().st_size,
                media_metadata={
                    "source_take_id": take.id,
                    "source_asset_id": video_asset.id,
                    "keyframe_id": source.keyframe_id,
                    "frame_index": frame_index,
                    "frame_rate": rate,
                },
                created_at=datetime.now(UTC),
            )
            store.insert_asset(asset)
        self._asset_path(store, asset)
        return asset, {
            "scene_id": source.scene_id,
            "keyframe_id": source.keyframe_id,
            "take_id": take.id,
            "asset_id": asset.id,
            "frame_index": frame_index,
            "frame_rate": rate,
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
