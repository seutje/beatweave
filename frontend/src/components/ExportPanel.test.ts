import { describe, expect, it } from "vitest";

import { EXPORT_PRESETS } from "./exportPresets";

describe("export presets", () => {
  it("makes 4K larger and higher quality than the 1080p preset", () => {
    expect(EXPORT_PRESETS["4k"].width).toBe(3840);
    expect(EXPORT_PRESETS["4k"].height).toBe(2160);
    expect(EXPORT_PRESETS["4k"].crf).toBeLessThan(EXPORT_PRESETS["1080p"].crf);
  });
});
