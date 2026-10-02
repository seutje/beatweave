import { describe, expect, it } from "vitest";

import { snapTime } from "./snapping";
import { containSize, createTimelineTransform } from "./transform";

describe("timeline transform", () => {
  it("round-trips time while zoomed and scrolled", () => {
    const transform = createTimelineTransform(125, 310);
    expect(transform.timeToX(4)).toBe(190);
    expect(transform.xToTime(190)).toBe(4);
  });

  it("keeps the playback head derived from time after zooming", () => {
    expect(createTimelineTransform(50).timeToX(3.25)).toBe(162.5);
    expect(createTimelineTransform(100).timeToX(3.25)).toBe(325);
  });
});

describe("timeline keyframe thumbnails", () => {
  it("fits landscape images without changing their aspect ratio", () => {
    expect(containSize(1920, 1080, 64, 40)).toEqual({
      width: 64,
      height: 36,
    });
  });

  it("fits portrait images without changing their aspect ratio", () => {
    const size = containSize(800, 1200, 64, 40);
    expect(size.width).toBeCloseTo(26.667);
    expect(size.height).toBe(40);
  });
});

describe("timeline snapping", () => {
  const beats = [0.5, 1, 1.5, 2];
  const downbeats = [0.5, 2];

  it("uses real detected timestamps", () => {
    expect(snapTime(1.46, "beat", beats, downbeats, 0.1)).toEqual({
      time: 1.5,
      index: 2,
      kind: "beat",
    });
  });

  it("allows free placement and a temporary modifier bypass", () => {
    expect(snapTime(1.46, "free", beats, downbeats, 0.1)).toBeUndefined();
    expect(snapTime(1.46, "beat", beats, downbeats, 0.1, true)).toBeUndefined();
  });
});
