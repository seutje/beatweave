export interface TimelineTransform {
  timeToX(time: number): number;
  xToTime(x: number): number;
}

export function createTimelineTransform(
  pixelsPerSecond: number,
  scrollX = 0,
): TimelineTransform {
  if (pixelsPerSecond <= 0) throw new Error("pixelsPerSecond must be positive");
  return {
    timeToX: (time) => time * pixelsPerSecond - scrollX,
    xToTime: (x) => (x + scrollX) / pixelsPerSecond,
  };
}
