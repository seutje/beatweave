import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.mcpserver.exceptions import ToolError

from beatweave.exports.schemas import ExportRequest
from beatweave.jobs.schemas import JobState
from beatweave.keyframes.schemas import GenerateKeyframeRequest
from beatweave.timeline.schemas import UpdateSceneRequest
from beatweave.video_takes.schemas import RenderSceneRequest

Requester = Callable[[str, str, dict[str, Any] | None], Any]


class BeatweaveControlSurface:
    """Local MCP bridge to the normal Beatweave application API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        requester: Requester | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.requester = requester or self._http_request

    def get_project(self) -> dict[str, Any]:
        return {"project": self._request("GET", "/projects/current")}

    def get_timeline(self) -> dict[str, Any]:
        return self._request("GET", "/timeline")

    def get_scenes(self, scene_id: str | None = None) -> dict[str, Any]:
        timeline = self.get_timeline()
        scenes = timeline["scenes"]
        if scene_id is not None:
            scenes = [scene for scene in scenes if scene["id"] == scene_id]
            if not scenes:
                raise ToolError(
                    json.dumps({"code": "scene_not_found", "message": "Scene not found."})
                )
        return {"scenes": scenes}

    def get_jobs(self, states: list[JobState] | None = None, limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 500:
            raise ToolError(
                json.dumps(
                    {
                        "code": "invalid_job_limit",
                        "message": "limit must be between 1 and 500.",
                    }
                )
            )
        query = urlencode(
            [("state", state.value) for state in states or []],
            doseq=True,
        )
        path = f"/jobs?{query}" if query else "/jobs"
        jobs = self._request("GET", path)
        return {"jobs": jobs[:limit]}

    def update_scene(self, scene_id: str, update: UpdateSceneRequest) -> dict[str, Any]:
        timeline = self._request(
            "PATCH", f"/timeline/scenes/{scene_id}", update.model_dump(mode="json")
        )
        scene = next(item for item in timeline["scenes"] if item["id"] == scene_id)
        return {"scene": scene}

    def generate_visual_plan(self, confirm_overwrite: bool = False) -> dict[str, Any]:
        return self._request(
            "POST",
            "/planning/visual-plan",
            {"confirm_overwrite": confirm_overwrite},
        )

    def render_keyframe(self, keyframe_id: str, request: GenerateKeyframeRequest) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/keyframes/{keyframe_id}/generate",
            request.model_dump(mode="json"),
        )

    def render_scene(self, scene_id: str, request: RenderSceneRequest) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/scenes/{scene_id}/renders",
            request.model_dump(mode="json"),
        )

    def select_take(self, scene_id: str, take_id: str) -> dict[str, Any]:
        return self._request("POST", f"/scenes/{scene_id}/takes/{take_id}/select")

    def export_project(self, request: ExportRequest) -> dict[str, Any]:
        return self._request("POST", "/exports", request.model_dump(mode="json"))

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            return self.requester(method, path, body)
        except ToolError:
            raise
        except Exception as error:
            raise ToolError(
                json.dumps(
                    {
                        "code": "backend_request_failed",
                        "message": "The Beatweave backend request failed.",
                    }
                )
            ) from error

    def _http_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = response.read()
        except HTTPError as error:
            try:
                response = json.loads(error.read())
                detail = response.get("error", response)
            except (json.JSONDecodeError, AttributeError):
                detail = {
                    "code": "backend_http_error",
                    "message": f"Beatweave returned HTTP {error.code}.",
                }
            raise ToolError(json.dumps(detail, ensure_ascii=False, default=str)) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ToolError(
                json.dumps(
                    {
                        "code": "backend_unavailable",
                        "message": (
                            f"Beatweave is unavailable at {self.base_url}. "
                            "Start the desktop app or backend and try again."
                        ),
                    }
                )
            ) from error
        return json.loads(payload) if payload else None
