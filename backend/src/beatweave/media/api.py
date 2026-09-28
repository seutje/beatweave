from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from beatweave.config import Settings
from beatweave.database import Database
from beatweave.media.process import MediaProcessRunner
from beatweave.media.schemas import (
    AudioImportResponse,
    CurrentAudioResponse,
    ImportAudioRequest,
    ImportReferenceRequest,
    WaveformData,
)
from beatweave.media.service import MediaService
from beatweave.project.schemas import AssetMetadata
from beatweave.project.service import ProjectService

router = APIRouter(prefix="/media", tags=["media"])


def service(request: Request) -> MediaService:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    return MediaService(
        ProjectService(database),
        MediaProcessRunner(settings.ffmpeg_path, settings.ffprobe_path),
    )


MediaServiceDep = Annotated[MediaService, Depends(service)]


@router.post("/audio/import", response_model=AudioImportResponse)
def import_audio(body: ImportAudioRequest, media_service: MediaServiceDep) -> AudioImportResponse:
    return media_service.import_audio(body.path)


@router.get("/audio", response_model=CurrentAudioResponse)
def current_audio(media_service: MediaServiceDep) -> CurrentAudioResponse:
    project, asset = media_service.current_audio()
    return CurrentAudioResponse(
        project=project,
        asset=asset,
        waveform=media_service.waveform(project, asset),
    )


@router.get("/audio/waveform", response_model=WaveformData)
def audio_waveform(media_service: MediaServiceDep) -> WaveformData:
    project, asset = media_service.current_audio()
    return media_service.waveform(project, asset)


@router.get("/audio/content")
def audio_content(media_service: MediaServiceDep) -> FileResponse:
    project, asset = media_service.current_audio()
    path: Path = media_service.asset_path(project, asset)
    return FileResponse(path, media_type=asset.mime_type, filename=asset.filename)


@router.post("/references", response_model=AssetMetadata)
def import_reference(body: ImportReferenceRequest, media_service: MediaServiceDep) -> AssetMetadata:
    return media_service.import_style_reference(body.path)


@router.get("/references", response_model=list[AssetMetadata])
def style_references(media_service: MediaServiceDep) -> list[AssetMetadata]:
    return media_service.style_references()


@router.get("/references/{asset_id}/content")
def reference_content(asset_id: str, media_service: MediaServiceDep) -> FileResponse:
    asset, path = media_service.style_reference_path(asset_id)
    return FileResponse(path, media_type=asset.mime_type, filename=asset.filename)


@router.delete("/references/{asset_id}")
def remove_reference(asset_id: str, media_service: MediaServiceDep) -> dict[str, str]:
    media_service.remove_style_reference(asset_id)
    return {"status": "removed"}
