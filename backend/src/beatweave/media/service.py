import hashlib
import math
import mimetypes
from array import array
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.errors import BeatweaveError
from beatweave.media.process import MediaProcessRunner
from beatweave.media.schemas import AudioImportResponse, MediaMetadata, WaveformData
from beatweave.project.schemas import AssetMetadata, Project
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore

SUPPORTED_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
WAVEFORM_SAMPLE_RATE = 8000
WAVEFORM_PEAK_COUNT = 2000


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class MediaService:
    def __init__(self, projects: ProjectService, runner: MediaProcessRunner) -> None:
        self.projects = projects
        self.runner = runner

    def import_audio(self, path_value: str) -> AudioImportResponse:
        project = self._current_project()
        source_path = Path(path_value).expanduser().resolve()
        if not source_path.is_file():
            raise BeatweaveError(
                "audio_file_missing",
                "The selected audio file does not exist.",
                status_code=404,
                details={"path": str(source_path)},
            )
        if source_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            raise BeatweaveError(
                "audio_format_unsupported",
                "The selected audio format is not supported.",
                status_code=415,
                details={"suffix": source_path.suffix.lower()},
            )

        metadata = self.runner.probe_audio(source_path)
        sha256 = file_sha256(source_path)
        store = ProjectStore(Path(project.path))
        existing = store.find_asset_by_hash(sha256, "audio")
        if existing is not None:
            waveform = self.waveform(project, existing)
            updated_project = self.projects.set_audio_asset(project, existing.id)
            return AudioImportResponse(project=updated_project, asset=existing, waveform=waveform)

        destination = self._available_destination(store.directory / "source", source_path, sha256)
        with source_path.open("rb") as source, destination.open("xb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if file_sha256(destination) != sha256:
            destination.unlink(missing_ok=True)
            raise BeatweaveError(
                "audio_copy_failed",
                "The imported copy did not match the source audio.",
                status_code=500,
            )

        asset = AssetMetadata(
            id=str(uuid4()),
            kind="audio",
            relative_path=destination.relative_to(store.directory).as_posix(),
            original_path=str(source_path),
            filename=source_path.name,
            mime_type=mimetypes.guess_type(source_path.name)[0],
            sha256=sha256,
            size_bytes=destination.stat().st_size,
            media_metadata=metadata.model_dump(mode="json"),
            created_at=datetime.now(UTC),
        )
        store.insert_asset(asset)
        waveform = self.waveform(project, asset, metadata)
        updated_project = self.projects.set_audio_asset(project, asset.id)
        return AudioImportResponse(project=updated_project, asset=asset, waveform=waveform)

    def waveform(
        self,
        project: Project,
        asset: AssetMetadata,
        metadata: MediaMetadata | None = None,
    ) -> WaveformData:
        store = ProjectStore(Path(project.path))
        cache_path = store.directory / "cache" / "waveforms" / f"{asset.sha256}.json"
        if cache_path.is_file():
            cached = WaveformData.model_validate_json(cache_path.read_text(encoding="utf-8"))
            if cached.source_sha256 == asset.sha256:
                return cached

        source_path = self.asset_path(project, asset)
        media_metadata = metadata or MediaMetadata.model_validate(asset.media_metadata)
        samples = array("f")
        samples.frombytes(self.runner.decode_mono_f32(source_path, WAVEFORM_SAMPLE_RATE))
        peaks = self._peaks(samples, WAVEFORM_PEAK_COUNT)
        waveform = WaveformData(
            source_sha256=asset.sha256,
            sample_rate=WAVEFORM_SAMPLE_RATE,
            duration_seconds=media_metadata.duration_seconds,
            peaks=peaks,
            generated_at=datetime.now(UTC),
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(waveform.model_dump_json(), encoding="utf-8")
        return waveform

    def current_audio(self) -> tuple[Project, AssetMetadata]:
        project = self._current_project()
        if project.audio_asset_id is None:
            raise BeatweaveError(
                "audio_not_imported",
                "The current project does not have an imported track.",
                status_code=404,
            )
        asset = ProjectStore(Path(project.path)).get_asset(project.audio_asset_id)
        if asset is None:
            raise BeatweaveError(
                "audio_asset_missing",
                "The imported audio record is missing from the project.",
                status_code=404,
            )
        return project, asset

    def asset_path(self, project: Project, asset: AssetMetadata) -> Path:
        project_directory = Path(project.path).resolve()
        path = (project_directory / asset.relative_path).resolve()
        if project_directory not in path.parents or not path.is_file():
            raise BeatweaveError(
                "asset_file_missing",
                "The audio file is missing from the project.",
                status_code=404,
                details={"path": str(path)},
            )
        return path

    def _current_project(self) -> Project:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError(
                "project_not_open", "Open a project before importing audio.", status_code=409
            )
        return project

    @staticmethod
    def _available_destination(directory: Path, source: Path, sha256: str) -> Path:
        safe_stem = (
            "".join(
                character if character.isalnum() or character in {"-", "_"} else "-"
                for character in source.stem
            ).strip("-")
            or "track"
        )
        filename = f"{safe_stem}-{sha256[:12]}{source.suffix.lower()}"
        destination = directory / filename
        if destination.exists():
            raise BeatweaveError(
                "audio_destination_exists",
                "The project already contains a different file at the import destination.",
                status_code=409,
                details={"path": str(destination)},
            )
        return destination

    @staticmethod
    def _peaks(samples: array[float], count: int) -> list[float]:
        if not samples:
            return []
        bucket_size = max(1, math.ceil(len(samples) / count))
        return [
            round(min(1.0, max(abs(value) for value in samples[start : start + bucket_size])), 6)
            for start in range(0, len(samples), bucket_size)
        ]
