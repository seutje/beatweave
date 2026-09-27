export type SnapMode =
  "beat" | "downbeat" | "bar-1" | "bar-2" | "bar-4" | "free";

export interface SnapTarget {
  time: number;
  index: number;
  kind: "beat" | "downbeat" | "bar";
}

function candidatesFor(
  mode: SnapMode,
  beats: number[],
  downbeats: number[],
): { values: number[]; kind: SnapTarget["kind"] } {
  if (mode === "beat") return { values: beats, kind: "beat" };
  if (mode === "downbeat") return { values: downbeats, kind: "downbeat" };
  if (mode.startsWith("bar-")) {
    const interval = Number(mode.slice(4));
    return {
      values: downbeats.filter((_, index) => index % interval === 0),
      kind: "bar",
    };
  }
  return { values: [], kind: "beat" };
}

export function snapTime(
  time: number,
  mode: SnapMode,
  beats: number[],
  downbeats: number[],
  thresholdSeconds: number,
  disabled = false,
): SnapTarget | undefined {
  if (disabled || mode === "free") return undefined;
  const { values, kind } = candidatesFor(mode, beats, downbeats);
  let closestIndex = -1;
  let closestDistance = Number.POSITIVE_INFINITY;
  values.forEach((candidate, index) => {
    const distance = Math.abs(candidate - time);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestIndex = index;
    }
  });
  if (closestIndex < 0 || closestDistance > thresholdSeconds) return undefined;
  const snappedTime = values[closestIndex];
  const beatIndex = beats.findIndex(
    (beat) => Math.abs(beat - snappedTime) < 0.000_001,
  );
  return {
    time: snappedTime,
    index: beatIndex >= 0 ? beatIndex : closestIndex,
    kind,
  };
}
