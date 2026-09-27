import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from beatweave import __version__
from beatweave.config import Settings, get_settings
from beatweave.database import Database
from beatweave.errors import BeatweaveError
from beatweave.logging import configure_logging
from beatweave.project.api import router as project_router
from beatweave.schemas import ErrorDetail, ErrorResponse, EventMessage, HealthResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    database = Database(app_settings.resolved_database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("Initializing database at %s", database.path)
        database.initialize()
        yield
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
    app.include_router(project_router)

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
            while True:
                await websocket.receive_text()
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
