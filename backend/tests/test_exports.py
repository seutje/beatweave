import json
import math
import struct
import time
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from beatweave.config import Settings
from beatweave.main import create_app
from beatweave.media.process import MediaProcessRunner
from beatweave.project.schemas import AssetMetadata, Project
from beatweave.project.store import ProjectStore
from beatweave.video_takes.schemas import VideoTake


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in {"complete", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("export job did not finish")


def create_export_project(client: TestClient, tmp_path: Path) -> tuple[dict, list[Path]]:
    parent = tmp_path / "projects"
    parent.mkdir()
    project_data = client.post(
        "/projects", json={"name": "Export Test", "parent_directory": str(parent)}
    ).json()
    store = ProjectStore(project_data["path"])
    now = datetime.now(UTC)

    audio_path = store.directory / "source" / "track.wav"
    sample_rate = 48_000
    with wave.open(str(audio_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate * 2):
            sample = int(8_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.extend(struct.pack("<h", sample))
        output.writeframes(frames)
    audio = AssetMetadata(
        id=str(uuid4()),
        kind="audio",
        relative_path=audio_path.relative_to(store.directory).as_posix(),
        filename=audio_path.name,
        mime_type="audio/wav",
        sha256="export-audio",
        size_bytes=audio_path.stat().st_size,
        media_metadata={"duration_seconds": 2.0},
        created_at=now,
    )
    store.insert_asset(audio)
    project = Project.model_validate(project_data).model_copy(update={"audio_asset_id": audio.id})
    store.update_project(project)

    keyframe_ids = [str(uuid4()) for _ in range(3)]
    scene_ids = [str(uuid4()) for _ in range(2)]
    now_iso = now.isoformat()
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [(keyframe_ids[index], float(index), now_iso, now_iso) for index in range(3)],
        )
        connection.executemany(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_keyframe_id,
                end_keyframe_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    scene_ids[index],
                    index,
                    float(index),
                    float(index + 1),
                    keyframe_ids[index],
                    keyframe_ids[index + 1],
                    now_iso,
                    now_iso,
                )
                for index in range(2)
            ],
        )

    runner = MediaProcessRunner()
    clip_paths = []
    for index, color in enumerate(("red", "blue")):
        clip = store.directory / "renders" / f"clip-{index}.mp4"
        runner.run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:r=24:d=1",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        )
        clip_paths.append(clip)
        asset = AssetMetadata(
            id=str(uuid4()),
            kind="generated_video",
            relative_path=clip.relative_to(store.directory).as_posix(),
            filename=clip.name,
            mime_type="video/mp4",
            sha256=f"clip-{index}-hash",
            size_bytes=clip.stat().st_size,
            media_metadata={"duration_seconds": 1.0},
            created_at=datetime.now(UTC),
        )
        take = VideoTake(
            id=str(uuid4()),
            scene_id=scene_ids[index],
            asset_id=asset.id,
            source_job_id=f"video-job-{index}",
            prompt=f"Scene {index}",
            backend="test",
            backend_settings={"duration_seconds": 1.0, "quality_mode": "final"},
            created_at=asset.created_at,
        )
        store.register_video_take(asset, take)
    return project_data, clip_paths


def test_export_readiness_and_final_assembly_preserve_order_audio_and_duration(
    tmp_path: Path,
) -> None:
    runner = MediaProcessRunner()
    app = create_app(Settings(database_path=tmp_path / "application.db"))
    with TestClient(app) as client:
        project, clips = create_export_project(client, tmp_path)
        ready = client.get("/exports/readiness").json()
        assert ready == {
            "ready": True,
            "scene_count": 2,
            "duration_seconds": 2.0,
            "issues": [],
        }

        store = ProjectStore(project["path"])
        with store.connection() as connection:
            first_take = connection.execute(
                """
                SELECT video_takes.id FROM video_takes
                JOIN scenes ON scenes.id = video_takes.scene_id
                WHERE scenes.position = 0
                """
            ).fetchone()
            connection.execute(
                "UPDATE video_takes SET backend_settings_json = ? WHERE id = ?",
                (json.dumps({"duration_seconds": 0.5, "quality_mode": "final"}), first_take["id"]),
            )
        assert "selected_take_duration_mismatch" in {
            issue["code"] for issue in client.get("/exports/readiness").json()["issues"]
        }
        with store.connection() as connection:
            connection.execute(
                "UPDATE video_takes SET backend_settings_json = ? WHERE id = ?",
                (json.dumps({"duration_seconds": 1.0, "quality_mode": "final"}), first_take["id"]),
            )

        with store.connection() as connection:
            connection.execute("UPDATE scenes SET selected_video_take_stale = 1 WHERE position = 0")
            connection.execute("UPDATE scenes SET selected_video_take_id = NULL WHERE position = 1")
        issue_codes = {issue["code"] for issue in client.get("/exports/readiness").json()["issues"]}
        assert {"selected_take_stale", "selected_take_missing"} <= issue_codes
        with store.connection() as connection:
            connection.execute("UPDATE scenes SET selected_video_take_stale = 0 WHERE position = 0")
            second = connection.execute(
                """
                SELECT video_takes.id FROM video_takes
                JOIN scenes ON scenes.id = video_takes.scene_id
                WHERE scenes.position = 1
                """
            ).fetchone()
            connection.execute(
                "UPDATE scenes SET selected_video_take_id = ? WHERE position = 1",
                (second["id"],),
            )
        clips[0].rename(clips[0].with_suffix(".missing"))
        assert "selected_take_file_missing" in {
            issue["code"] for issue in client.get("/exports/readiness").json()["issues"]
        }
        clips[0].with_suffix(".missing").rename(clips[0])

        response = client.post(
            "/exports",
            json={
                "filename": "assembled.mp4",
                "codec": "h264",
                "crf": 20,
                "frame_rate": 24,
                "width": 640,
                "height": 360,
            },
        )
        assert response.status_code == 202
        completed = wait_for_job(client, response.json()["job"]["id"])
        assert completed["state"] == "complete", completed.get("error")

    export = Path(project["path"]) / completed["output"]["relative_path"]
    probe = json.loads(
        runner.run_ffprobe(
            ["-v", "error", "-show_streams", "-show_format", "-of", "json", str(export)]
        )
    )
    assert {stream["codec_type"] for stream in probe["streams"]} == {"video", "audio"}
    assert abs(float(probe["format"]["duration"]) - 2.0) < 0.1

    colors = []
    for timestamp in (0.25, 1.25):
        pixel = runner.run_ffmpeg(
            [
                "-v",
                "error",
                "-ss",
                str(timestamp),
                "-i",
                str(export),
                "-frames:v",
                "1",
                "-vf",
                "scale=1:1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ]
        )
        colors.append(tuple(pixel[:3]))
    assert colors[0][0] > colors[0][2]
    assert colors[1][2] > colors[1][0]
