from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from beatweave.analysis.beat import BeatThisDetector
from beatweave.analysis.schemas import AnalysisJob, AudioAnalysis
from beatweave.analysis.service import AnalysisService
from beatweave.config import Settings
from beatweave.database import Database
from beatweave.jobs.worker import JobManager
from beatweave.media.process import MediaProcessRunner
from beatweave.project.service import ProjectService

router = APIRouter(prefix="/analysis", tags=["analysis"])


def service(request: Request) -> AnalysisService:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    return AnalysisService(
        ProjectService(database),
        MediaProcessRunner(settings.ffmpeg_path, settings.ffprobe_path),
        BeatThisDetector(
            settings.beat_this_model,
            settings.beat_this_device,
            settings.resolved_beat_this_model_directory,
        ),
    )


AnalysisServiceDep = Annotated[AnalysisService, Depends(service)]


@router.post("", response_model=AnalysisJob, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(
    request: Request,
    analysis_service: AnalysisServiceDep,
    force: bool = Query(default=False),
) -> AnalysisJob:
    job, project_path = analysis_service.start(force=force)
    manager: JobManager = request.app.state.job_manager
    manager.publish_created(job)
    if job.state.value == "queued":
        manager.submit(project_path, job.id, analysis_service.execute)
    return job


@router.get("", response_model=AudioAnalysis | None)
def current_analysis(analysis_service: AnalysisServiceDep) -> AudioAnalysis | None:
    return analysis_service.current_analysis()


@router.get("/jobs/{job_id}", response_model=AnalysisJob)
def analysis_job(job_id: str, analysis_service: AnalysisServiceDep) -> AnalysisJob:
    return analysis_service.get_job(job_id)
