import logging
import statistics
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from beatweave.analysis.beat import BeatDetector
from beatweave.analysis.energy import EnergyAnalyzer
from beatweave.analysis.schemas import AnalysisJob, AnalysisParameters, AudioAnalysis
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import Job, JobError, JobState, JobType
from beatweave.jobs.worker import JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.project.schemas import AssetMetadata, Project
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore

logger = logging.getLogger(__name__)
ANALYSIS_LOCK = threading.Lock()


class AnalysisService:
    def __init__(
        self,
        projects: ProjectService,
        media_runner: MediaProcessRunner,
        beat_detector: BeatDetector,
        energy_analyzer: EnergyAnalyzer | None = None,
    ) -> None:
        self.projects = projects
        self.media_runner = media_runner
        self.beat_detector = beat_detector
        self.energy_analyzer = energy_analyzer or EnergyAnalyzer()

    def start(self, *, force: bool = False) -> tuple[AnalysisJob, str]:
        project, asset = self._current_audio()
        store = ProjectStore(Path(project.path))
        cached = None if force else store.find_analysis_by_hash(asset.sha256)
        now = datetime.now(UTC)
        job = Job(
            id=str(uuid4()),
            type=JobType.AUDIO_ANALYSIS,
            state=JobState.COMPLETE if cached else JobState.QUEUED,
            progress=1 if cached else 0,
            project_id=project.id,
            related_entity_type="asset",
            related_entity_id=asset.id,
            backend=self.beat_detector.name,
            output={"analysis_id": cached.id, "cached": True} if cached else {},
            created_at=now,
            updated_at=now,
            completed_at=now if cached else None,
        )
        store.insert_job(job)
        return job, project.path

    def run(self, job_id: str, project_path: str) -> None:
        """Run synchronously for compatibility with direct service callers."""
        store = ProjectStore(Path(project_path))
        job = store.get_job(job_id)
        if job is None or job.state == JobState.COMPLETE:
            return
        with ANALYSIS_LOCK:
            try:
                self._update_job(store, job, state=JobState.RUNNING, progress=0.05, started=True)
                output = self._perform(
                    store,
                    job,
                    lambda progress: self._update_job(
                        store, job, state=JobState.RUNNING, progress=progress
                    ),
                )
                self._update_job(
                    store,
                    job,
                    state=JobState.COMPLETE,
                    progress=1,
                    output=output,
                    completed=True,
                )
            except Exception as error:
                logger.exception("Audio analysis job %s failed", job_id)
                error_payload = {
                    "code": getattr(error, "code", "analysis_failed"),
                    "message": getattr(error, "message", str(error)),
                }
                self._update_job(
                    store,
                    job,
                    state=JobState.FAILED,
                    progress=job.progress,
                    error=error_payload,
                    completed=True,
                )

    def execute(self, context: JobContext) -> dict:
        store = ProjectStore(context.project_path)
        job = store.get_job(context.job_id)
        if job is None:
            raise BeatweaveError(
                "job_not_found", "The analysis job was not found.", status_code=404
            )
        with ANALYSIS_LOCK:
            try:
                return self._perform(store, job, context.report)
            except BeatweaveError:
                raise
            except Exception as error:
                raise BeatweaveError("analysis_failed", str(error)) from error

    def _perform(self, store: ProjectStore, job: Job, report: Callable[[float], object]) -> dict:
        if job.related_entity_id is None:
            raise BeatweaveError("audio_asset_missing", "The analysis job has no audio asset.")
        asset = store.get_asset(job.related_entity_id)
        if asset is None:
            raise BeatweaveError(
                "audio_asset_missing",
                "The audio asset for this analysis job no longer exists.",
                status_code=404,
            )
        audio_path = self._asset_path(store, asset)
        beats, downbeats = self.beat_detector.detect(audio_path)
        self._validate_timestamps(beats, downbeats)
        report(0.5)

        energy_settings = self.energy_analyzer.settings
        raw = self.media_runner.decode_mono_f32(audio_path, energy_settings.sample_rate)
        samples = np.frombuffer(raw, dtype="<f4").copy()
        energy_curve = self.energy_analyzer.analyze(samples)
        report(0.9)

        analysis = AudioAnalysis(
            id=str(uuid4()),
            asset_id=asset.id,
            source_sha256=asset.sha256,
            bpm_estimate=self._estimate_bpm(beats),
            beats=beats,
            downbeats=downbeats,
            energy_curve=energy_curve,
            parameters=AnalysisParameters(
                beat_analyzer=self.beat_detector.name,
                beat_model=self.beat_detector.model_name,
                beat_device=self.beat_detector.resolved_device,
                energy_sample_rate=energy_settings.sample_rate,
                frame_length=energy_settings.frame_length,
                hop_length=energy_settings.hop_length,
                energy_weights=energy_settings.weights,
                normalization_percentiles=(
                    energy_settings.lower_percentile,
                    energy_settings.upper_percentile,
                ),
            ),
            created_at=datetime.now(UTC),
        )
        store.insert_analysis(analysis)
        return {"analysis_id": analysis.id, "cached": False}

    @staticmethod
    def _update_job(
        store: ProjectStore,
        job: AnalysisJob,
        *,
        state: JobState,
        progress: float,
        output: dict | None = None,
        error: dict | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        job.state = state
        job.progress = progress
        job.updated_at = datetime.now(UTC)
        if output is not None:
            job.output = output
        if error is not None:
            job.error = JobError.model_validate(error)
        if started:
            job.started_at = datetime.now(UTC)
        if completed:
            job.completed_at = datetime.now(UTC)
        store.update_job(job)

    def current_analysis(self) -> AudioAnalysis | None:
        project, asset = self._current_audio()
        return ProjectStore(Path(project.path)).find_analysis_by_hash(asset.sha256)

    def get_job(self, job_id: str) -> AnalysisJob:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        job = ProjectStore(Path(project.path)).get_job(job_id)
        if job is None:
            raise BeatweaveError(
                "job_not_found", "The analysis job was not found.", status_code=404
            )
        return job

    def _current_audio(self) -> tuple[Project, AssetMetadata]:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "No project is open.", status_code=409)
        if project.audio_asset_id is None:
            raise BeatweaveError(
                "audio_not_imported", "Import a track before starting analysis.", status_code=409
            )
        asset = ProjectStore(Path(project.path)).get_asset(project.audio_asset_id)
        if asset is None:
            raise BeatweaveError(
                "audio_asset_missing", "The audio asset is missing.", status_code=404
            )
        return project, asset

    @staticmethod
    def _asset_path(store: ProjectStore, asset: AssetMetadata) -> Path:
        path = (store.directory / asset.relative_path).resolve()
        if store.directory not in path.parents or not path.is_file():
            raise BeatweaveError(
                "asset_file_missing", "The audio file is missing.", status_code=404
            )
        return path

    @staticmethod
    def _validate_timestamps(beats: list[float], downbeats: list[float]) -> None:
        for name, timestamps in (("beats", beats), ("downbeats", downbeats)):
            if any(value < 0 for value in timestamps) or any(
                current <= previous
                for previous, current in zip(timestamps, timestamps[1:], strict=False)
            ):
                raise BeatweaveError(
                    "invalid_beat_timestamps",
                    f"Beat This returned invalid {name} timestamps.",
                    status_code=422,
                )

    @staticmethod
    def _estimate_bpm(beats: list[float]) -> float | None:
        if len(beats) < 2:
            return None
        intervals = [
            current - previous for previous, current in zip(beats, beats[1:], strict=False)
        ]
        median_interval = statistics.median(intervals)
        return round(60 / median_interval, 3) if median_interval > 0 else None
