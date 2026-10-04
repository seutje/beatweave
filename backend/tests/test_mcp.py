import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from beatweave.config import Settings
from beatweave.database import Database
from beatweave.main import create_app
from beatweave.mcp.server import build_argument_parser, create_mcp_server
from beatweave.project.schemas import AssetMetadata, CreateProjectRequest
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.service import TimelineService


def test_mcp_http_command_line_defaults_and_overrides() -> None:
    parser = build_argument_parser()
    defaults = parser.parse_args([])
    assert (defaults.transport, defaults.host, defaults.port) == ("stdio", "127.0.0.1", 8421)

    configured = parser.parse_args(
        ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "9123"]
    )
    assert (configured.transport, configured.host, configured.port) == (
        "streamable-http",
        "127.0.0.1",
        9123,
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def prepare_project(settings: Settings, parent: Path) -> tuple[dict, dict]:
    database = Database(settings.resolved_database_path)
    database.initialize()
    parent.mkdir()
    projects = ProjectService(database)
    project = projects.create(
        CreateProjectRequest(name="MCP Project", parent_directory=str(parent))
    )
    store = ProjectStore(project.path)
    asset = AssetMetadata(
        id="mcp-audio",
        kind="audio",
        relative_path="source/track.wav",
        filename="track.wav",
        sha256="mcp-audio-hash",
        size_bytes=1,
        media_metadata={"duration_seconds": 8, "sample_rate": 48000, "channels": 2},
        created_at=datetime.now(UTC),
    )
    (Path(project.path) / asset.relative_path).write_bytes(b"0")
    store.insert_asset(asset)
    projects.set_audio_asset(project, asset.id)
    timeline = TimelineService(projects).create_scene(None, None)
    database.close()
    return project.model_dump(mode="json"), timeline.model_dump(mode="json")


def api_requester(client: TestClient):
    def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        response = client.request(method, path, json=body)
        if response.is_error:
            raise ToolError(json.dumps(response.json()["error"]))
        return response.json()

    return request


@pytest.mark.anyio
async def test_mcp_lists_complete_control_surface_and_returns_clear_errors(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "application.db")
    with TestClient(create_app(settings)) as api:
        server = create_mcp_server(settings, requester=api_requester(api))
        async with Client(server, raise_exceptions=True) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "get_project",
                "create_project",
                "open_project",
                "import_audio",
                "get_analysis",
                "start_analysis",
                "get_timeline",
                "get_scenes",
                "get_jobs",
                "get_job",
                "suggest_layout",
                "apply_layout",
                "update_scene",
                "update_keyframe",
                "get_keyframe",
                "import_keyframe_image",
                "generate_visual_plan",
                "render_keyframe",
                "render_scene",
                "select_take",
                "get_video_takes",
                "check_wan2gp",
                "get_export_readiness",
                "export_project",
            }
            annotations = {tool.name: tool.annotations for tool in tools.tools}
            assert annotations["get_project"].read_only_hint is True
            assert annotations["update_scene"].read_only_hint is False

            project = await client.call_tool("get_project", {})
            assert project.is_error is False
            assert project.structured_content == {"project": None}

            timeline = await client.call_tool("get_timeline", {})
            assert timeline.is_error is True
            assert '"code": "project_not_open"' in timeline.content[0].text


@pytest.mark.anyio
async def test_mcp_reads_and_updates_project_through_timeline_service(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "application.db")
    expected_project, expected_timeline = prepare_project(settings, tmp_path / "projects")
    scene_id = expected_timeline["scenes"][0]["id"]
    with TestClient(create_app(settings)) as api:
        server = create_mcp_server(settings, requester=api_requester(api))
        async with Client(server, raise_exceptions=True) as client:
            project = await client.call_tool("get_project", {})
            assert project.structured_content["project"]["id"] == expected_project["id"]

            timeline = await client.call_tool("get_timeline", {})
            assert timeline.structured_content["scenes"][0]["id"] == scene_id
            assert len(timeline.structured_content["keyframes"]) == 2

            scenes = await client.call_tool("get_scenes", {"scene_id": scene_id})
            assert [scene["id"] for scene in scenes.structured_content["scenes"]] == [scene_id]

            updated = await client.call_tool(
                "update_scene",
                {
                    "scene_id": scene_id,
                    "update": {
                        "concept": "MCP concept",
                        "image_prompt": "MCP image",
                        "video_prompt": "MCP motion",
                        "approved": True,
                    },
                },
            )
            assert updated.is_error is False
            assert updated.structured_content["scene"]["concept"] == "MCP concept"
            assert updated.structured_content["scene"]["approved"] is True

            keyframe_id = expected_timeline["keyframes"][0]["id"]
            updated_keyframe = await client.call_tool(
                "update_keyframe",
                {"keyframe_id": keyframe_id, "prompt": "Agent-authored image prompt"},
            )
            assert updated_keyframe.structured_content["keyframe"]["prompt"] == (
                "Agent-authored image prompt"
            )

            image_path = tmp_path / "agent-frame.png"
            image_path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                    "AAAAC0lEQVR42mP8/x8AAusB9Y9ZlYQAAAAASUVORK5CYII="
                )
            )
            imported = await client.call_tool(
                "import_keyframe_image",
                {"keyframe_id": keyframe_id, "path": str(image_path)},
            )
            assert imported.is_error is False
            assert imported.structured_content["detail"]["keyframe"]["selected_variant_id"]

            detail = await client.call_tool("get_keyframe", {"keyframe_id": keyframe_id})
            assert detail.structured_content["detail"]["variants"][0]["prompt"] == (
                "Agent-authored image prompt"
            )

            jobs = await client.call_tool("get_jobs", {"states": ["queued"]})
            assert jobs.structured_content == {"jobs": []}


@pytest.mark.anyio
async def test_mcp_project_setup_tools_delegate_to_application_api(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "application.db")
    calls: list[tuple[str, str, object]] = []

    def requester(method: str, path: str, body: dict[str, Any] | None) -> Any:
        calls.append((method, path, body))
        if path == "/projects":
            return {"id": "project-1"}
        if path == "/projects/open":
            return {"id": "project-2"}
        if path == "/media/audio/import":
            return {"asset": {"id": "audio-1"}}
        if path == "/analysis":
            return {"id": "analysis-1"}
        if path.startswith("/analysis?"):
            return {"id": "analysis-job"}
        if path == "/jobs/analysis-job":
            return {"id": "analysis-job", "state": "complete"}
        if path == "/timeline/layout/suggest":
            return {"boundaries": [{"time": 0}, {"time": 8}]}
        if path == "/timeline/layout/apply":
            return {"scenes": [{"id": "scene-1"}], "keyframes": []}
        if path == "/scenes/takes":
            return {"scenes": []}
        if path == "/wan2gp/test":
            return {"available": True}
        if path == "/exports/readiness":
            return {"ready": True, "issues": []}
        raise AssertionError(f"Unexpected request: {method} {path} {body}")

    server = create_mcp_server(settings, requester=requester)
    async with Client(server, raise_exceptions=True) as client:
        created = await client.call_tool(
            "create_project",
            {"name": "Agent Project", "parent_directory": str(tmp_path)},
        )
        opened = await client.call_tool("open_project", {"path": str(tmp_path / "project")})
        imported = await client.call_tool("import_audio", {"path": str(tmp_path / "track.wav")})
        analysis = await client.call_tool("get_analysis", {})
        started = await client.call_tool("start_analysis", {"force": True})
        job = await client.call_tool("get_job", {"job_id": "analysis-job"})
        proposal = await client.call_tool(
            "suggest_layout",
            {"preferred_length_seconds": 8, "minimum_length_seconds": 2},
        )
        applied = await client.call_tool(
            "apply_layout",
            {
                "boundaries": [
                    {"time": 0, "reason": "track_start"},
                    {"time": 8, "reason": "track_end"},
                ]
            },
        )
        takes = await client.call_tool("get_video_takes", {})
        wan2gp = await client.call_tool("check_wan2gp", {})
        readiness = await client.call_tool("get_export_readiness", {})

    assert created.structured_content == {"project": {"id": "project-1"}}
    assert opened.structured_content == {"project": {"id": "project-2"}}
    assert imported.structured_content["asset"]["id"] == "audio-1"
    assert analysis.structured_content["analysis"]["id"] == "analysis-1"
    assert started.structured_content["job"]["id"] == "analysis-job"
    assert job.structured_content["job"]["state"] == "complete"
    assert proposal.structured_content["proposal"]["boundaries"][-1]["time"] == 8
    assert applied.structured_content["scenes"][0]["id"] == "scene-1"
    assert takes.structured_content == {"detail": {"scenes": []}}
    assert wan2gp.structured_content == {"status": {"available": True}}
    assert readiness.structured_content == {"readiness": {"ready": True, "issues": []}}
    assert calls == [
        ("POST", "/projects", {"name": "Agent Project", "parent_directory": str(tmp_path)}),
        ("POST", "/projects/open", {"path": str(tmp_path / "project")}),
        ("POST", "/media/audio/import", {"path": str(tmp_path / "track.wav")}),
        ("GET", "/analysis", None),
        ("POST", "/analysis?force=true", None),
        ("GET", "/jobs/analysis-job", None),
        (
            "POST",
            "/timeline/layout/suggest",
            {"preferred_length_seconds": 8.0, "minimum_length_seconds": 2.0},
        ),
        (
            "POST",
            "/timeline/layout/apply",
            {
                "boundaries": [
                    {
                        "time": 0.0,
                        "beat_index": None,
                        "reason": "track_start",
                        "energy_change": 0.0,
                    },
                    {
                        "time": 8.0,
                        "beat_index": None,
                        "reason": "track_end",
                        "energy_change": 0.0,
                    },
                ]
            },
        ),
        ("GET", "/scenes/takes", None),
        ("POST", "/wan2gp/test", None),
        ("GET", "/exports/readiness", None),
    ]


@pytest.mark.anyio
async def test_mcp_mutation_tools_validate_inputs_and_delegate(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "application.db")
    calls: list[tuple[str, str, object]] = []

    def requester(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        calls.append((method, path, body))
        if path == "/planning/visual-plan":
            return {"generated": True}
        if path.startswith("/keyframes/"):
            return {"job": {"id": "keyframe-job"}}
        if path.endswith("/renders"):
            return {"job": {"id": "scene-job"}}
        if path.endswith("/select"):
            return {"detail": {"selected_take_id": "take-1"}}
        return {"job": {"id": "export-job"}}

    server = create_mcp_server(settings, requester=requester)

    async with Client(server, raise_exceptions=True) as client:
        plan = await client.call_tool("generate_visual_plan", {"confirm_overwrite": True})
        keyframe = await client.call_tool(
            "render_keyframe",
            {"keyframe_id": "keyframe-1", "request": {"quality_mode": "final"}},
        )
        scene = await client.call_tool(
            "render_scene",
            {"scene_id": "scene-1", "request": {"quality_mode": "preview"}},
        )
        selected = await client.call_tool(
            "select_take", {"scene_id": "scene-1", "take_id": "take-1"}
        )
        exported = await client.call_tool("export_project", {"request": {"filename": "mcp-output"}})

    assert plan.structured_content == {"generated": True}
    assert keyframe.structured_content["job"]["id"] == "keyframe-job"
    assert scene.structured_content["job"]["id"] == "scene-job"
    assert selected.structured_content["detail"]["selected_take_id"] == "take-1"
    assert exported.structured_content["job"]["id"] == "export-job"
    assert calls == [
        ("POST", "/planning/visual-plan", {"confirm_overwrite": True}),
        (
            "POST",
            "/keyframes/keyframe-1/generate",
            {
                "prompt": None,
                "negative_prompt": "",
                "width": None,
                "height": None,
                "seed": None,
                "steps": None,
                "cfg": None,
                "include_global_style_references": True,
                "include_previous_keyframe": True,
                "additional_reference_asset_ids": [],
                "reference_mode": "semantic",
                "quality_mode": "final",
            },
        ),
        (
            "POST",
            "/scenes/scene-1/renders",
            {
                "quality_mode": "preview",
                "source_take_id": None,
                "select_on_complete": False,
            },
        ),
        ("POST", "/scenes/scene-1/takes/take-1/select", None),
        (
            "POST",
            "/exports",
            {
                "filename": "mcp-output.mp4",
                "codec": "h264",
                "crf": 18,
                "frame_rate": 24,
                "width": 1920,
                "height": 1080,
            },
        ),
    ]
