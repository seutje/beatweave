import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.analysis.schemas import AnalysisParameters, AudioAnalysis, EnergySample
from beatweave.config import Settings
from beatweave.llm.provider import LLMProvider
from beatweave.llm.schemas import (
    ProviderAvailability,
    ScenePlan,
    ScenePlanItem,
    StructuredGenerationResponse,
    VisualPlan,
    VisualTrajectoryStage,
)
from beatweave.main import create_app
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore


class FakePlanningProvider(LLMProvider):
    def __init__(self) -> None:
        self.release_after: list[bool] = []
        self.release_count = 0
        self.contexts: list[dict[str, object]] = []
        self.invalid_ids = False

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability(available=True, message="available")

    def release(self) -> None:
        self.release_count += 1

    def generate_structured(self, request, output_type, *, release_after=False):
        self.release_after.append(release_after)
        context = json.loads(request.user_prompt)
        self.contexts.append(context)
        if output_type is VisualPlan:
            output = VisualPlan(
                concept="Generated concept",
                style="Generated style",
                motifs=["glass"],
                palette=["cyan"],
                narrative_arc="calm to intense",
                visual_trajectory=[
                    VisualTrajectoryStage(position=0, description="Quiet geometry", intensity=0.2),
                    VisualTrajectoryStage(
                        position=1, description="Luminous release", intensity=0.9
                    ),
                ],
            )
        else:
            scenes = context["scenes"]
            output = ScenePlan(
                scenes=[
                    ScenePlanItem(
                        scene_id="invented-id" if self.invalid_ids else scene["scene_id"],
                        concept=f"Concept {scene['position']}",
                        image_prompt=f"Image {scene['position']}",
                        video_prompt=f"Motion {scene['position']}",
                        visual_energy=scene["average_energy"],
                        motion_energy=scene["peak_energy"],
                    )
                    for scene in scenes
                ]
            )
        return StructuredGenerationResponse(output=output, model="fake")


def prepare_project(client: TestClient, parent: Path) -> tuple[Path, FakePlanningProvider]:
    parent.mkdir()
    project = client.post(
        "/projects", json={"name": "Planning Test", "parent_directory": str(parent)}
    ).json()
    directory = Path(project["path"])
    store = ProjectStore(directory)
    asset = AssetMetadata(
        id="audio-1",
        kind="audio",
        relative_path="source/track.wav",
        filename="track.wav",
        sha256="planning-audio",
        size_bytes=100,
        media_metadata={"duration_seconds": 10, "sample_rate": 48000, "channels": 2},
        created_at=datetime.now(UTC),
    )
    store.insert_asset(asset)
    store.update_project(store.read_project().model_copy(update={"audio_asset_id": asset.id}))
    store.insert_analysis(
        AudioAnalysis(
            id="analysis-1",
            asset_id=asset.id,
            source_sha256=asset.sha256,
            bpm_estimate=120,
            beats=[0, 0.5, 1, 1.5],
            downbeats=[0, 2],
            energy_curve=[
                EnergySample(time=1, value=0.2, rms=0.2, spectral_flux=0.2, onset_density=0.2),
                EnergySample(time=4, value=0.4, rms=0.4, spectral_flux=0.4, onset_density=0.4),
                EnergySample(time=8, value=0.8, rms=0.8, spectral_flux=0.8, onset_density=0.8),
            ],
            parameters=AnalysisParameters(
                beat_analyzer="test",
                beat_model="test",
                beat_device="cpu",
                energy_sample_rate=100,
                frame_length=10,
                hop_length=5,
                energy_weights={"rms": 1},
                normalization_percentiles=(0, 100),
            ),
            created_at=datetime.now(UTC),
        )
    )
    client.post("/timeline/scenes", json={})
    client.post("/timeline/scenes", json={"at_time": 5})
    return directory, FakePlanningProvider()


def test_full_plan_preserves_timing_and_releases_after_final_call(
    tmp_path: Path, monkeypatch
) -> None:
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, provider = prepare_project(client, tmp_path / "projects")
        monkeypatch.setattr("beatweave.llm.service.LLMService.provider", lambda _self: provider)
        before = client.get("/timeline").json()

        response = client.post("/planning/visual-plan", json={})

        assert response.status_code == 200
        result = response.json()
        assert [(s["start_time"], s["end_time"]) for s in result["timeline"]["scenes"]] == [
            (s["start_time"], s["end_time"]) for s in before["scenes"]
        ]
        assert provider.release_after == [False, False]
        assert provider.release_count == 1
        assert provider.contexts[0]["track"]["average_energy"] == 0.46666666666666673
        assert len(result["project"]["creative_brief"]["visual_trajectory"]) == 2
        assert result["timeline"]["scenes"][0]["image_prompt"] == "Image 0"


def test_overwrite_confirmation_and_single_scene_regeneration_are_isolated(
    tmp_path: Path, monkeypatch
) -> None:
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, provider = prepare_project(client, tmp_path / "projects")
        monkeypatch.setattr("beatweave.llm.service.LLMService.provider", lambda _self: provider)
        planned = client.post("/planning/visual-plan", json={}).json()["timeline"]
        first, second = planned["scenes"]
        blocked = client.post(f"/planning/scenes/{first['id']}/regenerate", json={})
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "overwrite_confirmation_required"

        regenerated = client.post(
            f"/planning/scenes/{first['id']}/regenerate",
            json={"confirm_overwrite": True},
        ).json()["timeline"]

        assert regenerated["scenes"][1] == second
        assert provider.release_count == 2


def test_invalid_scene_ids_do_not_change_project(tmp_path: Path, monkeypatch) -> None:
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        directory, provider = prepare_project(client, tmp_path / "projects")
        provider.invalid_ids = True
        monkeypatch.setattr("beatweave.llm.service.LLMService.provider", lambda _self: provider)
        before = (directory / "project.db").read_bytes()

        response = client.post("/planning/visual-plan", json={})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_scene_plan"
        assert (directory / "project.db").read_bytes() == before


def test_large_scene_plan_is_generated_in_bounded_batches(tmp_path: Path, monkeypatch) -> None:
    with TestClient(create_app(Settings(database_path=tmp_path / "app.db"))) as client:
        _, provider = prepare_project(client, tmp_path / "projects")
        for boundary in (1, 2, 3, 4, 6, 7):
            assert client.post("/timeline/scenes", json={"at_time": boundary}).is_success
        monkeypatch.setattr("beatweave.llm.service.LLMService.provider", lambda _self: provider)

        response = client.post("/planning/visual-plan", json={})

        assert response.status_code == 200
        assert len(response.json()["timeline"]["scenes"]) == 8
        assert [len(context["scenes"]) for context in provider.contexts] == [8, 3, 3, 2]
        assert provider.release_count == 1
