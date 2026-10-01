import json
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from beatweave.errors import BeatweaveError

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ApplicationLogEntry(BaseModel):
    timestamp: datetime
    level: str
    logger: str
    message: str
    exception: str | None = None


class ApplicationLogResponse(BaseModel):
    path: str
    entries: list[ApplicationLogEntry] = Field(default_factory=list)


def _log_path(request: Request) -> Path:
    return request.app.state.settings.resolved_log_path


@router.get("/logs", response_model=ApplicationLogResponse)
def application_logs(
    request: Request, limit: int = Query(default=200, ge=1, le=1000)
) -> ApplicationLogResponse:
    path = _log_path(request)
    if not path.is_file():
        return ApplicationLogResponse(path=str(path))
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            lines.append(line)
    entries = []
    for line in lines:
        try:
            entries.append(ApplicationLogEntry.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            continue
    return ApplicationLogResponse(path=str(path), entries=entries)


@router.get("/logs/export")
def export_application_logs(request: Request) -> FileResponse:
    path = _log_path(request)
    if not path.is_file():
        raise BeatweaveError(
            "application_log_missing", "No application log exists yet.", status_code=404
        )
    return FileResponse(path, media_type="application/x-ndjson", filename=path.name)
