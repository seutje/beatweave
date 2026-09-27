import { describe, expect, it } from "vitest";

import { formatTime, seekAudio } from "../lib/audioPlayback";

describe("audio playback helpers", () => {
  it("formats timeline time", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(125.9)).toBe("2:05");
  });

  it("seeks to the requested timeline position", () => {
    const audio = { currentTime: 0 };
    seekAudio(audio, 42.25);
    expect(audio.currentTime).toBe(42.25);
  });
});
