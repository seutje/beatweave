from concurrent.futures import Future
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.jobs.schemas import JobError, JobState
from beatweave.jobs.worker import JobCancelled
from beatweave.main import create_app
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.schemas import VideoRenderRequest, Wan2GPConfig
from beatweave.wan2gp.service import Wan2GPService
from beatweave.wan2gp.transport import connection_url
from test_wan2gp import completed_job, create_project_with_scene, render_request, wait_for_job


@pytest.fixture(autouse=True)
def no_live_connections(monkeypatch):
    monkeypatch.setattr("beatweave.wan2gp.adapter.connection_url", lambda url, _timeout: url)


def test_localhost_prefers_reachable_ipv4_without_changing_password_identity(monkeypatch):
    calls = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    def connect(address, *, timeout):
        calls.append((address, timeout))
        return Socket()

    monkeypatch.setattr("beatweave.wan2gp.transport.socket.create_connection", connect)
    assert connection_url("http://localhost:7860/wan", 30) == "http://127.0.0.1:7860/wan"
    assert calls == [(("127.0.0.1", 7860), 1)]
    monkeypatch.setattr("beatweave.wan2gp.adapter.connection_url", connection_url)
    config = Wan2GPConfig(web_password="secret")
    adapter = Wan2GPAdapter(config)
    assert adapter.connection_url == "http://127.0.0.1:7860"
    assert config.base_url == "http://localhost:7860"
    assert adapter.web_session.config.base_url == "http://127.0.0.1:7860"
    assert adapter.web_session.config.web_password == "secret"


def test_ipv6_only_localhost_and_remote_hosts_keep_their_configured_address(monkeypatch):
    def refused(*_args, **_kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr("beatweave.wan2gp.transport.socket.create_connection", refused)
    assert connection_url("http://localhost:7860", 30) == "http://localhost:7860"
    assert connection_url("https://pod.example/wan", 30) == "https://pod.example/wan"
    assert connection_url("http://[::1]:7860", 30) == "http://[::1]:7860"


def test_https_localhost_preserves_certificate_hostname(monkeypatch):
    monkeypatch.setattr(
        "beatweave.wan2gp.transport.socket.create_connection",
        lambda *_args, **_kwargs: pytest.fail("HTTPS must preserve its hostname"),
    )
    assert connection_url("https://localhost:7860", 30) == "https://localhost:7860"


@pytest.mark.parametrize("old_bad_legacy_flag", [False, True])
def test_failure_before_client_initializes_is_safe_to_submit_after_restart(
    tmp_path: Path, monkeypatch, old_bad_legacy_flag: bool
):
    def offline_client(*_args, **_kwargs):
        raise httpx.ConnectTimeout("SSH tunnel is down")

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", offline_client)
    settings = Settings(database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as client:
        project, scene, start, end, audio = create_project_with_scene(client, tmp_path)
        response = client.post("/wan2gp/renders", json=render_request(scene, start, end, audio))
        failed = wait_for_job(client, response.json()["job"]["id"])
        assert failed["state"] == "failed"
        assert failed["output"]["wan2gp_submission_started"] is False
        assert "wan2gp_session_hash" not in failed["output"]
        assert failed["error"]["details"]["phase"] == "connect"
        if old_bad_legacy_flag:
            # Reproduce the supplied failed job from the preceding release.
            store = ProjectStore(project["path"])
            job = store.get_job(failed["id"])
            del job.output["wan2gp_submission_started"]
            job.output["wan2gp_legacy_submission"] = True
            job.output["wan2gp_output_filename"] = f"bw_scene_01_{job.id.replace('-', '')}"
            job.error = JobError(code="wan2gp_legacy_recovery_unavailable", message="Old error")
            store.update_job(job)

    submissions, uploads = [], []
    captured = {}

    class Client:
        def __init__(self, url, *, download_files, **kwargs):
            captured.update(kwargs)
            self.session_hash = "new-session"
            self.download_files = download_files
            self.directory = download_files

        def submit(self, *, api_name):
            if api_name == "/process_tasks_1":
                submissions.append(api_name)
                return completed_job(None)
            assert api_name == "/finalize_generation_with_state"
            output = self.directory / f"{failed['output']['wan2gp_output_filename']}.mp4"
            output.write_bytes(b"finished")
            return completed_job([{"video": {"path": str(output)}}])

        def close(self):
            pass

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", Client)
    monkeypatch.setattr(Wan2GPAdapter, "_load_queue", lambda *_args: uploads.append("load"))
    with TestClient(create_app(settings)) as client:
        recovered = wait_for_job(client, failed["id"])
        assert recovered["state"] == "complete", recovered
        assert recovered["output"]["wan2gp_legacy_submission"] is False
        assert len(client.get(f"/scenes/{scene}/takes").json()["takes"]) == 1
    assert submissions == ["/process_tasks_1"]
    assert uploads == ["load"]
    assert captured["httpx_kwargs"]["timeout"].connect == 5


def test_unknown_legacy_submission_stays_monitor_only_across_restarts(tmp_path: Path, monkeypatch):
    settings = Settings(database_path=tmp_path / "application.db")
    app = create_app(settings)
    with TestClient(app) as client:
        project, scene, start, end, audio = create_project_with_scene(client, tmp_path)
        job, _ = Wan2GPService(app.state.database).start_render(
            VideoRenderRequest.model_validate(render_request(scene, start, end, audio))
        )
        job.state = JobState.FAILED
        job.error = JobError(code="wan2gp_legacy_recovery_unavailable", message="Old render")
        del job.output["wan2gp_submission_started"]
        job.output.update(queue_generated=True, wan2gp_output_filename=f"beatweave-{scene}")
        ProjectStore(project["path"]).update_job(job)

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.session_hash = "monitor-session"

        def close(self):
            pass

    polls = []

    def poll(_adapter, _client, context, _saved):
        polls.append(True)
        if len(polls) == 1:
            raise BeatweaveError("wan2gp_recovery_timeout", "Tunnel dropped")
        output = Path(context.project_path) / "cache" / "remote.mp4"
        output.write_bytes(b"downloaded-from-remote-gallery")
        return [output]

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", Client)
    monkeypatch.setattr(Wan2GPAdapter, "_wait_for_output", poll)
    monkeypatch.setattr(Wan2GPAdapter, "_load_queue", lambda *_: pytest.fail("Never resubmit"))
    with TestClient(create_app(settings)) as client:
        first = wait_for_job(client, job.id)
        assert first["state"] == "failed"
        assert first["output"]["wan2gp_legacy_submission"] is True
        assert first["output"]["wan2gp_session_hash"] == "monitor-session"
    with TestClient(create_app(settings)) as client:
        final = wait_for_job(client, job.id)
        assert final["state"] == "complete", final
        assert final["output"]["wan2gp_legacy_submission"] is True
    assert len(polls) == 2


def test_dropped_render_stream_polls_remote_output_without_submitting_twice(tmp_path, monkeypatch):
    saved = {"wan2gp_output_filename": "unique-job", "wan2gp_submission_started": False}
    calls = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.session_hash = "original-session"

        def submit(self, *, api_name):
            calls.append(api_name)
            future = Future()
            future.set_exception(httpx.ReadTimeout("SSH stream disconnected"))
            return future

        def close(self):
            pass

    def poll(_adapter, client, _context, _saved):
        assert client.session_hash == "original-session"
        calls.append("poll")
        path = tmp_path / "output" / "unique-job.mp4"
        path.write_bytes(b"finished-remotely")
        return [path]

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", Client)
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.ProjectStore",
        lambda _: SimpleNamespace(get_job=lambda _: SimpleNamespace(output=saved)),
    )
    monkeypatch.setattr(Wan2GPAdapter, "_wait_for_output", poll)
    monkeypatch.setattr(Wan2GPAdapter, "_load_queue", lambda *_: calls.append("upload"))
    context = SimpleNamespace(
        project_path=tmp_path,
        job_id="job",
        report=lambda _progress, data=None: saved.update(data or {}),
        check_cancelled=lambda: None,
    )
    adapter = Wan2GPAdapter(Wan2GPConfig())
    result = adapter.execute(tmp_path / "queue.zip", tmp_path / "output", context)
    assert result.output_path.read_bytes() == b"finished-remotely"
    assert saved["wan2gp_submission_started"] is True
    assert saved["wan2gp_phase"] == "recover"
    assert calls == ["upload", "/process_tasks_1", "poll"]
    adapter.execute(tmp_path / "queue.zip", tmp_path / "output", context)
    assert calls == ["upload", "/process_tasks_1", "poll"]


def test_confirmed_remote_queue_is_not_uploaded_twice_after_restart(tmp_path, monkeypatch):
    saved = {
        "wan2gp_output_filename": "unique-job",
        "wan2gp_session_hash": "loaded-session",
        "wan2gp_submission_started": False,
        "wan2gp_queue_loaded": True,
    }
    calls = []

    class Client:
        def __init__(self, *_args, download_files, **_kwargs):
            self.session_hash = "new-session"
            self.download_files = download_files
            self.directory = download_files

        def submit(self, *, api_name):
            assert self.session_hash == "loaded-session"
            calls.append(api_name)
            if api_name == "/process_tasks_1":
                return completed_job(None)
            path = self.directory / "unique-job.mp4"
            path.write_bytes(b"finished")
            return completed_job([str(path)])

        def close(self):
            pass

    monkeypatch.setattr("beatweave.wan2gp.adapter.Client", Client)
    monkeypatch.setattr(
        "beatweave.wan2gp.adapter.ProjectStore",
        lambda _: SimpleNamespace(get_job=lambda _: SimpleNamespace(output=saved)),
    )
    monkeypatch.setattr(Wan2GPAdapter, "_load_queue", lambda *_: pytest.fail("Already uploaded"))
    context = SimpleNamespace(
        project_path=tmp_path,
        job_id="job",
        check_cancelled=lambda: None,
        report=lambda _progress, data=None: saved.update(data or {}),
    )
    result = Wan2GPAdapter(Wan2GPConfig()).execute(
        tmp_path / "queue.zip", tmp_path / "out", context
    )
    assert result.output_path.read_bytes() == b"finished"
    assert calls == ["/process_tasks_1", "/finalize_generation_with_state"]


@pytest.mark.parametrize("cancelled", [False, True])
def test_stuck_control_request_is_bounded_and_cancellable(monkeypatch, cancelled):
    cancelled_calls = []
    clock = iter([0, 2])
    monkeypatch.setattr("beatweave.wan2gp.adapter.time.monotonic", lambda: next(clock))
    job = SimpleNamespace(done=lambda: False, cancel=lambda: cancelled_calls.append(True))

    def check():
        if cancelled:
            raise JobCancelled

    context = SimpleNamespace(check_cancelled=check)
    adapter = Wan2GPAdapter(Wan2GPConfig(request_timeout_seconds=1))
    with pytest.raises(JobCancelled if cancelled else BeatweaveError) as error:
        adapter._wait_for_rpc(job, context, "/refresh_gallery")
    if not cancelled:
        assert error.value.code == "wan2gp_control_timeout"
    assert cancelled_calls == [True]


def test_stuck_upload_releases_its_local_waiter_and_cancels_only_its_event(tmp_path, monkeypatch):
    ticks = iter([0, 2])
    monkeypatch.setattr("beatweave.wan2gp.adapter.time.monotonic", lambda: next(ticks))
    helper = SimpleNamespace(updates=SimpleQueue(), thread_complete=False, should_cancel=False)
    future = Future()
    cancelled_events = []

    class Endpoint:
        dependency = {"targets": [[42, "upload"]]}

        def make_end_to_end_fn(self, _helper):
            return lambda *_args, **_kwargs: None

        def make_cancel(self, value):
            assert value is helper
            return lambda: cancelled_events.append(42)

    queue = tmp_path / "queue.zip"
    queue.write_bytes(b"queue")
    client = SimpleNamespace(
        endpoints={1: Endpoint()},
        _infer_fn_index=lambda *_args: 1,
        new_helper=lambda *_args: helper,
        executor=SimpleNamespace(submit=lambda *_args, **_kwargs: future),
    )
    with pytest.raises(BeatweaveError) as error:
        Wan2GPAdapter(Wan2GPConfig(request_timeout_seconds=1))._load_queue(
            client, queue, SimpleNamespace(check_cancelled=lambda: None)
        )
    assert error.value.code == "wan2gp_control_timeout"
    assert helper.thread_complete and helper.should_cancel
    assert future.cancelled()
    assert cancelled_events == [42]
