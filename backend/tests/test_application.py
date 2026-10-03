import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app


def make_client(database_path: Path) -> TestClient:
    settings = Settings(data_dir=database_path.parent, database_path=database_path)
    return TestClient(create_app(settings))


def test_health_and_database_initialization(tmp_path: Path) -> None:
    database_path = tmp_path / "beatweave.db"
    with make_client(database_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "beatweave-backend",
        "version": "0.3.3",
    }
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"alembic_version", "projects", "application_settings"} <= tables


def test_database_can_be_reopened(tmp_path: Path) -> None:
    database_path = tmp_path / "beatweave.db"
    for _ in range(2):
        with make_client(database_path) as client:
            assert client.get("/health").is_success


def test_event_socket_connects(tmp_path: Path) -> None:
    with (
        make_client(tmp_path / "beatweave.db") as client,
        client.websocket_connect("/events") as socket,
    ):
        assert socket.receive_json() == {"type": "connected", "payload": {}}


def test_job_event_is_delivered_to_connected_socket(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, database_path=tmp_path / "beatweave.db"))
    with TestClient(app) as client, client.websocket_connect("/events") as socket:
        assert socket.receive_json()["type"] == "connected"
        app.state.job_manager.events.publish("job-created", {"id": "job-1"})
        assert socket.receive_json() == {
            "type": "job-created",
            "payload": {"id": "job-1"},
        }
