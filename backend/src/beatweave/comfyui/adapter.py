import json
import logging
import time
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from beatweave.comfyui.profile import (
    build_workflow,
    validate_installation,
    validate_workflow_inputs,
)
from beatweave.comfyui.schemas import (
    ComfyUIConfig,
    ComfyUIHistoryEntry,
    ComfyUIOutput,
    ComfyUIStatus,
    ImageRenderRequest,
)
from beatweave.errors import BeatweaveError
from beatweave.jobs.worker import JobContext

logger = logging.getLogger(__name__)


class ComfyUIAdapter:
    def __init__(self, config: ComfyUIConfig) -> None:
        self.config = config

    def status(self) -> ComfyUIStatus:
        try:
            stats = self._json("GET", "/system_stats")
            object_info = self._json("GET", "/object_info")
            validate_installation(object_info, self.config.profile)
            system = stats.get("system", {})
            devices = stats.get("devices", [])
            return ComfyUIStatus(
                available=True,
                profile_ready=True,
                message="ComfyUI and the Qwen Image 2.1 profile are ready.",
                version=system.get("comfyui_version"),
                device=devices[0].get("name") if devices else None,
            )
        except BeatweaveError as error:
            if error.code in {"comfyui_nodes_missing", "comfyui_models_missing"}:
                return ComfyUIStatus(
                    available=True,
                    profile_ready=False,
                    message=error.message,
                )
            return ComfyUIStatus(
                available=False,
                profile_ready=False,
                message="ComfyUI is offline or unreachable.",
            )

    def render(self, request: ImageRenderRequest, context: JobContext) -> dict:
        object_info = self._json("GET", "/object_info")
        validate_installation(object_info, self.config.profile)
        workflow = build_workflow(request, self.config.profile, context.job_id)
        validate_workflow_inputs(workflow, object_info)
        context.report(0.05)
        submitted = self._json(
            "POST",
            "/prompt",
            {"prompt": workflow, "client_id": f"beatweave-{uuid4()}"},
        )
        prompt_id = submitted.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise BeatweaveError(
                "comfyui_submission_failed",
                "ComfyUI did not return a prompt ID.",
                details={"node_errors": submitted.get("node_errors", {})},
            )
        context.report(0.1, {"comfyui_prompt_id": prompt_id})
        entry = self._wait_for_completion(prompt_id, context)
        output = self._find_output(entry)
        image = self._bytes(
            "/view?"
            + urlencode(
                {
                    "filename": output.filename,
                    "subfolder": output.subfolder,
                    "type": output.type,
                }
            )
        )
        if not image:
            raise BeatweaveError("comfyui_output_empty", "ComfyUI returned an empty image output.")
        context.report(0.95)
        return {
            "comfyui_prompt_id": prompt_id,
            "comfyui_output": output.model_dump(mode="json"),
            "image_bytes": image,
        }

    def _wait_for_completion(self, prompt_id: str, context: JobContext) -> ComfyUIHistoryEntry:
        deadline = time.monotonic() + self.config.render_timeout_seconds
        while time.monotonic() < deadline:
            context.check_cancelled()
            history = self._json("GET", f"/history/{prompt_id}")
            raw_entry = history.get(prompt_id)
            if raw_entry is not None:
                entry = ComfyUIHistoryEntry.model_validate(raw_entry)
                status = entry.status
                if status.get("status_str") == "error":
                    message = self._execution_error(status) or "ComfyUI failed the workflow."
                    raise BeatweaveError("comfyui_execution_failed", message)
                if status.get("completed") or entry.outputs:
                    return entry
            context.report(0.15)
            time.sleep(self.config.poll_interval_seconds)
        raise BeatweaveError(
            "comfyui_render_timeout",
            "ComfyUI did not finish the image render before the configured timeout.",
        )

    @staticmethod
    def _execution_error(status: Mapping[str, object]) -> str | None:
        messages = status.get("messages")
        if not isinstance(messages, list):
            return None
        for item in reversed(messages):
            if (
                isinstance(item, list)
                and len(item) > 1
                and item[0] == "execution_error"
                and isinstance(item[1], dict)
            ):
                return str(item[1].get("exception_message") or "ComfyUI execution failed.")
        return None

    @staticmethod
    def _find_output(entry: ComfyUIHistoryEntry) -> ComfyUIOutput:
        for node_output in entry.outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images")
            if isinstance(images, list) and images:
                return ComfyUIOutput.model_validate(images[0])
        raise BeatweaveError("comfyui_output_missing", "ComfyUI completed without an image output.")

    def _json(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.config.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            detail = self._http_error_detail(error)
            raise BeatweaveError(
                "comfyui_rejected_request",
                f"ComfyUI returned HTTP {error.code}: {detail}",
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise BeatweaveError(
                "comfyui_unavailable", "ComfyUI is offline or unreachable."
            ) from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BeatweaveError(
                "comfyui_invalid_response", "ComfyUI returned an invalid response."
            ) from error
        if not isinstance(result, dict):
            raise BeatweaveError(
                "comfyui_invalid_response", "ComfyUI returned an invalid response."
            )
        return result

    def _bytes(self, path: str) -> bytes:
        request = Request(self.config.base_url + path, method="GET")
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise BeatweaveError(
                "comfyui_output_download_failed",
                "The generated ComfyUI image could not be downloaded.",
            ) from error

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str:
        try:
            payload = json.loads(error.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error.reason or "request rejected"
        if isinstance(payload, dict):
            message = payload.get("error")
            if isinstance(message, dict):
                return str(message.get("message") or message.get("type") or "request rejected")
            if message:
                return str(message)
        return error.reason or "request rejected"
