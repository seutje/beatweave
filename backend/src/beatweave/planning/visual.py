from datetime import UTC, datetime
from pathlib import Path

from beatweave.errors import BeatweaveError
from beatweave.llm.provider import LLMProvider
from beatweave.llm.schemas import (
    ScenePlan,
    ScenePlanItem,
    StructuredGenerationRequest,
    VisualPlan,
)
from beatweave.planning.schemas import (
    ScenePlanningContext,
    StyleReferenceSummary,
    TrackAnalysisSummary,
    VisualPlanningContext,
    VisualPlanningResult,
)
from beatweave.project.schemas import VisualTrajectoryStage
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.service import TimelineService

SCENE_PLAN_BATCH_SIZE = 3


class VisualPlanningService:
    def __init__(self, projects: ProjectService, provider: LLMProvider) -> None:
        self.projects = projects
        self.provider = provider

    def context(self, scene_id: str | None = None) -> VisualPlanningContext:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        if project.audio_asset_id is None:
            raise BeatweaveError("audio_not_imported", "Import audio first.", status_code=409)
        store = ProjectStore(Path(project.path))
        asset = store.get_asset(project.audio_asset_id)
        analysis = store.find_analysis_by_hash(asset.sha256) if asset else None
        if asset is None or analysis is None:
            raise BeatweaveError(
                "analysis_required",
                "Analyze the track before generating a visual plan.",
                status_code=409,
            )
        timeline = TimelineService(self.projects).current()
        if not timeline.scenes:
            raise BeatweaveError(
                "timeline_required",
                "Create a scene layout before generating a visual plan.",
                status_code=409,
            )
        scenes = timeline.scenes
        if scene_id is not None:
            scenes = [scene for scene in scenes if scene.id == scene_id]
            if not scenes:
                raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
        values = [sample.value for sample in analysis.energy_curve]
        scene_contexts = []
        for scene in scenes:
            samples = [
                sample.value
                for sample in analysis.energy_curve
                if scene.start_time <= sample.time <= scene.end_time
            ]
            scene_contexts.append(
                ScenePlanningContext(
                    scene_id=scene.id,
                    position=scene.position,
                    start_time=scene.start_time,
                    end_time=scene.end_time,
                    duration_seconds=scene.end_time - scene.start_time,
                    average_energy=sum(samples) / len(samples) if samples else 0,
                    peak_energy=max(samples, default=0),
                )
            )
        return VisualPlanningContext(
            creative_brief=project.creative_brief,
            track=TrackAnalysisSummary(
                duration_seconds=timeline.duration_seconds,
                bpm_estimate=analysis.bpm_estimate,
                beat_count=len(analysis.beats),
                downbeat_count=len(analysis.downbeats),
                average_energy=sum(values) / len(values) if values else 0,
                peak_energy=max(values, default=0),
            ),
            scenes=scene_contexts,
            style_references=[
                StyleReferenceSummary(
                    filename=reference.filename,
                    mime_type=reference.mime_type,
                    size_bytes=reference.size_bytes,
                )
                for reference in store.list_style_references()
            ],
        )

    def generate(self, *, confirm_overwrite: bool) -> VisualPlanningResult:
        context = self.context()
        self._require_overwrite_confirmation(
            [scene.scene_id for scene in context.scenes], confirm_overwrite
        )
        try:
            visual = self.provider.generate_structured(
                StructuredGenerationRequest(
                    system_prompt=self._visual_system_prompt(),
                    user_prompt=context.model_dump_json(),
                    temperature=0.7,
                ),
                VisualPlan,
            ).output
            scene_brief = context.creative_brief.model_copy(
                update={"visual_trajectory": visual.visual_trajectory}
            )
            planned_scenes: list[ScenePlanItem] = []
            for start in range(0, len(context.scenes), SCENE_PLAN_BATCH_SIZE):
                batch = context.scenes[start : start + SCENE_PLAN_BATCH_SIZE]
                batch_context = context.model_copy(
                    update={"creative_brief": scene_brief, "scenes": batch}
                )
                batch_plan = self.provider.generate_structured(
                    StructuredGenerationRequest(
                        system_prompt=self._scene_system_prompt(),
                        user_prompt=batch_context.model_dump_json(),
                        temperature=0.7,
                    ),
                    ScenePlan,
                ).output
                self._validate_scene_plan(batch_plan, [scene.scene_id for scene in batch])
                planned_scenes.extend(batch_plan.scenes)
            return self._persist(ScenePlan(scenes=planned_scenes), visual)
        finally:
            self.provider.release()

    def regenerate_scene(self, scene_id: str, *, confirm_overwrite: bool) -> VisualPlanningResult:
        context = self.context(scene_id)
        self._require_overwrite_confirmation([scene_id], confirm_overwrite)
        try:
            plan = self.provider.generate_structured(
                StructuredGenerationRequest(
                    system_prompt=self._scene_system_prompt(),
                    user_prompt=context.model_dump_json(),
                    temperature=0.7,
                ),
                ScenePlan,
            ).output
            self._validate_scene_plan(plan, [scene_id])
            return self._persist(plan, None)
        finally:
            self.provider.release()

    def _require_overwrite_confirmation(self, scene_ids: list[str], confirmed: bool) -> None:
        if confirmed:
            return
        project = self.projects.current()
        assert project is not None
        store = ProjectStore(Path(project.path))
        placeholders = ",".join("?" for _ in scene_ids)
        with store.connection() as connection:
            existing = connection.execute(
                f"""SELECT scenes.id FROM scenes
                JOIN keyframes ON keyframes.id = scenes.start_keyframe_id
                WHERE scenes.id IN ({placeholders}) AND
                (scenes.concept != '' OR scenes.image_prompt != '' OR
                 scenes.video_prompt != '' OR keyframes.prompt != '') LIMIT 1""",  # noqa: S608
                scene_ids,
            ).fetchone()
        if existing is not None:
            raise BeatweaveError(
                "overwrite_confirmation_required",
                "Generated content would overwrite existing scene or starting-keyframe text. "
                "Confirm before continuing.",
                status_code=409,
            )

    @staticmethod
    def _validate_scene_plan(plan: ScenePlan, expected_ids: list[str]) -> None:
        actual = [scene.scene_id for scene in plan.scenes]
        if len(actual) != len(set(actual)) or set(actual) != set(expected_ids):
            raise BeatweaveError(
                "invalid_scene_plan",
                "The provider returned scenes that do not match the timeline.",
                status_code=422,
            )

    def _persist(
        self, scene_plan: ScenePlan, visual_plan: VisualPlan | None
    ) -> VisualPlanningResult:
        project = self.projects.current()
        assert project is not None
        store = ProjectStore(Path(project.path))
        timeline_service = TimelineService(self.projects)
        now = datetime.now(UTC)
        updated_project = project
        if visual_plan is not None:
            trajectory = [
                VisualTrajectoryStage.model_validate(stage.model_dump())
                for stage in visual_plan.visual_trajectory
            ]
            updated_project = project.model_copy(
                update={
                    "creative_brief": project.creative_brief.model_copy(
                        update={"visual_trajectory": trajectory}
                    ),
                    "updated_at": now,
                }
            )
        with store.connection() as connection:
            before = timeline_service._snapshot(connection)
            if visual_plan is not None:
                connection.execute(
                    """UPDATE project_metadata
                    SET updated_at = ?, creative_brief_json = ? WHERE id = ?""",
                    (
                        now.isoformat(),
                        updated_project.creative_brief.model_dump_json(),
                        updated_project.id,
                    ),
                )
            for scene in scene_plan.scenes:
                self._update_scene(connection, scene, now.isoformat())
            timeline_service._record_history(
                connection,
                "generate_visual_plan" if visual_plan else "regenerate_scene",
                before,
                timeline_service._snapshot(connection),
                now.isoformat(),
            )
        self.projects._remember(updated_project)
        return VisualPlanningResult(
            project=updated_project,
            timeline=timeline_service.current(),
        )

    @staticmethod
    def _update_scene(connection: object, scene: ScenePlanItem, now: str) -> None:
        connection.execute(
            """UPDATE scenes SET concept = ?, image_prompt = ?, video_prompt = ?,
            visual_energy = ?, motion_energy = ?, updated_at = ? WHERE id = ?""",
            (
                scene.concept,
                scene.image_prompt,
                scene.video_prompt,
                scene.visual_energy,
                scene.motion_energy,
                now,
                scene.scene_id,
            ),
        )
        connection.execute(
            """UPDATE keyframes SET prompt = ?, updated_at = ?
            WHERE id = (SELECT start_keyframe_id FROM scenes WHERE id = ?)""",
            (scene.image_prompt, now, scene.scene_id),
        )

    @staticmethod
    def _visual_system_prompt() -> str:
        return (
            "Create a coherent abstract visual plan as JSON matching the VisualPlan schema. "
            "Use the supplied brief, music summary, scene timing, energy, and reference metadata. "
            "Create 3 to 8 visual_trajectory stages. Every stage must include a concise "
            "description, a normalized position from 0 to 1 spanning the track, and an intensity "
            "from 0 to 1. "
            "Do not emit IDs, file paths, renderer graphs, node IDs, or backend settings."
        )

    @staticmethod
    def _scene_system_prompt() -> str:
        return (
            "Create JSON matching ScenePlan. Return exactly one item for every supplied scene_id. "
            "Keep those IDs unchanged. Timing is context only and must not appear in output. "
            "Separate "
            "the destination still-image prompt from the motion/video prompt. Do not emit renderer "
            "graphs, node IDs, filenames, or backend settings."
        )
