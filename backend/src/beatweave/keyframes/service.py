from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.comfyui.schemas import ImageRenderRequest
from beatweave.comfyui.service import ComfyUIService
from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobContext
from beatweave.keyframes.schemas import (
    GenerateKeyframeRequest,
    KeyframeDetail,
    KeyframeVariant,
    KeyframeVariantView,
    SelectVariantResponse,
)
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.service import TimelineService


class KeyframeService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.projects = ProjectService(database)
        self.comfyui = ComfyUIService(database)

    def detail(self, keyframe_id: str) -> KeyframeDetail:
        store = self._store()
        timeline = TimelineService(self.projects).current()
        keyframe = next((item for item in timeline.keyframes if item.id == keyframe_id), None)
        if keyframe is None:
            raise BeatweaveError(
                "keyframe_not_found", "The keyframe was not found.", status_code=404
            )
        adjacent = [
            scene
            for scene in timeline.scenes
            if scene.start_keyframe_id == keyframe_id or scene.end_keyframe_id == keyframe_id
        ]
        variants = []
        for variant in store.list_keyframe_variants(keyframe_id):
            asset = store.get_asset(variant.asset_id)
            if asset is None:
                continue
            path = self._safe_asset_path(store, asset.relative_path)
            variants.append(
                KeyframeVariantView(**variant.model_dump(), asset=asset, asset_path=str(path))
            )
        jobs = [
            job
            for job in store.list_jobs()
            if job.related_entity_type == "keyframe" and job.related_entity_id == keyframe_id
        ]
        return KeyframeDetail(
            keyframe=keyframe,
            variants=variants,
            render_jobs=jobs,
            adjacent_scene_ids=[scene.id for scene in adjacent],
            affected_render_scene_ids=[
                scene.id for scene in adjacent if scene.selected_video_take_id
            ],
        )

    def start_generation(self, keyframe_id: str, body: GenerateKeyframeRequest):
        store = self._store()
        timeline = TimelineService(self.projects).current()
        keyframe = next((item for item in timeline.keyframes if item.id == keyframe_id), None)
        if keyframe is None:
            raise BeatweaveError(
                "keyframe_not_found", "The keyframe was not found.", status_code=404
            )
        prompt = (
            body.prompt or keyframe.prompt or self._scene_prompt(timeline, keyframe_id)
        ).strip()
        if not prompt:
            raise BeatweaveError(
                "keyframe_prompt_required",
                "Add an image prompt before generating this keyframe.",
                status_code=409,
            )
        references: list[str] = []
        previous = self._previous_selected_asset(timeline, store, keyframe_id)
        if previous:
            references.append(previous)
        if body.include_global_style_references:
            references.extend(asset.id for asset in store.list_style_references())
        references.extend(body.additional_reference_asset_ids)
        references = list(dict.fromkeys(references))
        if len(references) > 16:
            raise BeatweaveError(
                "too_many_keyframe_references",
                "A keyframe render supports at most 16 reference images.",
                status_code=422,
            )
        for asset_id in references:
            asset = store.get_asset(asset_id)
            if asset is None or not (asset.mime_type or "").startswith("image/"):
                raise BeatweaveError(
                    "invalid_keyframe_reference",
                    "Every keyframe reference must be an existing image asset.",
                    status_code=422,
                    details={"asset_id": asset_id},
                )
        with store.connection() as connection:
            connection.execute(
                "UPDATE keyframes SET prompt = ?, updated_at = ? WHERE id = ?",
                (prompt, datetime.now(UTC).isoformat(), keyframe_id),
            )
        request = ImageRenderRequest(
            prompt=prompt,
            negative_prompt=body.negative_prompt,
            width=body.width,
            height=body.height,
            seed=body.seed,
            steps=body.steps,
            cfg=body.cfg,
            output_name=f"keyframe-{keyframe_id[:8]}",
            related_entity_type="keyframe",
            related_entity_id=keyframe_id,
            reference_asset_ids=references,
        )
        return self.comfyui.start_render(request)

    def execute(self, context: JobContext) -> dict:
        store = ProjectStore(context.project_path)
        job = store.get_job(context.job_id)
        if job is None:
            raise BeatweaveError("job_not_found", "The render job was not found.", status_code=404)
        if job.related_entity_type != "keyframe" or not job.related_entity_id:
            return self.comfyui.execute(context)
        existing = store.find_keyframe_variant_by_job(job.id)
        if existing is not None:
            return {"asset_id": existing.asset_id, "variant_id": existing.id}
        request = ImageRenderRequest.model_validate(job.output.get("request"))
        result = self.comfyui.execute(context)
        config = self.comfyui.config()
        variant = KeyframeVariant(
            id=str(uuid4()),
            keyframe_id=job.related_entity_id,
            asset_id=result["asset_id"],
            source_job_id=job.id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            backend="comfyui",
            backend_settings={
                "profile": config.profile.name,
                "width": request.width,
                "height": request.height,
                "seed": request.seed,
                "steps": request.steps or config.profile.default_steps,
                "cfg": request.cfg if request.cfg is not None else config.profile.default_cfg,
            },
            source_asset_ids=request.reference_asset_ids,
            created_at=datetime.now(UTC),
        )
        store.insert_keyframe_variant(variant)
        with store.connection() as connection:
            connection.execute(
                """UPDATE keyframes SET selected_variant_id = ?, updated_at = ?
                WHERE id = ? AND selected_variant_id IS NULL""",
                (variant.id, datetime.now(UTC).isoformat(), variant.keyframe_id),
            )
        return {**result, "variant_id": variant.id}

    def select_variant(
        self, keyframe_id: str, variant_id: str, confirm: bool
    ) -> SelectVariantResponse:
        store = self._store()
        detail = self.detail(keyframe_id)
        variant = store.get_keyframe_variant(variant_id)
        if variant is None or variant.keyframe_id != keyframe_id:
            raise BeatweaveError(
                "keyframe_variant_not_found", "The keyframe variant was not found.", status_code=404
            )
        if detail.keyframe.selected_variant_id == variant_id:
            return SelectVariantResponse(
                detail=detail, timeline=TimelineService(self.projects).current(), stale_scene_ids=[]
            )
        affected = detail.affected_render_scene_ids
        if affected and not confirm:
            raise BeatweaveError(
                "keyframe_variant_affects_renders",
                "Changing this shared keyframe will make rendered adjacent scenes stale.",
                status_code=409,
                details={"scene_ids": affected},
            )
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            connection.execute(
                "UPDATE keyframes SET selected_variant_id = ?, updated_at = ? WHERE id = ?",
                (variant_id, now, keyframe_id),
            )
            if affected:
                placeholders = ",".join("?" for _ in affected)
                connection.execute(
                    "UPDATE scenes SET selected_video_take_stale = 1, "
                    f"updated_at = ? WHERE id IN ({placeholders})",
                    (now, *affected),
                )
        return SelectVariantResponse(
            detail=self.detail(keyframe_id),
            timeline=TimelineService(self.projects).current(),
            stale_scene_ids=affected,
        )

    def _store(self) -> ProjectStore:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        return ProjectStore(project.path)

    @staticmethod
    def _scene_prompt(timeline, keyframe_id: str) -> str:
        ending = next(
            (scene for scene in timeline.scenes if scene.end_keyframe_id == keyframe_id), None
        )
        if ending and ending.image_prompt:
            return ending.image_prompt
        starting = next(
            (scene for scene in timeline.scenes if scene.start_keyframe_id == keyframe_id), None
        )
        return starting.image_prompt if starting else ""

    @staticmethod
    def _previous_selected_asset(timeline, store: ProjectStore, keyframe_id: str) -> str | None:
        incoming = next(
            (scene for scene in timeline.scenes if scene.end_keyframe_id == keyframe_id), None
        )
        if incoming is None:
            return None
        previous = next(
            (item for item in timeline.keyframes if item.id == incoming.start_keyframe_id), None
        )
        if previous is None or previous.selected_variant_id is None:
            return None
        variant = store.get_keyframe_variant(previous.selected_variant_id)
        return variant.asset_id if variant else None

    @staticmethod
    def _safe_asset_path(store: ProjectStore, relative_path: str) -> Path:
        path = (store.directory / relative_path).resolve()
        if store.directory not in path.parents or not path.is_file():
            raise BeatweaveError(
                "asset_file_missing", "The generated image file is missing.", status_code=404
            )
        return path
