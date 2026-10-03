import hashlib
import mimetypes
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import JobType
from beatweave.media.process import MediaProcessRunner
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import (
    RenderSceneRequest,
    SceneVideoTakes,
    TimelineVideoTakes,
    VideoTake,
    VideoTakeView,
)
from beatweave.wan2gp.schemas import MotionParameters, VideoRenderRequest
from beatweave.wan2gp.service import Wan2GPService


class VideoTakeService:
    def __init__(self, database: Database, runner: MediaProcessRunner | None = None) -> None:
        self.database = database
        self.projects = ProjectService(database)
        self.runner = runner or MediaProcessRunner()

    def detail(self, scene_id: str) -> SceneVideoTakes:
        store = self._store()
        scene = self._scene_row(store, scene_id)
        takes = store.list_video_takes(scene_id)
        views: list[VideoTakeView] = []
        for take in takes:
            asset = store.get_asset(take.asset_id)
            if asset is None:
                continue
            views.append(
                VideoTakeView(
                    **take.model_dump(),
                    asset=asset,
                    asset_path=str(self._asset_path(store, asset.relative_path)),
                    selected=take.id == scene["selected_video_take_id"],
                    stale=self._is_stale(take, scene),
                )
            )
        selected = next((take for take in views if take.selected), None)
        selected_stale = bool(selected and selected.stale)
        if selected_stale != bool(scene["selected_video_take_stale"]):
            with store.connection() as connection:
                connection.execute(
                    "UPDATE scenes SET selected_video_take_stale = ? WHERE id = ?",
                    (int(selected_stale), scene_id),
                )
        jobs = [
            job
            for job in store.list_jobs()
            if job.type == JobType.VIDEO_RENDER
            and job.related_entity_type == "scene"
            and job.related_entity_id == scene_id
        ]
        return SceneVideoTakes(
            scene_id=scene_id,
            selected_take_id=scene["selected_video_take_id"],
            selected_take_stale=selected_stale,
            takes=views,
            render_jobs=jobs,
        )

    def timeline_detail(self) -> TimelineVideoTakes:
        store = self._store()
        with store.connection() as connection:
            scene_ids = [
                row["id"]
                for row in connection.execute("SELECT id FROM scenes ORDER BY position").fetchall()
            ]
        return TimelineVideoTakes(scenes=[self.detail(scene_id) for scene_id in scene_ids])

    def start_render(self, scene_id: str, body: RenderSceneRequest):
        store = self._store()
        scene = self._scene_row(store, scene_id)
        if not scene["video_prompt"].strip():
            raise BeatweaveError(
                "video_prompt_required",
                "Add a video prompt before rendering this scene.",
                status_code=422,
            )
        missing = []
        required_assets = [("start", scene["start_asset_id"])]
        if scene["use_last_frame_conditioning"]:
            required_assets.append(("end", scene["end_asset_id"]))
        for role, asset_id in required_assets:
            if not asset_id:
                missing.append(role)
        if missing:
            raise BeatweaveError(
                "selected_keyframes_required",
                "Select the required keyframe variants before rendering.",
                status_code=422,
                details={"missing": missing},
            )
        if not scene["audio_asset_id"]:
            raise BeatweaveError(
                "scene_audio_required",
                "Import a project soundtrack before rendering this scene.",
                status_code=422,
            )
        config = Wan2GPService(self.database).config()
        source_take = None
        if body.source_take_id:
            source_take = store.get_video_take(body.source_take_id)
            if source_take is None or source_take.scene_id != scene_id:
                raise BeatweaveError(
                    "video_take_not_found",
                    "The approved preview take was not found.",
                    status_code=404,
                )
            if self._is_stale(source_take, scene):
                raise BeatweaveError(
                    "video_take_stale",
                    "The approved preview is stale and cannot be promoted to final.",
                    status_code=409,
                )
        source_motion = source_take.backend_settings.get("motion", {}) if source_take else {}
        request = VideoRenderRequest(
            scene_id=scene_id,
            start_keyframe_asset_id=scene["start_asset_id"],
            end_keyframe_asset_id=(
                scene["end_asset_id"] if scene["use_last_frame_conditioning"] else None
            ),
            audio_asset_id=scene["audio_asset_id"],
            audio_start_seconds=float(scene["start_time"]),
            prompt=source_take.prompt if source_take else scene["video_prompt"],
            duration_seconds=float(scene["end_time"]) - float(scene["start_time"]),
            frame_rate=config.profile.default_frame_rate,
            model_profile=config.profile.name,
            motion=(
                MotionParameters.model_validate(source_motion)
                if source_motion
                else MotionParameters(amplitude=0.5 + 1.5 * float(scene["motion_energy"]))
            ),
            quality_mode=body.quality_mode,
        )
        job, project_path = Wan2GPService(self.database).start_render(request)
        if body.select_on_complete:
            job.output["select_on_complete"] = True
            store.update_job(job)
        return job, project_path

    def select(self, scene_id: str, take_id: str) -> SceneVideoTakes:
        store = self._store()
        scene = self._scene_row(store, scene_id)
        take = store.get_video_take(take_id)
        if take is None or take.scene_id != scene_id:
            raise BeatweaveError("video_take_not_found", "Video take not found.", status_code=404)
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            connection.execute(
                """
                UPDATE scenes
                SET selected_video_take_id = ?, selected_video_take_stale = ?, updated_at = ?
                WHERE id = ?
                """,
                (take_id, int(self._is_stale(take, scene)), now, scene_id),
            )
        return self.detail(scene_id)

    def delete(self, scene_id: str, take_id: str) -> SceneVideoTakes:
        store = self._store()
        scene = self._scene_row(store, scene_id)
        take = store.get_video_take(take_id)
        if take is None or take.scene_id != scene_id:
            raise BeatweaveError("video_take_not_found", "Video take not found.", status_code=404)
        asset = store.get_asset(take.asset_id)
        remaining = [item for item in store.list_video_takes(scene_id) if item.id != take_id]
        selected_id = scene["selected_video_take_id"]
        selected_stale = bool(scene["selected_video_take_stale"])
        if selected_id == take_id:
            fallback = remaining[0] if remaining else None
            selected_id = fallback.id if fallback else None
            selected_stale = self._is_stale(fallback, scene) if fallback else False
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            connection.execute("DELETE FROM video_takes WHERE id = ?", (take_id,))
            connection.execute("DELETE FROM assets WHERE id = ?", (take.asset_id,))
            connection.execute(
                """
                UPDATE scenes
                SET selected_video_take_id = ?, selected_video_take_stale = ?, updated_at = ?
                WHERE id = ?
                """,
                (selected_id, int(selected_stale), now, scene_id),
            )
        if asset is not None:
            self._asset_path(store, asset.relative_path).unlink(missing_ok=True)
        return self.detail(scene_id)

    def import_video(self, scene_id: str, path_value: str) -> SceneVideoTakes:
        store = self._store()
        scene = self._scene_row(store, scene_id)
        source = Path(path_value).expanduser().resolve()
        if not source.is_file():
            raise BeatweaveError(
                "video_file_missing", "The selected video does not exist.", status_code=404
            )
        if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            raise BeatweaveError(
                "video_format_unsupported",
                "Scene videos must be MP4, MOV, MKV, or WebM files.",
                status_code=415,
            )
        metadata = self.runner.probe_video(source)
        scene_duration = float(scene["end_time"]) - float(scene["start_time"])
        if float(metadata["duration_seconds"]) + 0.05 < scene_duration:
            raise BeatweaveError(
                "video_too_short",
                "The selected video is shorter than this scene.",
                status_code=422,
                details={
                    "video_duration_seconds": metadata["duration_seconds"],
                    "scene_duration_seconds": scene_duration,
                },
            )
        asset_id = str(uuid4())
        take_id = str(uuid4())
        destination = store.directory / "renders" / f"{asset_id}{source.suffix.lower()}"
        shutil.copyfile(source, destination)
        now = datetime.now(UTC)
        asset = AssetMetadata(
            id=asset_id,
            kind="imported_video",
            relative_path=destination.relative_to(store.directory).as_posix(),
            original_path=str(source),
            filename=source.name,
            mime_type=mimetypes.guess_type(source.name)[0],
            sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
            size_bytes=destination.stat().st_size,
            media_metadata={**metadata, "source": "manual_import"},
            created_at=now,
        )
        take = VideoTake(
            id=take_id,
            scene_id=scene_id,
            asset_id=asset_id,
            source_job_id=f"manual-import:{take_id}",
            prompt=scene["video_prompt"],
            backend="manual",
            backend_settings={
                "kind": "manual_import",
                "quality_mode": "imported",
                "resolution": f"{metadata['width']}x{metadata['height']}",
                "duration_seconds": scene_duration,
                "source_duration_seconds": metadata["duration_seconds"],
            },
            created_at=now,
        )
        try:
            store.register_video_take(asset, take)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return self.select(scene_id, take_id)

    def _store(self) -> ProjectStore:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        return ProjectStore(project.path)

    @staticmethod
    def _scene_row(store: ProjectStore, scene_id: str):
        with store.connection() as connection:
            row = connection.execute(
                """
                SELECT scenes.*,
                    start_variant.asset_id AS start_asset_id,
                    end_variant.asset_id AS end_asset_id,
                    (SELECT audio_asset_id FROM project_metadata LIMIT 1) AS audio_asset_id
                FROM scenes
                JOIN keyframes AS start_keyframe
                    ON start_keyframe.id = scenes.start_keyframe_id
                JOIN keyframes AS end_keyframe
                    ON end_keyframe.id = scenes.end_keyframe_id
                LEFT JOIN keyframe_variants AS start_variant
                    ON start_variant.id = start_keyframe.selected_variant_id
                LEFT JOIN keyframe_variants AS end_variant
                    ON end_variant.id = end_keyframe.selected_variant_id
                WHERE scenes.id = ?
                """,
                (scene_id,),
            ).fetchone()
        if row is None:
            raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
        return row

    @staticmethod
    def _is_stale(take: VideoTake | None, scene) -> bool:
        if take is None:
            return False
        duration = float(scene["end_time"]) - float(scene["start_time"])
        if take.backend == "manual":
            return (
                abs(float(take.backend_settings.get("duration_seconds", duration)) - duration)
                > 0.05
            )
        audio_conditioning = take.backend_settings.get("audio_conditioning", {})
        audio_start = float(audio_conditioning.get("start_seconds", -1))
        return (
            take.prompt != scene["video_prompt"]
            or take.source_asset_ids
            != (
                [scene["start_asset_id"], scene["end_asset_id"], scene["audio_asset_id"]]
                if scene["use_last_frame_conditioning"]
                else [scene["start_asset_id"], scene["audio_asset_id"]]
            )
            or abs(audio_start - float(scene["start_time"])) > 0.000_001
            or abs(float(take.backend_settings.get("duration_seconds", duration)) - duration)
            > 0.000_001
        )

    @staticmethod
    def _asset_path(store: ProjectStore, relative_path: str) -> Path:
        path = (store.directory / relative_path).resolve()
        if store.directory not in path.parents:
            raise BeatweaveError("asset_path_invalid", "Video asset path is invalid.")
        return path
