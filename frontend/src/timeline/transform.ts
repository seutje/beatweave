export interface TimelineTransform {
  timeToX(time: number): number;
  xToTime(x: number): number;
}

export interface ContainedSize {
  width: number;
  height: number;
}

export function containSize(
  sourceWidth: number,
  sourceHeight: number,
  maximumWidth: number,
  maximumHeight: number,
): ContainedSize {
  if (sourceWidth <= 0 || sourceHeight <= 0) {
    return { width: maximumWidth, height: maximumHeight };
  }
  const scale = Math.min(
    maximumWidth / sourceWidth,
    maximumHeight / sourceHeight,
  );
  return { width: sourceWidth * scale, height: sourceHeight * scale };
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
