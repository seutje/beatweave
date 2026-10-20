import io
import json
from http.cookiejar import Cookie
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.main import create_app
from beatweave.wan2gp.adapter import REQUIRED_ENDPOINTS, Wan2GPAdapter
from beatweave.wan2gp.schemas import VideoRenderRequest, Wan2GPConfig
from beatweave.wan2gp.service import Wan2GPService
from test_wan2gp import create_project_with_scene, render_request


def mock_login(monkeypatch, *, failure: int | None = None):
    calls = []

    def build(*handlers):
        jar = handlers[0].cookiejar

        class Opener:
            def open(self, request, *, timeout):
                calls.append(request)
                path = urlsplit(request.full_url).path
                if path == "/auth/login":
                    if request.data is None:
                        return io.BytesIO(
                            b'<input value="csrf&amp;token" name="csrf" type="hidden">'
                        )
                    assert parse_qs(request.data.decode()) == {
                        "csrf": ["csrf&token"],
                        "password": ["my private passphrase"],
                    }
                    assert request.get_header("Origin") == "https://pod.example"
                    if failure:
                        raise HTTPError(request.full_url, failure, "Rejected", {}, None)
                    jar.set_cookie(
                        Cookie(
                            version=0,
                            name="wangp_session",
                            value="private-session-cookie",
                            port=None,
                            port_specified=False,
                            domain="pod.example",
                            domain_specified=False,
                            domain_initial_dot=False,
                            path="/",
                            path_specified=True,
                            secure=True,
                            expires=None,
                            discard=True,
                            comment=None,
                            comment_url=None,
                            rest={},
                            rfc2109=False,
                        )
                    )
                    raise HTTPError(request.full_url, 303, "See Other", {}, None)
                payload = (
                    {"named_endpoints": dict.fromkeys(REQUIRED_ENDPOINTS, {})}
                    if path.endswith("/info")
                    else {"version": "5.29"}
                )
                return io.BytesIO(json.dumps(payload).encode())

        return Opener()

    monkeypatch.setattr("beatweave.wan2gp.authentication.build_opener", build)
    return calls


def test_password_login_uses_csrf_cookie_and_reports_ready(monkeypatch) -> None:
    calls = mock_login(monkeypatch)
    config = Wan2GPConfig(base_url="https://pod.example", web_password="my private passphrase")
    status = Wan2GPAdapter(config).status()
    assert status.available and status.profile_ready
    assert len(calls) == 4  # login form, login POST, API info, Gradio config
    assert sum(request.data is not None for request in calls) == 1
    assert "my private passphrase" not in config.model_dump_json()
    assert "my private passphrase" not in repr(config)


@pytest.mark.parametrize("code", [401, 403, 429])
def test_authentication_failure_is_actionable_and_does_not_retry(monkeypatch, code: int) -> None:
    calls = mock_login(monkeypatch, failure=code)
    status = Wan2GPAdapter(
        Wan2GPConfig(
            base_url="https://pod.example",
            web_password="my private passphrase",
        )
    ).status()
    assert not status.available
    assert ("rate limited" if code == 429 else "password") in status.message
    assert len(calls) == 2
    assert "my private passphrase" not in status.model_dump_json()


def test_authenticated_cookie_reaches_gradio_client_and_errors_are_redacted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    mock_login(monkeypatch)
    captured = {}

    def client(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("my private passphrase private-session-cookie")

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", client)
    adapter = Wan2GPAdapter(
        Wan2GPConfig(
            base_url="https://pod.example",
            web_password="my private passphrase",
        )
    )
    with pytest.raises(BeatweaveError) as error:
        adapter.execute(tmp_path / "queue.zip", tmp_path / "out", object())
    assert captured["httpx_kwargs"]["cookies"] == {"wangp_session": "private-session-cookie"}
    assert "my private passphrase" not in str(error.value.details)
    assert "private-session-cookie" not in str(error.value.details)
    assert error.value.__suppress_context__


def test_missing_password_reports_login_required(monkeypatch) -> None:
    def rejected(request, **kwargs):
        raise HTTPError(request.full_url, 401, "Sign in", {}, None)

    monkeypatch.setattr("beatweave.wan2gp.adapter.urlopen", rejected)
    assert "web password" in Wan2GPAdapter(Wan2GPConfig()).status().message


def test_password_is_endpoint_scoped_persistent_and_absent_from_jobs(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "application.db")
    app = create_app(settings)
    with TestClient(app) as client:
        config = client.get("/wan2gp/config").json()
        config.update(base_url="https://pod.example", web_password="my private passphrase")
        saved = client.put("/wan2gp/config", json=config)
        assert saved.is_success
        assert saved.json()["web_password_configured"]
        assert "my private passphrase" not in saved.text
        assert "web_password" not in saved.json()
        config = saved.json()
        assert client.put("/wan2gp/config", json=config).json()["web_password_configured"]
        _, scene, start, end, audio = create_project_with_scene(client, tmp_path)
        job, _ = Wan2GPService(app.state.database).start_render(
            VideoRenderRequest.model_validate(render_request(scene, start, end, audio))
        )
        assert "my private passphrase" not in job.model_dump_json()
        assert "web_password" not in job.output["renderer_config"]
        invalid = {**config, "web_password": "my private passphrase"}
        invalid["profiles"] = {"bad-key": config["profile"]}
        response = client.put("/wan2gp/config", json=invalid)
        assert response.status_code == 422
        assert "my private passphrase" not in response.text
        config["base_url"] = "https://another.example"
        assert not client.put("/wan2gp/config", json=config).json()["web_password_configured"]
    with TestClient(create_app(settings)) as client:
        config["base_url"] = "https://pod.example"
        assert client.put("/wan2gp/config", json=config).json()["web_password_configured"]
        config["web_password"] = ""
        assert not client.put("/wan2gp/config", json=config).json()["web_password_configured"]
