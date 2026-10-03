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
from beatweave.mcp.server import create_mcp_server
from beatweave.project.schemas import AssetMetadata, CreateProjectRequest
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.service import TimelineService


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
                "get_timeline",
                "get_scenes",
                "get_jobs",
                "update_scene",
                "generate_visual_plan",
                "render_keyframe",
                "render_scene",
                "select_take",
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

            jobs = await client.call_tool("get_jobs", {"states": ["queued"]})
            assert jobs.structured_content == {"jobs": []}


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
