import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.store import PROJECT_DIRECTORIES


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
        project_directory = projects_directory / "Glass Tides"
        assert Path(project["path"]) == project_directory
        assert (project_directory / "project.db").is_file()
        assert all((project_directory / name).is_dir() for name in PROJECT_DIRECTORIES)

        update_response = client.patch(
            f"/projects/{project['id']}",
            json={
                "name": "Glass Tides Edit",
                "creative_brief": {"concept": "Order becomes liquid", "style": "Prismatic"},
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

    with sqlite3.connect(project_directory / "project.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
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


def test_open_missing_project_returns_structured_error(tmp_path: Path) -> None:
    with client_for(tmp_path / "application.db") as client:
        response = client.post("/projects/open", json={"path": str(tmp_path / "missing")})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_directory_missing"
