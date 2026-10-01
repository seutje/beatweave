import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beatweave.comfyui.profile import NODE_IDS, REQUIRED_NODE_CLASSES, build_workflow
from beatweave.comfyui.schemas import ComfyUIConfig, ImageRenderRequest
from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.project.store import ProjectStore


class FakeResponse:
    def __init__(self, body: dict | bytes) -> None:
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def object_info() -> dict:
    result = {name: {"input": {"required": {}}} for name in REQUIRED_NODE_CLASSES}
    result["UNETLoader"]["input"]["required"]["unet_name"] = [
        ["qwen_image_2.1_int8_convrot.safetensors"]
    ]
    result["CLIPLoader"]["input"]["required"]["clip_name"] = [
        ["qwen3vl_8b_int8_convrot.safetensors"]
    ]
    result["VAELoader"]["input"]["required"]["vae_name"] = [["qwen_image_2.1_vae_bf16.safetensors"]]
    return result


def create_project(client: TestClient, tmp_path: Path) -> dict:
    parent = tmp_path / "projects"
    parent.mkdir(exist_ok=True)
    response = client.post(
        "/projects", json={"name": "Comfy Test", "parent_directory": str(parent)}
    )
    assert response.status_code == 201
    return response.json()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("render job did not finish")


def test_profile_maps_canonical_request_without_leaking_node_ids() -> None:
    request = ImageRenderRequest(
        prompt="A luminous abstract wave",
        negative_prompt="text",
        width=640,
        height=384,
        seed=42,
        steps=7,
        cfg=1.5,
        output_name="mapped",
    )
    config = ComfyUIConfig()

    workflow = build_workflow(request, config.profile, "job-123456")

    assert workflow[NODE_IDS["conditioning"]]["inputs"]["prompt"] == request.prompt
    assert workflow[NODE_IDS["latent"]]["inputs"]["width"] == 640
    assert workflow[NODE_IDS["sampler"]]["inputs"]["seed"] == 42
    assert workflow[NODE_IDS["save"]]["inputs"]["filename_prefix"].startswith("beatweave/mapped-")
    assert "class_type" in workflow[NODE_IDS["model"]]
    assert "node" not in request.model_dump_json()


def test_profile_maps_reference_images_into_qwen_conditioning() -> None:
    workflow = build_workflow(
        ImageRenderRequest(prompt="Continue this visual"),
        ComfyUIConfig().profile,
        "job-reference",
        ["previous.png", "style.png"],
    )

    assert workflow["100"]["inputs"]["image"] == "previous.png"
    assert workflow["101"]["inputs"]["image"] == "style.png"
    conditioning = workflow[NODE_IDS["conditioning"]]["inputs"]
    assert conditioning["images.image_1"] == ["100", 0]
    assert conditioning["images.image_2"] == ["101", 0]


def test_config_persists_and_offline_comfyui_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*_: object, **__: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("beatweave.comfyui.adapter.urlopen", offline)
    database_path = tmp_path / "application.db"
    with TestClient(create_app(Settings(database_path=database_path))) as client:
        saved = client.put(
            "/comfyui/config",
            json={
                "base_url": "http://127.0.0.1:9199/",
                "request_timeout_seconds": 4,
                "render_timeout_seconds": 120,
                "poll_interval_seconds": 0.2,
                "profile": ComfyUIConfig().profile.model_dump(mode="json"),
            },
        )
        assert saved.status_code == 200
        status = client.post("/comfyui/test")
        assert status.json() == {
            "available": False,
            "profile_ready": False,
            "message": "ComfyUI is offline or unreachable.",
            "version": None,
            "device": None,
        }
        assert client.get("/health").is_success

    with TestClient(create_app(Settings(database_path=database_path))) as reopened:
        assert reopened.get("/comfyui/config").json()["base_url"] == "http://127.0.0.1:9199"


def test_render_submits_tracks_downloads_and_registers_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    submitted: list[dict] = []

    def fake_urlopen(request, **_kwargs):
        path = request.full_url
        if path.endswith("/object_info"):
            return FakeResponse(object_info())
        if path.endswith("/prompt"):
            submitted.append(json.loads(request.data))
            return FakeResponse({"prompt_id": "prompt-1", "node_errors": {}})
        if path.endswith("/history/prompt-1"):
            return FakeResponse(
                {
                    "prompt-1": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "render.png",
                                        "subfolder": "beatweave",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                        "status": {"status_str": "success", "completed": True},
                    }
                }
            )
        if "/view?" in path:
            return FakeResponse(b"fake-png-bytes")
        raise AssertionError(path)

    monkeypatch.setattr("beatweave.comfyui.adapter.urlopen", fake_urlopen)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project = create_project(client, tmp_path)
        response = client.post(
            "/comfyui/renders",
            json={
                "prompt": "Iridescent liquid geometry",
                "width": 512,
                "height": 512,
                "seed": 7,
                "steps": 3,
                "output_name": "phase-12",
            },
        )
        assert response.status_code == 202
        job = wait_for_job(client, response.json()["job"]["id"])

    assert job["state"] == "complete"
    assert job["output"]["comfyui_prompt_id"] == "prompt-1"
    asset = ProjectStore(project["path"]).get_asset(job["output"]["asset_id"])
    assert asset is not None
    assert asset.kind == "generated_image"
    assert (Path(project["path"]) / asset.relative_path).read_bytes() == b"fake-png-bytes"
    assert submitted[0]["prompt"][NODE_IDS["conditioning"]]["inputs"]["prompt"] == (
        "Iridescent liquid geometry"
    )


def test_execution_failure_is_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, **_kwargs):
        if request.full_url.endswith("/object_info"):
            return FakeResponse(object_info())
        if request.full_url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "failed-prompt", "node_errors": {}})
        if request.full_url.endswith("/history/failed-prompt"):
            return FakeResponse(
                {
                    "failed-prompt": {
                        "outputs": {},
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [
                                [
                                    "execution_error",
                                    {"exception_message": "synthetic ComfyUI failure"},
                                ]
                            ],
                        },
                    }
                }
            )
        raise AssertionError(request.full_url)

    monkeypatch.setattr("beatweave.comfyui.adapter.urlopen", fake_urlopen)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        create_project(client, tmp_path)
        started = client.post(
            "/comfyui/renders", json={"prompt": "Fail safely", "width": 256, "height": 256}
        ).json()
        job = wait_for_job(client, started["job"]["id"])

    assert job["state"] == "failed"
    assert job["error"]["code"] == "comfyui_execution_failed"
    assert job["error"]["message"] == "synthetic ComfyUI failure"


@pytest.mark.skipif(
    os.environ.get("BEATWEAVE_RUN_COMFYUI_INTEGRATION") != "1",
    reason="Set BEATWEAVE_RUN_COMFYUI_INTEGRATION=1 for a live image render",
)
def test_live_comfyui_render_survives_beatweave_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "application.db"
    app = create_app(Settings(database_path=database_path))
    with TestClient(app) as client:
        project = create_project(client, tmp_path)
        assert client.post("/comfyui/test").json()["profile_ready"] is True
        started = client.post(
            "/comfyui/renders",
            json={
                "prompt": (
                    "Abstract luminous cyan and violet ribbons on black, "
                    "minimal composition, no text"
                ),
                "width": 256,
                "height": 256,
                "steps": 2,
                "seed": 12,
                "output_name": "phase-12-live",
            },
        ).json()
        completed = wait_for_job(client, started["job"]["id"], timeout=900)
        assert completed["state"] == "complete", completed.get("error")

    with TestClient(create_app(Settings(database_path=database_path))) as restarted:
        assert restarted.post("/comfyui/test").json()["profile_ready"] is True
        reopened = restarted.post("/projects/open", json={"path": project["path"]})
        assert reopened.status_code == 200
        persisted = restarted.get(f"/jobs/{completed['id']}").json()
        assert Path(project["path"], persisted["output"]["relative_path"]).is_file()
