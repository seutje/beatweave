from dataclasses import dataclass

from beatweave.analysis.schemas import EnergySample

DEFAULT_PREFERRED_LENGTHS = (4.0, 6.0, 8.0)


@dataclass(frozen=True)
class LayoutCandidate:
    time: float
    beat_index: int | None
    reason: str
    energy_change: float


@dataclass(frozen=True)
class SuggestedBoundary:
    time: float
    beat_index: int | None
    reason: str
    energy_change: float


def suggest_boundaries(
    duration: float,
    beats: list[float],
    downbeats: list[float],
    energy_curve: list[EnergySample],
    *,
    preferred_length: float = 6.0,
    minimum_length: float = 2.0,
    maximum_length: float = 10.0,
    section_boundaries: list[float] | None = None,
) -> list[SuggestedBoundary]:
    if duration <= 0 or minimum_length <= 0 or not minimum_length <= preferred_length:
        raise ValueError("Invalid layout duration settings")
    if maximum_length < preferred_length:
        raise ValueError("Maximum length must be at least the preferred length")

    beat_indexes = {round(time, 6): index for index, time in enumerate(beats)}
    candidates: dict[float, LayoutCandidate] = {}

    def add(time: float, reason: str, energy_change: float = 0) -> None:
        if not minimum_length <= time <= duration - minimum_length:
            return
        rounded = round(time, 6)
        priorities = {"section": 4, "downbeat": 3, "energy": 2, "beat": 1}
        candidate = LayoutCandidate(
            time=rounded,
            beat_index=beat_indexes.get(rounded),
            reason=reason,
            energy_change=round(energy_change, 6),
        )
        existing = candidates.get(rounded)
        if existing is None or priorities[reason] > priorities[existing.reason]:
            candidates[rounded] = candidate

    for time in beats:
        add(time, "beat")
    for time in downbeats:
        add(time, "downbeat")
    for time in section_boundaries or []:
        add(time, "section")
    for previous, current in zip(energy_curve, energy_curve[1:], strict=False):
        change = abs(current.value - previous.value)
        if change >= 0.12:
            add(current.time, "energy", change)

    ordered = sorted(candidates.values(), key=lambda candidate: candidate.time)
    boundaries = [SuggestedBoundary(0.0, None, "track_start", 0.0)]
    current = 0.0
    while duration - current > maximum_length:
        target = current + preferred_length
        latest = min(current + maximum_length, duration - minimum_length)
        viable = [
            candidate
            for candidate in ordered
            if current + minimum_length <= candidate.time <= latest
        ]
        if viable:
            bonuses = {"section": 2.0, "downbeat": 1.5, "energy": 0.8, "beat": 0.3}
            chosen = max(
                viable,
                key=lambda candidate: (
                    bonuses[candidate.reason]
                    + candidate.energy_change
                    - abs(candidate.time - target) / preferred_length,
                    -abs(candidate.time - target),
                    -candidate.time,
                ),
            )
        else:
            fallback = min(target, latest)
            chosen = LayoutCandidate(round(fallback, 6), None, "interval", 0.0)
        boundaries.append(
            SuggestedBoundary(chosen.time, chosen.beat_index, chosen.reason, chosen.energy_change)
        )
        current = chosen.time
    boundaries.append(SuggestedBoundary(round(duration, 6), None, "track_end", 0.0))
    return boundaries
