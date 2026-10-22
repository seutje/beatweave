import json
import re
import time
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from gradio_client import Client, handle_file

from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobCancelled, JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.project.store import ProjectStore
from beatweave.wan2gp.authentication import Wan2GPWebSession
from beatweave.wan2gp.schemas import Wan2GPConfig, Wan2GPExecutionResult, Wan2GPStatus

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
            cached = [
                path
                for path in cached
                if self._matches_output(path, saved["wan2gp_output_filename"])
            ]
        if cached and saved.get("wan2gp_download_complete"):
            return Wan2GPExecutionResult(output_path=cached[0])
        if saved.get("wan2gp_submission_started") and saved.get("wan2gp_output_filename"):
            # Older versions downloaded the correct file, then rejected its
            # truncated name. Recover that completed media without another API
            # call or render, even though no completion marker was saved.
            for path in cached:
                try:
                    self.media_runner.probe_video(path)
                except (BeatweaveError, OSError):
                    continue
                context.report(
                    0.97,
                    {"wan2gp_download_complete": True, "wan2gp_downloaded_path": str(path)},
                )
                return Wan2GPExecutionResult(output_path=path)
        local = self._local_output(saved)
        if local is not None:
            return Wan2GPExecutionResult(output_path=local)
        if saved.get("wan2gp_legacy_submission"):
            raise BeatweaveError(
                "wan2gp_legacy_recovery_unavailable",
                "This older render has no saved Wan2GP session. Set the Wan2GP output folder "
                "to recover its finished file, or link the video manually.",
            )
        try:
            httpx_kwargs: dict[str, Any] = {"timeout": self.config.request_timeout_seconds}
            if self.web_session is not None:
                httpx_kwargs["cookies"] = self.web_session.authenticate()
            client = Client(
                self.config.base_url,
                verbose=False,
                download_files=output_directory,
                httpx_kwargs=httpx_kwargs,
            )
            if saved.get("wan2gp_session_hash"):
                client.session_hash = saved["wan2gp_session_hash"]
            else:
                context.report(0.04, {"wan2gp_session_hash": client.session_hash})
            if not saved.get("wan2gp_submission_started"):
                self._load_queue(client, queue_path)
                # Persist before submission: an ambiguous interrupted submission must
                # be monitored, never blindly replayed and rendered twice.
                context.report(0.08, {"wan2gp_submission_started": True})
                self._wait_for_job(
                    client.submit(api_name="/process_tasks_1"),
                    context,
                    progress_start=0.08,
                    progress_end=0.94,
                )
                gallery = self._read_gallery(
                    client, "/finalize_generation_with_state", context, saved
                )
            else:
                gallery = None
            candidates = self._video_paths(gallery)
            if not candidates:
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
                "Wan2GP could not process the video queue.",
                details={"error": self._safe_error(error), "type": type(error).__name__},
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
            if candidates:
                return candidates
            if time.monotonic() - started > self.config.render_timeout_seconds:
                raise BeatweaveError(
                    "wan2gp_recovery_timeout",
                    "The original Wan2GP render could not be recovered. It was not resubmitted.",
                    details={"output_filename": saved.get("wan2gp_output_filename")},
                )
            time.sleep(max(1, self.config.poll_interval_seconds))

    def _refresh_gallery(self, client: Client, context: JobContext, saved: dict) -> Any:
        return self._read_gallery(client, "/refresh_gallery", context, saved)

    def _read_gallery(self, client: Client, api_name: str, context: JobContext, saved: dict) -> Any:
        download_files = client.download_files
        try:
            client.download_files = False
            raw = client.predict(api_name=api_name)
        finally:
            client.download_files = download_files
        # The gallery includes earlier renders. Filter server paths before the
        # Gradio client downloads anything, including during finalization.
        matching = self._matching_gallery(raw, saved.get("wan2gp_output_filename"))
        if matching is None:
            return []
        local = self._video_paths(matching)
        if local:
            directory = str(local[0].parent)
            saved["wan2gp_remote_output_directory"] = directory
            context.report(0.95, {"wan2gp_remote_output_directory": directory})
            return matching
        index = client._infer_fn_index(api_name, None)
        return client.endpoints[index].download_files(matching)[0]

    def _local_output(self, saved: dict) -> Path | None:
        expected = saved.get("wan2gp_output_filename")
        if not expected:
            return None
        directories = [saved.get("wan2gp_remote_output_directory"), self.config.output_directory]
        for directory in dict.fromkeys(path for path in directories if path):
            # The unique job token prevents confusing multiple takes of one scene.
            candidates = [
                path
                for path in self._video_paths(list(Path(directory).glob("*")))
                if self._matches_output(path, expected)
            ]
            for path in sorted(candidates, key=lambda path: path.stat().st_mtime_ns, reverse=True):
                try:
                    # Files may appear while FFmpeg is writing; only import readable media.
                    self.media_runner.probe_video(path)
                except (BeatweaveError, OSError):
                    continue
                return path
        return None

    @staticmethod
    def _matches_output(value: str | Path, expected: str) -> bool:
        # WanGP truncates stems to 50 UTF-8 bytes on Windows. Only accept that
        # precise legacy transformation, never an arbitrary filename prefix.
        name = unquote(str(value))
        if "://" in name:
            name = urlparse(name).path
        stem = PureWindowsPath(name).stem
        stems = {expected, expected.encode("utf-8")[:50].decode("utf-8", errors="ignore")}
        if stem in stems:
            return True
        # WanGP adds (2), (3), ... when that exact output name already exists.
        collision = re.fullmatch(r"(.+)\(([2-9]|[1-9]\d+)\)", stem)
        return collision is not None and collision.group(1) in stems

    @classmethod
    def _matching_gallery(cls, value: Any, expected: str | None) -> Any:
        def is_video(path: Any) -> bool:
            return isinstance(path, (str, Path)) and PureWindowsPath(
                str(path).split("?", 1)[0]
            ).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}

        if isinstance(value, (str, Path)):
            return (
                value
                if is_video(value) and (not expected or cls._matches_output(value, expected))
                else None
            )
        if isinstance(value, dict):
            # Preserve Gradio FileData metadata for its authenticated downloader.
            if is_video(value.get("path")):
                names = [value.get("path"), value.get("orig_name")]
                return (
                    value
                    if not expected
                    or any(name and cls._matches_output(name, expected) for name in names)
                    else None
                )
            filtered = {
                key: match
                for key, item in value.items()
                if (match := cls._matching_gallery(item, expected)) is not None
            }
            return filtered or None
        if isinstance(value, (list, tuple)):
            filtered = [
                match
                for item in value
                if (match := cls._matching_gallery(item, expected)) is not None
            ]
            return filtered or None
        return None

    @staticmethod
    def _load_queue(client: Client, queue_path: Path) -> None:
        """Invoke the upload event with trigger metadata omitted by Gradio's client."""
        index = client._infer_fn_index("/load_queue_action", None)
        endpoint = client.endpoints[index]
        helper = client.new_helper(index)
        upload_target = next(
            target
            for target, event_name in endpoint.dependency["targets"]
            if event_name == "upload"
        )
        endpoint.make_end_to_end_fn(helper)(
            handle_file(str(queue_path)), event_data={}, trigger_id=upload_target
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
            raise BeatweaveError(
                "wan2gp_render_failed",
                "Wan2GP did not complete the video render.",
                details={"error": self._safe_error(error)},
            ) from None

    def _get_json(self, path: str) -> dict[str, Any]:
        if self.web_session is not None:
            return self.web_session.get_json(path)
        try:
            request = Request(
                f"{self.config.base_url}{path}",
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
