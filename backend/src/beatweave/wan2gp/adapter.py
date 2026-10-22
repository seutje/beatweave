import json
import time
from collections.abc import Callable
from contextlib import suppress
from functools import cached_property
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx
from gradio_client import Client, handle_file

from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobCancelled, JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.authentication import Wan2GPWebSession
from beatweave.wan2gp.schemas import Wan2GPConfig, Wan2GPExecutionResult, Wan2GPStatus
from beatweave.wan2gp.transport import connection_url

REQUIRED_ENDPOINTS = {
    "/load_queue_action",
    "/process_tasks_1",
    "/finalize_generation_with_state",
    "/refresh_gallery",
}


class Wan2GPAdapter:
    def __init__(
        self, config: Wan2GPConfig, media_runner: MediaProcessRunner | None = None
    ) -> None:
        self.config = config
        self.media_runner = media_runner or MediaProcessRunner()
        self.web_session = Wan2GPWebSession(config) if config.web_password else None

    @cached_property
    def connection_url(self) -> str:
        url = connection_url(self.config.base_url, self.config.request_timeout_seconds)
        if url != self.config.base_url and self.web_session is not None:
            self.web_session = Wan2GPWebSession(self.config.model_copy(update={"base_url": url}))
        return url

    def status(self) -> Wan2GPStatus:
        try:
            info = self._get_json("/gradio_api/info")
            server_config = self._get_json("/config")
        except BeatweaveError as error:
            return Wan2GPStatus(
                available=False,
                message=(
                    error.message
                    if error.code.startswith("wan2gp_auth_")
                    else "Wan2GP is offline or its Gradio API is unreachable."
                ),
            )
        endpoints = sorted(info.get("named_endpoints", {}))
        missing = sorted(REQUIRED_ENDPOINTS.difference(endpoints))
        profile_ready = not missing
        return Wan2GPStatus(
            available=True,
            profile_ready=profile_ready,
            message=(
                "Wan2GP's queue-processing API is ready."
                if profile_ready
                else "Wan2GP is online, but required queue API endpoints are missing."
            ),
            version=str(server_config.get("version") or "") or None,
            api_endpoints=endpoints,
        )

    def execute(
        self, queue_path: Path, output_directory: Path, context: JobContext
    ) -> Wan2GPExecutionResult:
        output_directory.mkdir(parents=True, exist_ok=True)
        saved = {}
        if hasattr(context, "project_path"):
            record = ProjectStore(context.project_path).get_job(context.job_id)
            saved = record.output if record else {}
        # A completed download survives a crash before take registration.
        cached = self._video_paths(list(output_directory.rglob("*")))
        if saved.get("wan2gp_downloaded_path"):
            cached = [
                path
                for path in cached
                if path.resolve() == Path(saved["wan2gp_downloaded_path"]).resolve()
            ]
        elif saved.get("wan2gp_output_filename"):
            cached = [path for path in cached if path.stem == saved["wan2gp_output_filename"]]
        if cached and saved.get("wan2gp_download_complete"):
            return Wan2GPExecutionResult(output_path=cached[0])
        local = self._local_output(saved)
        if local is not None:
            return Wan2GPExecutionResult(output_path=local)
        phase = "connect"
        try:
            context.report(0.04, {"wan2gp_phase": phase})
            url = self.connection_url
            httpx_kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(
                    self.config.request_timeout_seconds,
                    connect=min(5, self.config.request_timeout_seconds),
                )
            }
            if self.web_session is not None:
                httpx_kwargs["cookies"] = self.web_session.authenticate()
            client = Client(
                url,
                verbose=False,
                download_files=output_directory,
                httpx_kwargs=httpx_kwargs,
                analytics_enabled=False,
            )
            monitor_only = bool(saved.get("wan2gp_legacy_submission"))
            if saved.get("wan2gp_session_hash") and (
                saved.get("wan2gp_submission_started") or saved.get("wan2gp_queue_loaded")
            ):
                client.session_hash = saved["wan2gp_session_hash"]
            else:
                context.report(0.04, {"wan2gp_session_hash": client.session_hash})
            if not saved.get("wan2gp_submission_started") and not monitor_only:
                phase = "upload"
                context.report(0.05, {"wan2gp_phase": phase})
                if not saved.get("wan2gp_queue_loaded"):
                    self._load_queue(client, queue_path, context)
                    context.report(0.07, {"wan2gp_queue_loaded": True})
                # Persist before submission: an ambiguous interrupted submission must
                # be monitored, never blindly replayed and rendered twice.
                phase = "render"
                context.report(0.08, {"wan2gp_submission_started": True, "wan2gp_phase": phase})
                try:
                    self._wait_for_job(
                        client.submit(api_name="/process_tasks_1"),
                        context,
                        progress_start=0.08,
                        progress_end=0.94,
                    )
                    phase = "finalize"
                    gallery = self._read_gallery(
                        client, "/finalize_generation_with_state", context, saved
                    )
                except Exception as error:
                    if not self._is_transport_error(error):
                        raise
                    # A disconnected stream says nothing about GPU completion.
                    # Poll output by its unique filename; never submit again.
                    context.report(0.94, {"wan2gp_transport_error": self._safe_error(error)})
                    gallery = None
            else:
                gallery = None
            candidates = self._video_paths(gallery)
            if not candidates:
                phase = "recover"
                context.report(0.94, {"wan2gp_phase": phase})
                candidates = self._wait_for_output(client, context, saved)
            result_path = max(candidates, key=lambda path: path.stat().st_mtime_ns)
            context.report(
                0.97,
                {
                    "wan2gp_download_complete": True,
                    "wan2gp_downloaded_path": str(result_path),
                },
            )
        except (BeatweaveError, JobCancelled):
            raise
        except Exception as error:
            raise BeatweaveError(
                "wan2gp_api_failed",
                f"WanGP connection failed during {phase}: {self._safe_error(error)}",
                details={
                    "phase": phase,
                    "error": self._safe_error(error),
                    "type": type(error).__name__,
                },
            ) from None
        finally:
            if "client" in locals():
                client.close()
        if not candidates:
            raise BeatweaveError(
                "wan2gp_output_missing",
                "Wan2GP completed without returning a downloadable video output.",
            )
        return Wan2GPExecutionResult(output_path=result_path)

    def _wait_for_output(self, client: Client, context: JobContext, saved: dict) -> list[Path]:
        started = time.monotonic()
        while True:
            context.check_cancelled()
            local = self._local_output(saved)
            if local is not None:
                return [local]
            # Refresh is safe while the original render is running. Finalize clears
            # Wan2GP's in-progress state and must only run after generation finishes.
            try:
                gallery = self._refresh_gallery(client, context, saved)
            except JobCancelled:
                raise
            except Exception:
                # The renderer may still be finishing despite a dropped API
                # connection. Keep looking for its durable, job-specific output.
                if time.monotonic() - started > self.config.render_timeout_seconds:
                    raise
                time.sleep(max(1, self.config.poll_interval_seconds))
                continue
            candidates = self._video_paths(gallery)
            expected = saved.get("wan2gp_output_filename")
            if expected:
                candidates = [path for path in candidates if self._matches_output(path, expected)]
            if candidates:
                return candidates
            if time.monotonic() - started > self.config.render_timeout_seconds:
                raise BeatweaveError(
                    "wan2gp_recovery_timeout",
                    "The original Wan2GP render could not be recovered. It was not resubmitted.",
                    details={"output_filename": expected},
                )
            time.sleep(max(1, self.config.poll_interval_seconds))

    def _refresh_gallery(self, client: Client, context: JobContext, saved: dict) -> Any:
        return self._read_gallery(client, "/refresh_gallery", context, saved)

    def _read_gallery(self, client: Client, api_name: str, context: JobContext, saved: dict) -> Any:
        download_files = client.download_files
        try:
            client.download_files = False
            raw = self._wait_for_rpc(client.submit(api_name=api_name), context, api_name)
            expected = saved.get("wan2gp_output_filename")
            if expected:
                raw = self._matching_outputs(raw, expected)
                if not raw:
                    return []
            local = self._video_paths(raw)
            if local:
                directory = str(local[0].parent)
                saved["wan2gp_remote_output_directory"] = directory
                context.report(0.95, {"wan2gp_remote_output_directory": directory})
                return raw
        finally:
            client.download_files = download_files
        index = client._infer_fn_index(api_name, None)
        return client.endpoints[index].download_files(raw)[0]

    def _local_output(self, saved: dict) -> Path | None:
        directories = [saved.get("wan2gp_remote_output_directory"), self.config.output_directory]
        expected = saved.get("wan2gp_output_filename")
        if not expected:
            return None
        # The unique job token prevents confusing multiple takes of one scene.
        for directory in dict.fromkeys(directories):
            if not directory:
                continue
            for stem in dict.fromkeys((expected, expected[:50])):
                candidates = self._video_paths(list(Path(directory).glob(f"{stem}.*")))
                for path in candidates:
                    try:
                        # Files may appear while FFmpeg is writing; import readable media only.
                        self.media_runner.probe_video(path)
                    except (BeatweaveError, OSError):
                        continue
                    return path
        return None

    @staticmethod
    def _matches_output(path: str | Path, expected: str) -> bool:
        # Remote Windows paths must also work when Beatweave runs on another OS.
        candidate = Path(str(path).replace("\\", "/"))
        return candidate.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"} and (
            candidate.stem == expected or (len(expected) > 50 and candidate.stem == expected[:50])
        )

    @classmethod
    def _matching_outputs(cls, value: Any, expected: str) -> list[Any]:
        """Select this job's files before Gradio downloads or local gallery discovery."""
        if isinstance(value, dict):
            if "path" in value:
                return [value] if cls._matches_output(value["path"], expected) else []
            return [
                item for child in value.values() for item in cls._matching_outputs(child, expected)
            ]
        if isinstance(value, (list, tuple)):
            return [item for child in value for item in cls._matching_outputs(child, expected)]
        if isinstance(value, (str, Path)) and cls._matches_output(value, expected):
            return [value]
        return []

    def _load_queue(self, client: Client, queue_path: Path, context: JobContext) -> None:
        """Invoke the upload event with trigger metadata omitted by Gradio's client."""
        index = client._infer_fn_index("/load_queue_action", None)
        endpoint = client.endpoints[index]
        helper = client.new_helper(index)
        upload_target = next(
            target
            for target, event_name in endpoint.dependency["targets"]
            if event_name == "upload"
        )
        future = client.executor.submit(
            endpoint.make_end_to_end_fn(helper),
            handle_file(str(queue_path)),
            event_data={},
            trigger_id=upload_target,
        )

        def cancel_upload() -> None:
            helper.thread_complete = True
            helper.should_cancel = True
            # Cancel the upload event only, never another running GPU task.
            with suppress(Exception):
                endpoint.make_cancel(helper)()

        self._wait_for_rpc(
            future,
            context,
            "/load_queue_action",
            cancel=cancel_upload,
        )
        messages: list[str] = []
        for _ in range(helper.updates.qsize()):
            update = helper.updates.get_nowait()
            log = getattr(update, "log", None)
            if log:
                messages.append(str(log[0]))
        failures = [
            message for message in messages if message.lower().startswith(("failed", "error"))
        ]
        if failures:
            raise BeatweaveError(
                "wan2gp_queue_rejected",
                "Wan2GP rejected the generated queue.",
                details={"messages": failures},
            )

    def _wait_for_rpc(
        self,
        job: Any,
        context: JobContext,
        api_name: str,
        *,
        cancel: Callable[[], None] | None = None,
    ) -> Any:
        started = time.monotonic()
        try:
            while not job.done():
                context.check_cancelled()
                if time.monotonic() - started > self.config.request_timeout_seconds:
                    raise BeatweaveError(
                        "wan2gp_control_timeout",
                        f"WanGP did not answer {api_name} before the request timeout. "
                        "Check the SSH tunnel or increase the request timeout.",
                        details={"api_name": api_name},
                    )
                time.sleep(min(0.25, self.config.poll_interval_seconds))
            return job.result()
        except BaseException:
            if cancel is not None:
                cancel()
            with suppress(Exception):
                job.cancel()
            raise

    def _wait_for_job(
        self,
        job: Any,
        context: JobContext,
        *,
        progress_start: float,
        progress_end: float,
    ) -> Any:
        started = time.monotonic()
        while not job.done():
            try:
                context.check_cancelled()
            except Exception:
                job.cancel()
                raise
            elapsed = time.monotonic() - started
            if elapsed > self.config.render_timeout_seconds:
                job.cancel()
                raise BeatweaveError(
                    "wan2gp_render_timeout",
                    "Wan2GP did not finish before the configured timeout.",
                )
            fraction = min(0.99, elapsed / self.config.render_timeout_seconds)
            context.report(progress_start + (progress_end - progress_start) * fraction)
            time.sleep(self.config.poll_interval_seconds)
        try:
            return job.result()
        except Exception as error:
            if self._is_transport_error(error):
                raise
            raise BeatweaveError(
                "wan2gp_render_failed",
                "Wan2GP did not complete the video render.",
                details={"error": self._safe_error(error)},
            ) from None

    def _get_json(self, path: str) -> dict[str, Any]:
        url = self.connection_url
        if self.web_session is not None:
            return self.web_session.get_json(path)
        try:
            request = Request(
                f"{url}{path}",
                headers={"Accept": "application/json"},
            )
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                return json.loads(response.read())
        except HTTPError as error:
            if error.code in {401, 403}:
                raise BeatweaveError(
                    "wan2gp_auth_required",
                    "WanGP requires a web password. Set it in Settings > Video.",
                ) from error
            raise BeatweaveError(
                "wan2gp_unavailable", "Wan2GP is offline or unreachable."
            ) from error
        except (URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            raise BeatweaveError(
                "wan2gp_unavailable", "Wan2GP is offline or unreachable."
            ) from error

    def _safe_error(self, error: Exception) -> str:
        message = str(error)
        if self.config.web_password:
            message = message.replace(self.config.web_password, "[redacted]")
        if self.web_session is not None:
            for cookie in self.web_session.jar:
                message = message.replace(cookie.value, "[redacted]")
        return message

    @staticmethod
    def _is_transport_error(error: Exception) -> bool:
        if isinstance(error, BeatweaveError) and error.code == "wan2gp_control_timeout":
            return True
        return isinstance(
            error, (httpx.TransportError, TimeoutError, ConnectionError, URLError)
        ) or (
            isinstance(error, ValueError)
            and str(error)
            in {"Did not receive process_completed message.", "Unexpected message: None"}
        )

    @classmethod
    def _video_paths(cls, value: Any) -> list[Path]:
        paths: list[Path] = []
        if isinstance(value, (str, Path)):
            path = Path(value)
            if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                paths.append(path)
        elif isinstance(value, dict):
            for item in value.values():
                paths.extend(cls._video_paths(item))
        elif isinstance(value, (list, tuple)):
            for item in value:
                paths.extend(cls._video_paths(item))
        return paths
