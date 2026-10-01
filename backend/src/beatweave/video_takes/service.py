from datetime import UTC, datetime
from pathlib import Path

from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import JobType
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
    def __init__(self, database: Database) -> None:
        self.database = database
        self.projects = ProjectService(database)

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
        for role, asset_id in (
            ("start", scene["start_asset_id"]),
            ("end", scene["end_asset_id"]),
        ):
            if not asset_id:
                missing.append(role)
        if missing:
            raise BeatweaveError(
                "selected_keyframes_required",
                "Select generated variants for both scene boundaries before rendering.",
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
            end_keyframe_asset_id=scene["end_asset_id"],
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
        return Wan2GPService(self.database).start_render(request)

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
        audio_conditioning = take.backend_settings.get("audio_conditioning", {})
        audio_start = float(audio_conditioning.get("start_seconds", -1))
        return (
            take.prompt != scene["video_prompt"]
            or take.source_asset_ids
            != [scene["start_asset_id"], scene["end_asset_id"], scene["audio_asset_id"]]
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
