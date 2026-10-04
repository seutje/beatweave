import argparse
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from beatweave import __version__
from beatweave.config import Settings, get_settings
from beatweave.exports.schemas import ExportRequest
from beatweave.jobs.schemas import JobState
from beatweave.keyframes.schemas import GenerateKeyframeRequest, ImportKeyframeRequest
from beatweave.mcp.control import BeatweaveControlSurface, Requester
from beatweave.media.schemas import ImportAudioRequest
from beatweave.project.schemas import CreateProjectRequest, OpenProjectRequest
from beatweave.timeline.schemas import (
    ApplyLayoutRequest,
    ProposedBoundary,
    SuggestLayoutRequest,
    UpdateKeyframeRequest,
    UpdateSceneRequest,
)
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
        description="Local end-to-end control surface for Beatweave projects.",
        instructions=(
            "Create or inspect a project before mutating it. Audio analysis, render, and export "
            "tools enqueue durable jobs and return immediately; use get_job to inspect their "
            "state. An agent may author prompts and import its own keyframe images without an "
            "LLM or ComfyUI."
        ),
        version=__version__,
    )

    @server.tool(annotations=READ_ONLY)
    def get_project() -> dict[str, Any]:
        """Return the currently open Beatweave project, or null when none is open."""
        return control.get_project()

    @server.tool(annotations=MUTATION)
    def create_project(name: str, parent_directory: str) -> dict[str, Any]:
        """Create and open a portable Beatweave project in an existing parent directory."""
        return control.create_project(
            CreateProjectRequest(name=name, parent_directory=parent_directory)
        )

    @server.tool(annotations=MUTATION)
    def open_project(path: str) -> dict[str, Any]:
        """Open an existing Beatweave project directory or project.db path."""
        return control.open_project(OpenProjectRequest(path=path))

    @server.tool(annotations=MUTATION)
    def import_audio(path: str) -> dict[str, Any]:
        """Copy a local audio file into the active project and create its waveform."""
        return control.import_audio(ImportAudioRequest(path=path))

    @server.tool(annotations=READ_ONLY)
    def get_analysis() -> dict[str, Any]:
        """Return the active track analysis, or null before analysis completes."""
        return control.get_analysis()

    @server.tool(annotations=MUTATION)
    def start_analysis(force: bool = False) -> dict[str, Any]:
        """Enqueue durable beat, downbeat, and energy analysis for the active track."""
        return control.start_analysis(force)

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

    @server.tool(annotations=READ_ONLY)
    def get_job(job_id: str) -> dict[str, Any]:
        """Return one persisted job by ID for precise polling and failure inspection."""
        return control.get_job(job_id)

    @server.tool(annotations=READ_ONLY)
    def suggest_layout(
        preferred_length_seconds: float = 6,
        minimum_length_seconds: float = 2,
    ) -> dict[str, Any]:
        """Propose beat-aware contiguous scene boundaries without changing the timeline."""
        return control.suggest_layout(
            SuggestLayoutRequest(
                preferred_length_seconds=preferred_length_seconds,
                minimum_length_seconds=minimum_length_seconds,
            )
        )

    @server.tool(annotations=MUTATION)
    def apply_layout(boundaries: list[ProposedBoundary]) -> dict[str, Any]:
        """Replace the timeline with a previously reviewed layout proposal."""
        return control.apply_layout(ApplyLayoutRequest(boundaries=boundaries))

    @server.tool(annotations=MUTATION)
    def update_scene(scene_id: str, update: UpdateSceneRequest) -> dict[str, Any]:
        """Edit one scene's creative fields through the normal timeline history service."""
        return control.update_scene(scene_id, update)

    @server.tool(annotations=MUTATION)
    def update_keyframe(keyframe_id: str, prompt: str) -> dict[str, Any]:
        """Set an existing shared keyframe's editable image prompt through timeline history."""
        return control.update_keyframe(keyframe_id, UpdateKeyframeRequest(prompt=prompt))

    @server.tool(annotations=READ_ONLY)
    def get_keyframe(keyframe_id: str) -> dict[str, Any]:
        """Return one keyframe with its variants, adjacent scenes, and render jobs."""
        return control.get_keyframe(keyframe_id)

    @server.tool(annotations=MUTATION)
    def import_keyframe_image(
        keyframe_id: str,
        path: str,
        confirm_stale_renders: bool = False,
    ) -> dict[str, Any]:
        """Copy and select an agent-generated PNG, JPEG, or WebP for a shared keyframe."""
        return control.import_keyframe_image(
            keyframe_id,
            ImportKeyframeRequest(path=path, confirm_stale_renders=confirm_stale_renders),
        )

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

    @server.tool(annotations=READ_ONLY)
    def get_video_takes(scene_id: str | None = None) -> dict[str, Any]:
        """List video takes and render jobs for one scene or the whole timeline."""
        return control.get_video_takes(scene_id)

    @server.tool(annotations=READ_ONLY)
    def check_wan2gp() -> dict[str, Any]:
        """Check whether the configured Wan2GP service and required endpoints are ready."""
        return control.check_wan2gp()

    @server.tool(annotations=READ_ONLY)
    def get_export_readiness() -> dict[str, Any]:
        """Report missing, stale, mismatched, or unavailable selected scene takes."""
        return control.get_export_readiness()

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
