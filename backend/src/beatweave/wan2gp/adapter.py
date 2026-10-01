import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gradio_client import Client, handle_file

from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobContext
from beatweave.wan2gp.schemas import Wan2GPConfig, Wan2GPExecutionResult, Wan2GPStatus

REQUIRED_ENDPOINTS = {
    "/load_queue_action",
    "/process_tasks_1",
    "/finalize_generation_with_state",
}


class Wan2GPAdapter:
    def __init__(self, config: Wan2GPConfig) -> None:
        self.config = config

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
        try:
            client = Client(
                self.config.base_url,
                verbose=False,
                download_files=output_directory,
                httpx_kwargs={"timeout": self.config.request_timeout_seconds},
            )
            self._load_queue(client, queue_path)
            context.report(0.08)
            self._wait_for_job(
                client.submit(api_name="/process_tasks_1"),
                context,
                progress_start=0.08,
                progress_end=0.94,
            )
            gallery = client.predict(api_name="/finalize_generation_with_state")
        except BeatweaveError:
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
        candidates = self._video_paths(gallery)
        if not candidates:
            candidates = [
                path
                for path in output_directory.rglob("*")
                if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
            ]
        if not candidates:
            raise BeatweaveError(
                "wan2gp_output_missing",
                "Wan2GP completed without returning a downloadable video output.",
            )
        return Wan2GPExecutionResult(
            output_path=max(candidates, key=lambda path: path.stat().st_mtime_ns)
        )

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
