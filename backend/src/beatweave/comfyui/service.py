import mimetypes
from datetime import UTC, datetime
from uuid import uuid4

from beatweave.comfyui.adapter import ComfyUIAdapter
from beatweave.comfyui.schemas import (
    ComfyUIConfig,
    ComfyUIConfigUpdate,
    ComfyUIStatus,
    ImageRenderRequest,
)
from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import Job, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.service import file_sha256
from beatweave.models import ApplicationSettingRecord
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore

COMFYUI_CONFIG_KEY = "comfyui_config"


class ComfyUIService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.projects = ProjectService(database)

    def config(self) -> ComfyUIConfig:
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, COMFYUI_CONFIG_KEY)
        return (
            ComfyUIConfig.model_validate_json(setting.value)
            if setting is not None
            else ComfyUIConfig()
        )

    def update_config(self, update: ComfyUIConfigUpdate) -> ComfyUIConfig:
        config = ComfyUIConfig.model_validate(update.model_dump())
        with self.database.session() as session:
            setting = session.get(ApplicationSettingRecord, COMFYUI_CONFIG_KEY)
            if setting is None:
                session.add(
                    ApplicationSettingRecord(
                        key=COMFYUI_CONFIG_KEY,
                        value=config.model_dump_json(),
                    )
                )
            else:
                setting.value = config.model_dump_json()
        return config

    def status(self) -> ComfyUIStatus:
        return ComfyUIAdapter(self.config()).status()

    def start_render(self, request: ImageRenderRequest) -> tuple[Job, str]:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        now = datetime.now(UTC)
        job = Job(
            id=str(uuid4()),
            type=JobType.KEYFRAME_RENDER,
            state=JobState.QUEUED,
            progress=0,
            project_id=project.id,
            related_entity_type=request.related_entity_type,
            related_entity_id=request.related_entity_id,
            backend="comfyui",
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
            raise BeatweaveError("job_not_found", "The render job was not found.", status_code=404)
        request = ImageRenderRequest.model_validate(job.output.get("request"))
        reference_paths = []
        for asset_id in request.reference_asset_ids:
            asset = store.get_asset(asset_id)
            if asset is None:
                raise BeatweaveError(
                    "reference_asset_missing",
                    "A reference image for this render no longer exists.",
                    status_code=404,
                    details={"asset_id": asset_id},
                )
            path = (store.directory / asset.relative_path).resolve()
            if store.directory not in path.parents or not path.is_file():
                raise BeatweaveError(
                    "reference_file_missing",
                    "A reference image file for this render is missing.",
                    status_code=404,
                    details={"asset_id": asset_id},
                )
            reference_paths.append(path)
        result = ComfyUIAdapter(self.config()).render(request, context, reference_paths)
        image = result.pop("image_bytes")
        destination = store.directory / "keyframes" / f"{request.output_name}-{uuid4()}.png"
        temporary = destination.with_suffix(".png.partial")
        try:
            temporary.write_bytes(image)
            temporary.replace(destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise BeatweaveError(
                "comfyui_output_copy_failed",
                "The generated image could not be copied into the project.",
            ) from error
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_image",
            relative_path=destination.relative_to(store.directory).as_posix(),
            filename=destination.name,
            mime_type=mimetypes.guess_type(destination.name)[0],
            sha256=file_sha256(destination),
            size_bytes=destination.stat().st_size,
            media_metadata={
                "width": request.width,
                "height": request.height,
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "backend": "comfyui",
                "profile": self.config().profile.name,
                "settings": {
                    "seed": request.seed,
                    "steps": request.steps or self.config().profile.default_steps,
                    "cfg": request.cfg
                    if request.cfg is not None
                    else self.config().profile.default_cfg,
                },
                "reference_asset_ids": request.reference_asset_ids,
            },
            created_at=datetime.now(UTC),
        )
        try:
            store.insert_asset(asset)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {
            **result,
            "asset_id": asset.id,
            "relative_path": asset.relative_path,
        }
