import { describe, expect, it } from "vitest";

import type { AnalysisJob, BackendEvent } from "../api/types";
import { trackedJobFromEvent } from "./exportJobTracking";
import { EXPORT_PRESETS } from "./exportPresets";

describe("export presets", () => {
  it("makes 4K larger and higher quality than the 1080p preset", () => {
    expect(EXPORT_PRESETS["4k"].width).toBe(3840);
    expect(EXPORT_PRESETS["4k"].height).toBe(2160);
    expect(EXPORT_PRESETS["4k"].crf).toBeLessThan(EXPORT_PRESETS["1080p"].crf);
  });
});

describe("export job tracking", () => {
  const job = {
    id: "export-1",
    type: "final_assembly",
    state: "running",
    progress: 0.65,
    project_id: "project-1",
    output: {},
    created_at: "2026-10-02T10:00:00Z",
    updated_at: "2026-10-02T10:01:00Z",
  } satisfies AnalysisJob;

  it("accepts live updates for the active export", () => {
    const event: BackendEvent = { type: "job-progress", payload: job };
    expect(trackedJobFromEvent(event, job.id)).toEqual(job);
  });

  it("ignores unrelated jobs and non-job events", () => {
    expect(
      trackedJobFromEvent({ type: "job-progress", payload: job }, "other"),
    ).toBeUndefined();
    expect(
      trackedJobFromEvent({ type: "project-updated", payload: job }, job.id),
    ).toBeUndefined();
  });
});
