from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.analysis.schemas import AnalysisParameters, AudioAnalysis, EnergySample
from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.planning.layout import suggest_boundaries
from beatweave.project.schemas import AssetMetadata
from beatweave.project.store import ProjectStore


def parameters() -> AnalysisParameters:
    return AnalysisParameters(
        beat_analyzer="test",
        beat_model="test",
        beat_device="cpu",
        energy_sample_rate=100,
        frame_length=10,
        hop_length=5,
        energy_weights={"rms": 1},
        normalization_percentiles=(5, 95),
    )


def test_suggestions_are_deterministic_and_use_musical_structure() -> None:
    beats = [float(value) for value in range(1, 24)]
    downbeats = [4.0, 8.0, 12.0, 16.0, 20.0]
    energy = [
        EnergySample(time=0, value=0.1, rms=0.1, spectral_flux=0, onset_density=0),
        EnergySample(time=6, value=0.95, rms=0.9, spectral_flux=0.8, onset_density=0.8),
        EnergySample(time=24, value=0.8, rms=0.8, spectral_flux=0.5, onset_density=0.5),
    ]

    first = suggest_boundaries(24, beats, downbeats, energy)
    second = suggest_boundaries(24, beats, downbeats, energy)

    assert first == second
    assert first[0].time == 0
    assert first[-1].time == 24
    assert any(boundary.reason == "energy" for boundary in first)
    assert any(boundary.reason == "downbeat" for boundary in first)
    assert all(
        0 < end.time - start.time <= 10 for start, end in zip(first, first[1:], strict=False)
    )


def prepare_analyzed_project(client: TestClient, tmp_path: Path) -> Path:
    parent = tmp_path / "projects"
    parent.mkdir()
    project = client.post(
        "/projects", json={"name": "Layout Project", "parent_directory": str(parent)}
    ).json()
    store = ProjectStore(Path(project["path"]))
    asset = AssetMetadata(
        id="audio-layout",
        kind="audio",
        relative_path="source/track.wav",
        filename="track.wav",
        sha256="layout-source",
        size_bytes=100,
        media_metadata={"duration_seconds": 20},
        created_at=datetime.now(UTC),
    )
    store.insert_asset(asset)
    store.update_project(store.read_project().model_copy(update={"audio_asset_id": asset.id}))
    beats = [float(value) for value in range(1, 20)]
    store.insert_analysis(
        AudioAnalysis(
            id="analysis-layout",
            asset_id=asset.id,
            source_sha256=asset.sha256,
            bpm_estimate=60,
            beats=beats,
            downbeats=[4, 8, 12, 16],
            energy_curve=[
                EnergySample(
                    time=float(value),
                    value=(value % 5) / 5,
                    rms=(value % 5) / 5,
                    spectral_flux=0,
                    onset_density=0,
                )
                for value in range(21)
            ],
            parameters=parameters(),
            created_at=datetime.now(UTC),
        )
    )
    return Path(project["path"])


def test_preview_apply_and_undo_restore_exact_layout(tmp_path: Path) -> None:
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project_path = prepare_analyzed_project(client, tmp_path)
        client.post("/timeline/scenes", json={})
        original = client.post("/timeline/scenes", json={"at_time": 7.125}).json()

        proposed = client.post(
            "/timeline/layout/suggest",
            json={"preferred_length_seconds": 6, "minimum_length_seconds": 2},
        )
        assert proposed.status_code == 200
        assert client.get("/timeline").json()["scenes"] == original["scenes"]

        applied = client.post(
            "/timeline/layout/apply",
            json={"boundaries": proposed.json()["boundaries"]},
        )
        assert applied.status_code == 200
        timeline = applied.json()
        assert timeline["can_undo"] is True
        assert timeline["scenes"][0]["start_time"] == 0
        assert timeline["scenes"][-1]["end_time"] == 20
        for left, right in zip(timeline["scenes"], timeline["scenes"][1:], strict=False):
            assert left["end_keyframe_id"] == right["start_keyframe_id"]
            assert left["end_time"] == right["start_time"]

        with TestClient(
            create_app(Settings(database_path=tmp_path / "application.db"))
        ) as reopened:
            reopened.post("/projects/open", json={"path": str(project_path)})
            assert reopened.get("/timeline").json()["can_undo"] is True
            restored = reopened.post("/timeline/layout/undo")
            assert restored.status_code == 200
            assert restored.json()["scenes"] == original["scenes"]
            assert restored.json()["keyframes"] == original["keyframes"]
            assert restored.json()["can_redo"] is True
