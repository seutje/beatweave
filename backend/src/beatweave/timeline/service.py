import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.errors import BeatweaveError
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.schemas import Keyframe, Scene, Timeline

MIN_SCENE_DURATION = 0.05


class TimelineService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def current(self) -> Timeline:
        store, duration = self._store_and_duration()
        return self._read(store, duration)

    def create_scene(self, at_time: float | None, beat_index: int | None) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            rows = connection.execute("SELECT * FROM scenes ORDER BY position").fetchall()
            if not rows:
                if duration < MIN_SCENE_DURATION:
                    raise BeatweaveError(
                        "audio_too_short",
                        "The source track is too short to create a scene.",
                        status_code=422,
                    )
                self._insert_initial_scene(connection, duration, now)
            else:
                if at_time is None:
                    raise BeatweaveError(
                        "split_time_required",
                        "Choose a position inside a scene to create a new scene.",
                        status_code=422,
                    )
                self._split_scene(connection, rows, at_time, beat_index, now)
        return self._read(store, duration)

    def move_boundary(self, keyframe_id: str, time: float, beat_index: int | None) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            keyframe = connection.execute(
                "SELECT * FROM keyframes WHERE id = ?", (keyframe_id,)
            ).fetchone()
            if keyframe is None:
                raise BeatweaveError("keyframe_not_found", "Keyframe not found.", status_code=404)
            left = connection.execute(
                "SELECT * FROM scenes WHERE end_keyframe_id = ?", (keyframe_id,)
            ).fetchone()
            right = connection.execute(
                "SELECT * FROM scenes WHERE start_keyframe_id = ?", (keyframe_id,)
            ).fetchone()
            if left is None or right is None:
                raise BeatweaveError(
                    "outer_boundary_fixed",
                    "The track start and end boundaries are fixed.",
                    status_code=422,
                )
            minimum = float(left["start_time"]) + MIN_SCENE_DURATION
            maximum = float(right["end_time"]) - MIN_SCENE_DURATION
            if not minimum <= time <= maximum:
                raise BeatweaveError(
                    "invalid_scene_duration",
                    "Moving this boundary would create a zero or negative-duration scene.",
                    status_code=422,
                    details={"minimum": minimum, "maximum": maximum},
                )
            connection.execute(
                "UPDATE keyframes SET time = ?, updated_at = ? WHERE id = ?",
                (time, now, keyframe_id),
            )
            connection.execute(
                "UPDATE scenes SET end_time = ?, end_beat_index = ?, updated_at = ? WHERE id = ?",
                (time, beat_index, now, left["id"]),
            )
            connection.execute(
                """
                UPDATE scenes SET start_time = ?, start_beat_index = ?, updated_at = ?
                WHERE id = ?
                """,
                (time, beat_index, now, right["id"]),
            )
        return self._read(store, duration)

    def delete_scene(self, scene_id: str) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            scenes = connection.execute("SELECT * FROM scenes ORDER BY position").fetchall()
            index = next((i for i, scene in enumerate(scenes) if scene["id"] == scene_id), None)
            if index is None:
                raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
            scene = scenes[index]
            if len(scenes) == 1:
                connection.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
                connection.execute(
                    "DELETE FROM keyframes WHERE id IN (?, ?)",
                    (scene["start_keyframe_id"], scene["end_keyframe_id"]),
                )
            elif index > 0:
                previous = scenes[index - 1]
                connection.execute(
                    """
                    UPDATE scenes SET end_time = ?, end_beat_index = ?, end_keyframe_id = ?,
                        updated_at = ? WHERE id = ?
                    """,
                    (
                        scene["end_time"],
                        scene["end_beat_index"],
                        scene["end_keyframe_id"],
                        now,
                        previous["id"],
                    ),
                )
                connection.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
                connection.execute(
                    "DELETE FROM keyframes WHERE id = ?", (scene["start_keyframe_id"],)
                )
            else:
                following = scenes[1]
                connection.execute(
                    """
                    UPDATE scenes SET start_time = ?, start_beat_index = ?, start_keyframe_id = ?,
                        updated_at = ? WHERE id = ?
                    """,
                    (
                        scene["start_time"],
                        scene["start_beat_index"],
                        scene["start_keyframe_id"],
                        now,
                        following["id"],
                    ),
                )
                connection.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
                connection.execute(
                    "DELETE FROM keyframes WHERE id = ?", (scene["end_keyframe_id"],)
                )
            remaining = connection.execute("SELECT id FROM scenes ORDER BY position").fetchall()
            for position, row in enumerate(remaining):
                connection.execute(
                    "UPDATE scenes SET position = ? WHERE id = ?", (position, row["id"])
                )
        return self._read(store, duration)

    def _store_and_duration(self) -> tuple[ProjectStore, float]:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        if project.audio_asset_id is None:
            raise BeatweaveError("audio_not_imported", "Import audio first.", status_code=409)
        store = ProjectStore(Path(project.path))
        asset = store.get_asset(project.audio_asset_id)
        if asset is None:
            raise BeatweaveError(
                "audio_asset_missing", "The source audio is missing.", status_code=404
            )
        return store, float(asset.media_metadata["duration_seconds"])

    @staticmethod
    def _insert_initial_scene(connection: sqlite3.Connection, duration: float, now: str) -> None:
        start_id, end_id, scene_id = str(uuid4()), str(uuid4()), str(uuid4())
        connection.executemany(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ((start_id, 0.0, now, now), (end_id, duration, now, now)),
        )
        connection.execute(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_keyframe_id, end_keyframe_id,
                created_at, updated_at
            ) VALUES (?, 0, 0, ?, ?, ?, ?, ?)
            """,
            (scene_id, duration, start_id, end_id, now, now),
        )

    @staticmethod
    def _split_scene(
        connection: sqlite3.Connection,
        scenes: list[sqlite3.Row],
        at_time: float,
        beat_index: int | None,
        now: str,
    ) -> None:
        scene = next(
            (
                row
                for row in scenes
                if float(row["start_time"]) + MIN_SCENE_DURATION
                <= at_time
                <= float(row["end_time"]) - MIN_SCENE_DURATION
            ),
            None,
        )
        if scene is None:
            raise BeatweaveError(
                "invalid_scene_split",
                "The boundary must be inside a scene and leave duration on both sides.",
                status_code=422,
            )
        for row in reversed(scenes[int(scene["position"]) + 1 :]):
            connection.execute(
                "UPDATE scenes SET position = ? WHERE id = ?",
                (int(row["position"]) + 1, row["id"]),
            )
        boundary_id, new_scene_id = str(uuid4()), str(uuid4())
        connection.execute(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (boundary_id, at_time, now, now),
        )
        connection.execute(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_beat_index, end_beat_index,
                start_keyframe_id, end_keyframe_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_scene_id,
                int(scene["position"]) + 1,
                at_time,
                scene["end_time"],
                beat_index,
                scene["end_beat_index"],
                boundary_id,
                scene["end_keyframe_id"],
                now,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE scenes SET end_time = ?, end_beat_index = ?, end_keyframe_id = ?,
                updated_at = ? WHERE id = ?
            """,
            (at_time, beat_index, boundary_id, now, scene["id"]),
        )

    @staticmethod
    def _read(store: ProjectStore, duration: float) -> Timeline:
        with store.connection() as connection:
            scene_rows = connection.execute("SELECT * FROM scenes ORDER BY position").fetchall()
            keyframe_rows = connection.execute("SELECT * FROM keyframes ORDER BY time").fetchall()
        timeline = Timeline(
            duration_seconds=duration,
            scenes=[Scene.model_validate(dict(row)) for row in scene_rows],
            keyframes=[Keyframe.model_validate(dict(row)) for row in keyframe_rows],
        )
        TimelineService._validate(timeline)
        return timeline

    @staticmethod
    def _validate(timeline: Timeline) -> None:
        keyframes = {keyframe.id: keyframe for keyframe in timeline.keyframes}
        for position, scene in enumerate(timeline.scenes):
            start = keyframes.get(scene.start_keyframe_id)
            end = keyframes.get(scene.end_keyframe_id)
            valid = (
                scene.position == position
                and start is not None
                and end is not None
                and start.time == scene.start_time
                and end.time == scene.end_time
                and scene.start_time < scene.end_time
            )
            if position > 0:
                previous = timeline.scenes[position - 1]
                valid = valid and (
                    previous.end_keyframe_id == scene.start_keyframe_id
                    and previous.end_time == scene.start_time
                )
            if not valid:
                raise BeatweaveError(
                    "timeline_invariant_violation",
                    "The stored timeline has inconsistent scene or keyframe boundaries.",
                    status_code=422,
                )
