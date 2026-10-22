from beatweave.errors import BeatweaveError


def timeline_frame_count(start_seconds: float, end_seconds: float, frame_rate: int) -> int:
    """Quantize absolute cuts so fractional frames cannot accumulate across scenes."""
    count = round(end_seconds * frame_rate) - round(start_seconds * frame_rate)
    if count < 1:
        raise BeatweaveError(
            "scene_shorter_than_frame",
            "A scene is shorter than one output frame. Extend it or increase the frame rate.",
            status_code=422,
        )
    return count
