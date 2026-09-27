from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from beatweave.database import Database
from beatweave.project.schemas import (
    CloseProjectResponse,
    CreateProjectRequest,
    OpenProjectRequest,
    Project,
    RecentProject,
    UpdateProjectRequest,
)
from beatweave.project.service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def service(request: Request) -> ProjectService:
    database: Database = request.app.state.database
    return ProjectService(database)


ProjectServiceDep = Annotated[ProjectService, Depends(service)]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(body: CreateProjectRequest, project_service: ProjectServiceDep) -> Project:
    return project_service.create(body)


@router.get("/recent", response_model=list[RecentProject])
def recent_projects(project_service: ProjectServiceDep) -> list[RecentProject]:
    return project_service.recent()


@router.post("/open", response_model=Project)
def open_project(body: OpenProjectRequest, project_service: ProjectServiceDep) -> Project:
    return project_service.open(body.path)


@router.get("/current", response_model=Project | None)
def current_project(project_service: ProjectServiceDep) -> Project | None:
    return project_service.current()


@router.post("/close", response_model=CloseProjectResponse)
def close_project(project_service: ProjectServiceDep) -> CloseProjectResponse:
    project_service.close()
    return CloseProjectResponse()


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    project_service: ProjectServiceDep,
) -> Project:
    return project_service.update(project_id, body)
