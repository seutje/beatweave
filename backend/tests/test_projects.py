import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.service import ProjectService
from beatweave.project.store import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    PROJECT_DIRECTORIES,
    ProjectStore,
)


def client_for(database_path: Path) -> TestClient:
    return TestClient(create_app(Settings(database_path=database_path)))


def test_create_update_close_and_reopen_project(tmp_path: Path) -> None:
    application_database = tmp_path / "application.db"
    projects_directory = tmp_path / "projects"
    projects_directory.mkdir()

    with client_for(application_database) as client:
        create_response = client.post(
            "/projects",
            json={"name": "Glass Tides", "parent_directory": str(projects_directory)},
        )
        assert create_response.status_code == 201
        project = create_response.json()
        assert project["settings"]["max_clip_length_seconds"] == 30
        project_directory = projects_directory / "Glass Tides"
        assert Path(project["path"]) == project_directory
        assert (project_directory / "project.db").is_file()
        assert all((project_directory / name).is_dir() for name in PROJECT_DIRECTORIES)

        update_response = client.patch(
            f"/projects/{project['id']}",
            json={
                "name": "Glass Tides Edit",
                "creative_brief": {
                    "concept": "Order becomes liquid",
                    "style": "Prismatic",
                    "motifs": ["glass", "tides"],
                    "palette": ["cyan", "violet"],
                    "narrative_arc": "Stillness to rupture to renewal",
                    "negative_guidance": "No text",
                    "visual_trajectory": [
                        {"position": 0.5, "description": "Fracture", "intensity": 0.8}
                    ],
                },
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["creative_brief"]["concept"] == "Order becomes liquid"

        assert client.post("/projects/close").json() == {"status": "closed"}
        assert client.get("/projects/current").json() is None

    with client_for(application_database) as restarted_client:
        recent = restarted_client.get("/projects/recent").json()
        assert recent[0]["name"] == "Glass Tides Edit"
        assert recent[0]["exists"] is True

        opened = restarted_client.post("/projects/open", json={"path": str(project_directory)})
        assert opened.status_code == 200
        assert opened.json()["id"] == project["id"]
        assert opened.json()["creative_brief"]["style"] == "Prismatic"
        assert opened.json()["creative_brief"]["motifs"] == ["glass", "tides"]
        assert opened.json()["creative_brief"]["visual_trajectory"][0]["description"] == "Fracture"

    with sqlite3.connect(project_directory / "project.db") as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_PROJECT_SCHEMA_VERSION
        )
        assert connection.execute("SELECT count(*) FROM assets").fetchone()[0] == 0


def test_create_refuses_to_overwrite_existing_directory(tmp_path: Path) -> None:
    projects_directory = tmp_path / "projects"
    existing = projects_directory / "Existing"
    existing.mkdir(parents=True)
    marker = existing / "keep.txt"
    marker.write_text("do not overwrite", encoding="utf-8")

    with client_for(tmp_path / "application.db") as client:
        response = client.post(
            "/projects",
            json={"name": "Existing", "parent_directory": str(projects_directory)},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_path_exists"
    assert marker.read_text(encoding="utf-8") == "do not overwrite"


@pytest.mark.parametrize("old_maximum, expected", [(10, 30), (18, 18), (45, 45)])
def test_clip_limit_migration_preserves_other_settings(
    tmp_path: Path, old_maximum: float, expected: float
) -> None:
    with client_for(tmp_path / "application.db") as client:
        project = client.post(
            "/projects", json={"name": "Clip Limit", "parent_directory": str(tmp_path)}
        ).json()
        store = ProjectStore(project["path"])
        with store.connection() as connection:
            connection.execute(
                "UPDATE project_metadata SET settings_json = ?",
                (json.dumps({"max_clip_length_seconds": old_maximum, "other_setting": True}),),
            )
            connection.execute("PRAGMA user_version = 11")

        opened = client.post("/projects/open", json={"path": project["path"]})
        assert opened.status_code == 200
        assert opened.json()["settings"]["max_clip_length_seconds"] == expected
        store.initialize()
        with store.connection() as connection:
            settings = json.loads(
                connection.execute("SELECT settings_json FROM project_metadata").fetchone()[0]
            )
            assert settings == {"max_clip_length_seconds": expected, "other_setting": True}
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 12
        assert list((Path(project["path"]) / "backups").glob("*.db"))


def test_open_missing_project_returns_structured_error(tmp_path: Path) -> None:
    with client_for(tmp_path / "application.db") as client:
        response = client.post("/projects/open", json={"path": str(tmp_path / "missing")})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_directory_missing"


def test_startup_recovers_when_current_project_database_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    application_database = tmp_path / "application.db"
    projects_directory = tmp_path / "projects"
    projects_directory.mkdir()

    with client_for(application_database) as client:
        response = client.post(
            "/projects",
            json={"name": "Unavailable", "parent_directory": str(projects_directory)},
        )
        assert response.status_code == 201

    def fail_to_initialize(_: ProjectStore) -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(ProjectStore, "initialize", fail_to_initialize)
    with client_for(application_database) as restarted_client:
        assert restarted_client.get("/health").status_code == 200
        assert restarted_client.get("/projects/current").json() is None
        reopen = restarted_client.post(
            "/projects/open", json={"path": str(projects_directory / "Unavailable")}
        )

    assert reopen.status_code == 422
    assert reopen.json()["error"]["code"] == "project_database_unavailable"


def test_startup_health_survives_unexpected_current_project_recovery_failure(
    tmp_path: Path, monkeypatch
) -> None:
    def fail_to_recover(_: ProjectService):
        raise RuntimeError("recovery failed")

    monkeypatch.setattr(ProjectService, "current", fail_to_recover)
    with client_for(tmp_path / "application.db") as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_polling_current_project_does_not_rewrite_registry(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "projects"
    parent.mkdir()
    with client_for(tmp_path / "app.db") as client:
        project = client.post(
            "/projects",
            json={
                "name": "Read only polling",
                "parent_directory": str(parent),
            },
        ).json()

        def unexpected_write(*_args):
            raise AssertionError("Polling must not update the recent-project registry")

        monkeypatch.setattr(ProjectService, "_remember", unexpected_write)
        for _ in range(5):
            assert client.get("/projects/current").json()["id"] == project["id"]
            assert client.get("/jobs").is_success
