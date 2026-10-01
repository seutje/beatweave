import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from beatweave import __version__
from beatweave.analysis.api import router as analysis_router
from beatweave.comfyui.api import router as comfyui_router
from beatweave.config import Settings, get_settings
from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.jobs.api import router as jobs_router
from beatweave.jobs.events import EventBroker
from beatweave.jobs.schemas import JobType
from beatweave.jobs.worker import JobManager
from beatweave.keyframes.api import router as keyframes_router
from beatweave.keyframes.service import KeyframeService
from beatweave.llm.api import router as llm_router
from beatweave.logging import configure_logging
from beatweave.media.api import router as media_router
from beatweave.media.process import MediaProcessRunner
from beatweave.planning.api import router as planning_router
from beatweave.project.api import router as project_router
from beatweave.project.service import ProjectService
from beatweave.schemas import ErrorDetail, ErrorResponse, EventMessage, HealthResponse
from beatweave.timeline.api import router as timeline_router
from beatweave.video_takes.api import router as video_takes_router
from beatweave.wan2gp.api import router as wan2gp_router
from beatweave.wan2gp.service import Wan2GPService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    database = Database(app_settings.resolved_database_path)
    event_broker = EventBroker()
    job_manager = JobManager(event_broker)

    def analysis_handler(_: object):
        from beatweave.analysis.beat import BeatThisDetector
        from beatweave.analysis.service import AnalysisService

        service = AnalysisService(
            ProjectService(database),
            MediaProcessRunner(app_settings.ffmpeg_path, app_settings.ffprobe_path),
            BeatThisDetector(
                app_settings.beat_this_model,
                app_settings.beat_this_device,
                app_settings.resolved_beat_this_model_directory,
            ),
        )
        return service.execute

    job_manager.register(JobType.AUDIO_ANALYSIS, analysis_handler)
    job_manager.register(JobType.KEYFRAME_RENDER, lambda _: KeyframeService(database).execute)
    job_manager.register(JobType.VIDEO_RENDER, lambda _: Wan2GPService(database).execute)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("Initializing database at %s", database.path)
        database.initialize()
        event_broker.bind(asyncio.get_running_loop())
        job_manager.start()
        try:
            current = ProjectService(database).current()
            if current is not None:
                job_manager.reconcile(current.path)
        except BeatweaveError:
            logger.warning("Could not reconcile jobs for the current project", exc_info=True)
        yield
        job_manager.stop()
        database.close()
        logger.info("Beatweave backend stopped")

    app = FastAPI(title=app_settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = app_settings
    app.state.database = database
    app.state.events = event_broker
    app.state.job_manager = job_manager
    app.include_router(project_router)
    app.include_router(media_router)
    app.include_router(analysis_router)
    app.include_router(timeline_router)
    app.include_router(llm_router)
    app.include_router(planning_router)
    app.include_router(jobs_router)
    app.include_router(comfyui_router)
    app.include_router(keyframes_router)
    app.include_router(wan2gp_router)
    app.include_router(video_takes_router)

    @app.exception_handler(BeatweaveError)
    async def beatweave_error_handler(_: Request, exc: BeatweaveError) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="The request was invalid.",
                details={"errors": exc.errors()},
            )
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error", exc_info=exc)
        response = ErrorResponse(
            error=ErrorDetail(code="internal_error", message="An internal error occurred.")
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.websocket("/events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json(EventMessage(type="connected").model_dump(mode="json"))
        try:
            async for event in event_broker.subscribe():
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            logger.debug("Event client disconnected")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "beatweave.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
