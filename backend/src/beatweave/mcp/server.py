import argparse
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from beatweave import __version__
from beatweave.config import Settings, get_settings
from beatweave.exports.schemas import ExportRequest
from beatweave.jobs.schemas import JobState
from beatweave.keyframes.schemas import GenerateKeyframeRequest
from beatweave.mcp.control import BeatweaveControlSurface, Requester
from beatweave.timeline.schemas import UpdateSceneRequest
from beatweave.video_takes.schemas import RenderSceneRequest

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
MUTATION = ToolAnnotations(read_only_hint=False, destructive_hint=False)


def create_mcp_server(
    settings: Settings | None = None, *, requester: Requester | None = None
) -> MCPServer:
    app_settings = settings or get_settings()
    host = app_settings.host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    control = BeatweaveControlSurface(
        f"http://{host}:{app_settings.port}",
        timeout_seconds=app_settings.mcp_request_timeout_seconds,
        requester=requester,
    )
    server = MCPServer(
        name="beatweave",
        title="Beatweave",
        description="Optional local control surface for the active Beatweave project.",
        instructions=(
            "Inspect the current project before mutating it. Render and export tools enqueue "
            "durable jobs and return immediately; use get_jobs to inspect their state."
        ),
        version=__version__,
    )

    @server.tool(annotations=READ_ONLY)
    def get_project() -> dict[str, Any]:
        """Return the currently open Beatweave project, or null when none is open."""
        return control.get_project()

    @server.tool(annotations=READ_ONLY)
    def get_timeline() -> dict[str, Any]:
        """Return the active timeline with scenes, shared keyframes, timing, and selection state."""
        return control.get_timeline()

    @server.tool(annotations=READ_ONLY)
    def get_scenes(scene_id: str | None = None) -> dict[str, Any]:
        """List timeline scenes, optionally restricted to one exact scene ID."""
        return control.get_scenes(scene_id)

    @server.tool(annotations=READ_ONLY)
    def get_jobs(states: list[JobState] | None = None, limit: int = 100) -> dict[str, Any]:
        """List persisted jobs for the active project, optionally filtered by state."""
        return control.get_jobs(states, limit)

    @server.tool(annotations=MUTATION)
    def update_scene(scene_id: str, update: UpdateSceneRequest) -> dict[str, Any]:
        """Edit one scene's creative fields through the normal timeline history service."""
        return control.update_scene(scene_id, update)

    @server.tool(annotations=MUTATION)
    def generate_visual_plan(confirm_overwrite: bool = False) -> dict[str, Any]:
        """Generate a validated project visual plan without changing scene timing."""
        return control.generate_visual_plan(confirm_overwrite)

    @server.tool(annotations=MUTATION)
    def render_keyframe(keyframe_id: str, request: GenerateKeyframeRequest) -> dict[str, Any]:
        """Enqueue a durable ComfyUI keyframe render and return its job."""
        return control.render_keyframe(keyframe_id, request)

    @server.tool(annotations=MUTATION)
    def render_scene(scene_id: str, request: RenderSceneRequest) -> dict[str, Any]:
        """Enqueue a durable Wan2GP scene render and return its job."""
        return control.render_scene(scene_id, request)

    @server.tool(annotations=MUTATION)
    def select_take(scene_id: str, take_id: str) -> dict[str, Any]:
        """Select an existing immutable video take for one scene."""
        return control.select_take(scene_id, take_id)

    @server.tool(annotations=MUTATION)
    def export_project(request: ExportRequest) -> dict[str, Any]:
        """Validate the selected sequence and enqueue a durable final export job."""
        return control.export_project(request)

    return server


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Beatweave MCP control surface.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=8421, help="HTTP bind port.")
    return parser


def run_server(
    transport: Literal["stdio", "streamable-http"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8421,
) -> None:
    server = create_mcp_server()
    if transport == "streamable-http":
        server.run(
            transport="streamable-http",
            host=host,
            port=port,
            streamable_http_path="/mcp",
        )
        return
    server.run(transport="stdio")


def main() -> None:
    arguments = build_argument_parser().parse_args()
    run_server(arguments.transport, arguments.host, arguments.port)


if __name__ == "__main__":
    main()
