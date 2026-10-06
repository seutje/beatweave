import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gradio_client import Client, handle_file

from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobCancelled, JobContext
from beatweave.media.process import MediaProcessRunner
from beatweave.project.store import ProjectStore
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

    def status(self) -> Wan2GPStatus:
        try:
            info = self._get_json("/gradio_api/info")
            server_config = self._get_json("/config")
        except BeatweaveError:
            return Wan2GPStatus(
                available=False,
                message="Wan2GP is offline or its Gradio API is unreachable.",
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
        if saved.get("wan2gp_legacy_submission"):
            raise BeatweaveError(
                "wan2gp_legacy_recovery_unavailable",
                "This older render has no saved Wan2GP session. Set the Wan2GP output folder "
                "to recover its finished file, or link the video manually.",
            )
        try:
            client = Client(
                self.config.base_url,
                verbose=False,
                download_files=output_directory,
                httpx_kwargs={"timeout": self.config.request_timeout_seconds},
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
                gallery = client.predict(api_name="/finalize_generation_with_state")
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
                details={"error": str(error), "type": type(error).__name__},
            ) from error
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
                candidates = [path for path in candidates if path.stem == expected]
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
        download_files = client.download_files
        try:
            client.download_files = False
            raw = client.predict(api_name="/refresh_gallery")
            local = self._video_paths(raw)
            if local:
                directory = str(local[0].parent)
                saved["wan2gp_remote_output_directory"] = directory
                context.report(0.95, {"wan2gp_remote_output_directory": directory})
        finally:
            client.download_files = download_files
        index = client._infer_fn_index("/refresh_gallery", None)
        return client.endpoints[index].download_files(raw)[0]

    def _local_output(self, saved: dict) -> Path | None:
        directory = saved.get("wan2gp_remote_output_directory") or self.config.output_directory
        expected = saved.get("wan2gp_output_filename")
        if not directory or not expected:
            return None
        # The unique job token prevents confusing multiple takes of one scene.
        candidates = self._video_paths(list(Path(directory).glob(f"{expected}.*")))
        for path in candidates:
            try:
                # Files may appear while FFmpeg is writing; only import readable media.
                self.media_runner.probe_video(path)
            except (BeatweaveError, OSError):
                continue
            return path
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
                details={"error": str(error)},
            ) from error

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            request = Request(
                f"{self.config.base_url}{path}",
                headers={"Accept": "application/json"},
            )
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                return json.loads(response.read())
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
            raise BeatweaveError(
                "wan2gp_unavailable", "Wan2GP is offline or unreachable."
            ) from error

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
