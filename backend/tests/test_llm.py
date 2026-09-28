import json
import logging
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.errors import BeatweaveError
from beatweave.llm.provider import OpenAICompatibleProvider
from beatweave.llm.schemas import (
    LLMProviderConfig,
    ScenePlan,
    StructuredGenerationRequest,
    VisualPlan,
)
from beatweave.main import create_app


def make_client(database_path: Path) -> TestClient:
    settings = Settings(data_dir=database_path.parent, database_path=database_path)
    return TestClient(create_app(settings))


class FakeResponse:
    status = 200

    def __init__(self, body: dict[str, object]) -> None:
        self.body = json.dumps(body).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def completion(content: str) -> FakeResponse:
    return FakeResponse({"choices": [{"message": {"content": content}}]})


def test_default_provider_config_targets_ollama(tmp_path: Path) -> None:
    with make_client(tmp_path / "beatweave.db") as client:
        assert client.get("/llm/config").json() == {
            "provider": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen3:8b",
            "timeout_seconds": 30.0,
            "api_key_configured": False,
        }


def test_provider_config_persists_without_changing_project(tmp_path: Path) -> None:
    database_path = tmp_path / "beatweave.db"
    project_parent = tmp_path / "projects"
    project_parent.mkdir()

    with make_client(database_path) as client:
        created = client.post(
            "/projects", json={"name": "Provider Test", "parent_directory": str(project_parent)}
        )
        assert created.status_code == 201
        project_database = Path(created.json()["path"]) / "project.db"
        project_before = project_database.read_bytes()

        response = client.put(
            "/llm/config",
            json={
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:9999/v1/",
                "model": "qwen-local",
                "timeout_seconds": 12,
                "api_key": "secret-value",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "provider": "openai_compatible",
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "qwen-local",
            "timeout_seconds": 12.0,
            "api_key_configured": True,
        }
        assert "secret-value" not in response.text
        assert project_database.read_bytes() == project_before

    with make_client(database_path) as reopened:
        assert reopened.get("/llm/config").json()["model"] == "qwen-local"


def test_offline_provider_does_not_break_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*_: object, **__: object) -> None:
        raise URLError("connection refused and secret details")

    monkeypatch.setattr("beatweave.llm.provider.urlopen", offline)
    with make_client(tmp_path / "beatweave.db") as client:
        response = client.post("/llm/test")
        assert response.status_code == 200
        assert response.json() == {
            "available": False,
            "message": "Provider is offline or unreachable.",
        }
        assert client.get("/health").is_success


def test_structured_generation_repairs_and_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            completion("not json"),
            completion(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "scene_id": "scene-1",
                                "concept": "A luminous city wakes",
                                "image_prompt": "Wide neon city at dawn",
                                "video_prompt": "Slow aerial push forward",
                                "visual_energy": 0.6,
                                "motion_energy": 0.4,
                            }
                        ]
                    }
                )
            ),
        ]
    )
    monkeypatch.setattr("beatweave.llm.provider.urlopen", lambda *_args, **_kwargs: next(responses))
    provider = OpenAICompatibleProvider(LLMProviderConfig(model="test-model"))

    result = provider.generate_structured(
        StructuredGenerationRequest(system_prompt="Plan scenes.", user_prompt="Use one scene."),
        ScenePlan,
    )

    assert result.repaired is True
    assert result.output.scenes[0].scene_id == "scene-1"


def test_invalid_structured_output_is_rejected_without_leaking_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "beatweave.llm.provider.urlopen",
        lambda *_args, **_kwargs: completion('{"concept": "incomplete"}'),
    )
    provider = OpenAICompatibleProvider(
        LLMProviderConfig(model="test-model", api_key="never-log-this")
    )

    with caplog.at_level(logging.INFO), pytest.raises(BeatweaveError) as raised:
        provider.generate_structured(
            StructuredGenerationRequest(system_prompt="Plan visuals.", user_prompt="Make a plan."),
            VisualPlan,
        )

    assert raised.value.code == "invalid_llm_output"
    assert "never-log-this" not in caplog.text


def test_planning_schemas_forbid_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ScenePlan.model_validate(
            {
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "concept": "Concept",
                        "image_prompt": "Image",
                        "video_prompt": "Video",
                        "visual_energy": 0.5,
                        "motion_energy": 0.5,
                        "backend_node_id": "forbidden",
                    }
                ]
            }
        )
