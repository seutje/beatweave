import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beatweave.errors import BeatweaveError
from beatweave.planning.layout import DEFAULT_PREFERRED_LENGTHS, suggest_boundaries
from beatweave.project.service import ProjectService
from beatweave.project.store import ProjectStore
from beatweave.timeline.schemas import (
    Keyframe,
    LayoutProposal,
    ProposedBoundary,
    Scene,
    Timeline,
)

MIN_SCENE_DURATION = 0.05


class TimelineService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def current(self) -> Timeline:
        store, duration = self._store_and_duration()
        return self._read(store, duration)

    def suggest_layout(self, preferred_length: float, minimum_length: float) -> LayoutProposal:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        store, duration = self._store_and_duration()
        asset = store.get_asset(project.audio_asset_id or "")
        analysis = store.find_analysis_by_hash(asset.sha256) if asset else None
        if analysis is None:
            raise BeatweaveError(
                "analysis_required",
                "Analyze the track before suggesting a scene layout.",
                status_code=409,
            )
        maximum_length = project.settings.max_clip_length_seconds
        if not minimum_length <= preferred_length <= maximum_length:
            raise BeatweaveError(
                "invalid_layout_settings",
                "The preferred length must be between the minimum and project maximum.",
                status_code=422,
                details={"maximum_length_seconds": maximum_length},
            )
        suggested = suggest_boundaries(
            duration,
            analysis.beats,
            analysis.downbeats,
            analysis.energy_curve,
            preferred_length=preferred_length,
            minimum_length=minimum_length,
            maximum_length=maximum_length,
        )
        return LayoutProposal(
            duration_seconds=duration,
            preferred_length_seconds=preferred_length,
            minimum_length_seconds=minimum_length,
            maximum_length_seconds=maximum_length,
            default_preferred_lengths=list(DEFAULT_PREFERRED_LENGTHS),
            boundaries=[ProposedBoundary(**boundary.__dict__) for boundary in suggested],
        )

    def apply_layout(self, boundaries: list[ProposedBoundary]) -> Timeline:
        project = self.projects.current()
        if project is None:
            raise BeatweaveError("project_not_open", "Open a project first.", status_code=409)
        store, duration = self._store_and_duration()
        self._validate_proposed_boundaries(
            boundaries, duration, project.settings.max_clip_length_seconds
        )
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            before = self._snapshot(connection)
            self._replace_layout(connection, boundaries, now)
            self._record_history(
                connection, "apply_layout", before, self._snapshot(connection), now
            )
        return self._read(store, duration)

    def undo_layout(self) -> Timeline:
        return self.undo()

    def undo(self) -> Timeline:
        store, duration = self._store_and_duration()
        with store.connection() as connection:
            history = connection.execute(
                """
                SELECT * FROM timeline_edit_history
                WHERE applied = 1 ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            if history is None:
                raise BeatweaveError(
                    "undo_unavailable",
                    "There is no timeline edit to undo.",
                    status_code=409,
                )
            self._restore_snapshot(connection, json.loads(history["before_json"]))
            connection.execute(
                "UPDATE timeline_edit_history SET applied = 0 WHERE id = ?", (history["id"],)
            )
        return self._read(store, duration)

    def redo(self) -> Timeline:
        store, duration = self._store_and_duration()
        with store.connection() as connection:
            history = connection.execute(
                """
                SELECT * FROM timeline_edit_history
                WHERE applied = 0 ORDER BY sequence ASC LIMIT 1
                """
            ).fetchone()
            if history is None:
                raise BeatweaveError(
                    "redo_unavailable",
                    "There is no timeline edit to redo.",
                    status_code=409,
                )
            self._restore_snapshot(connection, json.loads(history["after_json"]))
            connection.execute(
                "UPDATE timeline_edit_history SET applied = 1 WHERE id = ?", (history["id"],)
            )
        return self._read(store, duration)

    def create_scene(self, at_time: float | None, beat_index: int | None) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            before = self._snapshot(connection)
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
            self._record_history(
                connection, "create_scene", before, self._snapshot(connection), now
            )
        return self._read(store, duration)

    def move_boundary(self, keyframe_id: str, time: float, beat_index: int | None) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            before = self._snapshot(connection)
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
                """
                UPDATE scenes
                SET end_time = ?, end_beat_index = ?,
                    selected_video_take_stale = CASE
                        WHEN selected_video_take_id IS NOT NULL THEN 1
                        ELSE selected_video_take_stale
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (time, beat_index, now, left["id"]),
            )
            connection.execute(
                """
                UPDATE scenes
                SET start_time = ?, start_beat_index = ?,
                    selected_video_take_stale = CASE
                        WHEN selected_video_take_id IS NOT NULL THEN 1
                        ELSE selected_video_take_stale
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (time, beat_index, now, right["id"]),
            )
            self._record_history(
                connection, "move_boundary", before, self._snapshot(connection), now
            )
        return self._read(store, duration)

    def delete_scene(self, scene_id: str) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            before = self._snapshot(connection)
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
            self._record_history(
                connection, "delete_scene", before, self._snapshot(connection), now
            )
        return self._read(store, duration)

    def update_scene(
        self,
        scene_id: str,
        *,
        concept: str | None,
        image_prompt: str | None,
        video_prompt: str | None,
        approved: bool | None,
        use_last_frame_conditioning: bool | None,
    ) -> Timeline:
        store, duration = self._store_and_duration()
        now = datetime.now(UTC).isoformat()
        with store.connection() as connection:
            scene = connection.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
            if scene is None:
                raise BeatweaveError("scene_not_found", "Scene not found.", status_code=404)
            before = self._snapshot(connection)
            next_video_prompt = scene["video_prompt"] if video_prompt is None else video_prompt
            stale = int(
                bool(scene["selected_video_take_id"])
                and (
                    next_video_prompt != scene["video_prompt"]
                    or (
                        use_last_frame_conditioning is not None
                        and use_last_frame_conditioning
                        != bool(scene["use_last_frame_conditioning"])
                    )
                )
            )
            connection.execute(
                """
                UPDATE scenes SET concept = ?, image_prompt = ?, video_prompt = ?, approved = ?,
                    use_last_frame_conditioning = ?,
                    selected_video_take_stale = CASE
                        WHEN ? = 1 THEN 1 ELSE selected_video_take_stale END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    scene["concept"] if concept is None else concept,
                    scene["image_prompt"] if image_prompt is None else image_prompt,
                    next_video_prompt,
                    int(scene["approved"] if approved is None else approved),
                    int(
                        scene["use_last_frame_conditioning"]
                        if use_last_frame_conditioning is None
                        else use_last_frame_conditioning
                    ),
                    stale,
                    now,
                    scene_id,
                ),
            )
            self._record_history(
                connection, "update_scene", before, self._snapshot(connection), now
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
            keyframe_rows = connection.execute(
                """
                SELECT keyframes.*, keyframe_variants.asset_id AS selected_variant_asset_id
                FROM keyframes
                LEFT JOIN keyframe_variants
                    ON keyframe_variants.id = keyframes.selected_variant_id
                ORDER BY keyframes.time
                """
            ).fetchall()
            can_undo = (
                connection.execute(
                    "SELECT 1 FROM timeline_edit_history WHERE applied = 1 LIMIT 1"
                ).fetchone()
                is not None
            )
            can_redo = (
                connection.execute(
                    "SELECT 1 FROM timeline_edit_history WHERE applied = 0 LIMIT 1"
                ).fetchone()
                is not None
            )
        timeline = Timeline(
            duration_seconds=duration,
            scenes=[Scene.model_validate(dict(row)) for row in scene_rows],
            keyframes=[Keyframe.model_validate(dict(row)) for row in keyframe_rows],
            can_undo=can_undo,
            can_redo=can_redo,
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

    @staticmethod
    def _validate_proposed_boundaries(
        boundaries: list[ProposedBoundary], duration: float, maximum_length: float
    ) -> None:
        times = [boundary.time for boundary in boundaries]
        valid_edges = abs(times[0]) < 0.000_001 and abs(times[-1] - duration) < 0.000_001
        durations = [end - start for start, end in zip(times, times[1:], strict=False)]
        if (
            not valid_edges
            or any(length < MIN_SCENE_DURATION for length in durations)
            or any(length > maximum_length + 0.000_001 for length in durations)
            or any(end <= start for start, end in zip(times, times[1:], strict=False))
        ):
            raise BeatweaveError(
                "invalid_layout_proposal",
                "The proposed layout must cover the track with valid contiguous scenes.",
                status_code=422,
            )

    @staticmethod
    def _snapshot(connection: sqlite3.Connection) -> dict[str, list[dict]]:
        return {
            "scenes": [
                dict(row) for row in connection.execute("SELECT * FROM scenes ORDER BY position")
            ],
            "keyframes": [
                dict(row) for row in connection.execute("SELECT * FROM keyframes ORDER BY time")
            ],
        }

    @staticmethod
    def _record_history(
        connection: sqlite3.Connection,
        operation: str,
        before: dict[str, list[dict]],
        after: dict[str, list[dict]],
        created_at: str,
    ) -> None:
        connection.execute("DELETE FROM timeline_edit_history WHERE applied = 0")
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM timeline_edit_history"
        ).fetchone()
        connection.execute(
            """
            INSERT INTO timeline_edit_history (
                id, sequence, operation, before_json, after_json, applied, created_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid4()),
                row["value"],
                operation,
                json.dumps(before),
                json.dumps(after),
                created_at,
            ),
        )

    @staticmethod
    def _replace_layout(
        connection: sqlite3.Connection, boundaries: list[ProposedBoundary], now: str
    ) -> None:
        connection.execute("DELETE FROM scenes")
        connection.execute("DELETE FROM keyframes")
        keyframe_ids = [str(uuid4()) for _ in boundaries]
        connection.executemany(
            "INSERT INTO keyframes (id, time, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [
                (keyframe_id, boundary.time, now, now)
                for keyframe_id, boundary in zip(keyframe_ids, boundaries, strict=True)
            ],
        )
        connection.executemany(
            """
            INSERT INTO scenes (
                id, position, start_time, end_time, start_beat_index, end_beat_index,
                start_keyframe_id, end_keyframe_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid4()),
                    position,
                    start.time,
                    end.time,
                    start.beat_index,
                    end.beat_index,
                    keyframe_ids[position],
                    keyframe_ids[position + 1],
                    now,
                    now,
                )
                for position, (start, end) in enumerate(
                    zip(boundaries, boundaries[1:], strict=False)
                )
            ],
        )

    @staticmethod
    def _restore_snapshot(connection: sqlite3.Connection, snapshot: dict) -> None:
        connection.execute("DELETE FROM scenes")
        connection.execute("DELETE FROM keyframes")
        keyframe_columns = (
            "id",
            "time",
            "prompt",
            "selected_variant_id",
            "created_at",
            "updated_at",
        )
        scene_columns = (
            "id",
            "position",
            "start_time",
            "end_time",
            "start_beat_index",
            "end_beat_index",
            "start_keyframe_id",
            "end_keyframe_id",
            "concept",
            "image_prompt",
            "video_prompt",
            "visual_energy",
            "motion_energy",
            "selected_video_take_id",
            "selected_video_take_stale",
            "approved",
            "use_last_frame_conditioning",
            "created_at",
            "updated_at",
        )
        keyframe_query = (
            f"INSERT INTO keyframes ({', '.join(keyframe_columns)}) "
            f"VALUES ({', '.join('?' for _ in keyframe_columns)})"
        )
        scene_query = (
            f"INSERT INTO scenes ({', '.join(scene_columns)}) "
            f"VALUES ({', '.join('?' for _ in scene_columns)})"
        )
        connection.executemany(
            keyframe_query,
            [tuple(row[column] for column in keyframe_columns) for row in snapshot["keyframes"]],
        )
        connection.executemany(
            scene_query,
            [
                tuple(
                    row.get(column, 0)
                    if column in {"selected_video_take_stale", "approved"}
                    else row.get(column, 1)
                    if column == "use_last_frame_conditioning"
                    else row[column]
                    for column in scene_columns
                )
                for row in snapshot["scenes"]
            ],
        )
