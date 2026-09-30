import math
import os
import struct
import time
import wave
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from beatweave.analysis import api as analysis_api
from beatweave.analysis.beat import BeatThisDetector
from beatweave.analysis.service import AnalysisService
from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.media.process import MediaProcessRunner
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore


class TimestampDetector:
    name = "test_detector"
    model_name = "deterministic"
    resolved_device = "cpu"

    def __init__(self, tempo: float, duration: float = 6.0) -> None:
        interval = 60 / tempo
        self.beats = []
        value = 0.15
        index = 0
        while value < duration:
            self.beats.append(round(value + (0.004 if index % 2 else 0), 6))
            value += interval
            index += 1
        self.downbeats = self.beats[::4]

    def detect(self, _: Path) -> tuple[list[float], list[float]]:
        return self.beats.copy(), self.downbeats.copy()


class FailingDetector(TimestampDetector):
    def detect(self, _: Path) -> tuple[list[float], list[float]]:
        raise RuntimeError("synthetic detector failure")


def write_click_track(path: Path, tempo: float, duration: float = 6.0) -> None:
    sample_rate = 22050
    samples = [0.0] * int(sample_rate * duration)
    beat_interval = 60 / tempo
    beat_time = 0.15
    while beat_time < duration:
        start = int(beat_time * sample_rate)
        for offset in range(min(300, len(samples) - start)):
            samples[start + offset] += 0.8 * math.exp(-offset / 70) * math.sin(offset * 0.4)
        beat_time += beat_interval
    frames = b"".join(struct.pack("<h", int(max(-1, min(1, value)) * 32767)) for value in samples)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def prepare_project(client: TestClient, tmp_path: Path, track: Path) -> dict:
    parent = tmp_path / "projects"
    parent.mkdir()
    project = client.post(
        "/projects", json={"name": "Analysis Project", "parent_directory": str(parent)}
    ).json()
    response = client.post("/media/audio/import", json={"path": str(track)})
    assert response.status_code == 200
    return project


@pytest.mark.parametrize("tempo", [80.0, 120.0, 160.0])
def test_analysis_persists_real_timestamps_and_normalized_energy(
    tmp_path: Path, tempo: float
) -> None:
    track = tmp_path / f"click-{int(tempo)}.wav"
    write_click_track(track, tempo)
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    detector = TimestampDetector(tempo)

    with TestClient(app) as client:
        project = prepare_project(client, tmp_path, track)
        service = AnalysisService(
            ProjectService(app.state.database), MediaProcessRunner(), detector
        )
        job, project_path = service.start()
        assert job.state == "queued"
        service.run(job.id, project_path)

        completed = service.get_job(job.id)
        analysis = service.current_analysis()
        assert completed.state == "complete"
        assert completed.progress == 1
        assert analysis is not None
        assert analysis.beats == detector.beats
        assert analysis.downbeats == detector.downbeats
        assert analysis.bpm_estimate == pytest.approx(tempo, abs=2)
        assert analysis.energy_curve
        assert all(0 <= sample.value <= 1 for sample in analysis.energy_curve)
        assert analysis.parameters.energy_weights == {
            "rms": 0.5,
            "spectral_flux": 0.3,
            "onset_density": 0.2,
        }

        store = ProjectStore(Path(project["path"]))
        persisted = store.find_analysis_by_hash(analysis.source_sha256)
        assert persisted is not None
        assert persisted.beats == detector.beats

        cached_job, _ = service.start()
        assert cached_job.state == "complete"
        assert cached_job.output["cached"] is True
        forced_job, _ = service.start(force=True)
        assert forced_job.state == "queued"


def test_analysis_api_persists_failure_details(tmp_path: Path) -> None:
    track = tmp_path / "click.wav"
    write_click_track(track, 100)
    app = create_app(Settings(database_path=tmp_path / "application.db"))

    def failing_service(request: Request) -> AnalysisService:
        return AnalysisService(
            ProjectService(request.app.state.database),
            MediaProcessRunner(),
            FailingDetector(100),
        )

    app.dependency_overrides[analysis_api.service] = failing_service
    with TestClient(app) as client:
        prepare_project(client, tmp_path, track)
        started = client.post("/analysis")
        assert started.status_code == 202
        deadline = time.monotonic() + 3
        while True:
            job = client.get(f"/analysis/jobs/{started.json()['id']}").json()
            if job["state"] in {"complete", "failed", "cancelled"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)

    assert job["state"] == "failed"
    assert job["error"]["code"] == "analysis_failed"
    assert "synthetic detector failure" in job["error"]["message"]


def test_official_beat_this_inference_class_is_available() -> None:
    from beat_this.inference import File2Beats

    assert File2Beats is not None


@pytest.mark.skipif(
    os.environ.get("BEATWEAVE_RUN_BEAT_THIS_INTEGRATION") != "1",
    reason="Set BEATWEAVE_RUN_BEAT_THIS_INTEGRATION=1 for model inference",
)
@pytest.mark.parametrize("tempo", [80.0, 120.0, 160.0])
def test_real_beat_this_on_three_tempos(tmp_path: Path, tempo: float) -> None:
    track = tmp_path / f"beat-this-{int(tempo)}.wav"
    write_click_track(track, tempo)
    beats, downbeats = BeatThisDetector("small0", "cpu").detect(track)

    assert len(beats) >= 2
    assert all(current > previous for previous, current in zip(beats, beats[1:], strict=False))
    assert all(
        current > previous for previous, current in zip(downbeats, downbeats[1:], strict=False)
    )
