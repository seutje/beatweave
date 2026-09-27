import math
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.media.process import MediaProcessRunner


def write_sine_wave(path: Path, *, frequency: float = 120.0, duration: float = 1.0) -> None:
    sample_rate = 8000
    frames = bytearray()
    for index in range(int(sample_rate * duration)):
        sample = int(12_000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(frames)


def create_project(client: TestClient, parent: Path, name: str = "Media Project") -> dict:
    parent.mkdir()
    response = client.post("/projects", json={"name": name, "parent_directory": str(parent)})
    assert response.status_code == 201
    return response.json()


def test_imports_wav_and_mp3_and_reuses_waveform_cache(tmp_path: Path) -> None:
    source_wav = tmp_path / "source.wav"
    source_mp3 = tmp_path / "source.mp3"
    write_sine_wave(source_wav)
    MediaProcessRunner().run_ffmpeg(["-y", "-v", "error", "-i", str(source_wav), str(source_mp3)])

    application_database = tmp_path / "application.db"
    with TestClient(create_app(Settings(database_path=application_database))) as client:
        project = create_project(client, tmp_path / "projects")

        wav_response = client.post("/media/audio/import", json={"path": str(source_wav)})
        assert wav_response.status_code == 200
        wav_import = wav_response.json()
        assert wav_import["asset"]["media_metadata"]["sample_rate"] == 8000
        assert wav_import["asset"]["media_metadata"]["channels"] == 1
        assert 0.9 < wav_import["asset"]["media_metadata"]["duration_seconds"] < 1.1
        assert wav_import["waveform"]["peaks"]
        assert all(0 <= peak <= 1 for peak in wav_import["waveform"]["peaks"])

        copied_wav = Path(project["path"]) / wav_import["asset"]["relative_path"]
        assert copied_wav.is_file()
        assert copied_wav != source_wav
        assert source_wav.is_file()

        cache_path = (
            Path(project["path"]) / "cache" / "waveforms" / f"{wav_import['asset']['sha256']}.json"
        )
        first_cache_timestamp = cache_path.stat().st_mtime_ns
        cached_response = client.get("/media/audio/waveform")
        assert cached_response.status_code == 200
        assert cache_path.stat().st_mtime_ns == first_cache_timestamp

        content = client.get("/media/audio/content", headers={"Range": "bytes=0-99"})
        assert content.status_code == 206
        assert len(content.content) == 100

        mp3_response = client.post("/media/audio/import", json={"path": str(source_mp3)})
        assert mp3_response.status_code == 200
        assert mp3_response.json()["asset"]["media_metadata"]["codec"] == "mp3"

    with TestClient(create_app(Settings(database_path=application_database))) as restarted:
        current = restarted.get("/projects/current").json()
        assert current["audio_asset_id"] == mp3_response.json()["asset"]["id"]
        waveform = restarted.get("/media/audio/waveform")
        assert waveform.status_code == 200
        assert waveform.json()["source_sha256"] == mp3_response.json()["asset"]["sha256"]


def test_audio_import_reports_probe_failure(tmp_path: Path) -> None:
    invalid_audio = tmp_path / "broken.wav"
    invalid_audio.write_bytes(b"not audio")
    with TestClient(create_app(Settings(database_path=tmp_path / "application.db"))) as client:
        create_project(client, tmp_path / "projects")
        response = client.post("/media/audio/import", json={"path": str(invalid_audio)})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "media_process_failed"
