import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { BackendEvent } from "../api/types";
import { useProjectStore } from "../stores/projectStore";
import { useTimelineStore } from "../stores/timelineStore";
import { agentActivityFromEvent, synchronizeBackendChange } from "./useBackend";

vi.mock("../api/client", () => ({
  API_BASE_URL: "http://127.0.0.1:8420",
  api: {
    projects: { current: vi.fn(), recent: vi.fn() },
    media: { currentAudio: vi.fn(), references: vi.fn() },
    analysis: { current: vi.fn() },
    timeline: { current: vi.fn() },
  },
}));

const event = (path: string): BackendEvent => ({
  type: "project-changed",
  payload: { source: "mcp", method: "PATCH", path },
});

describe("MCP frontend synchronization", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useProjectStore.setState({
      current: undefined,
      audio: undefined,
      analysis: undefined,
      recent: [],
      styleReferences: [],
      loading: false,
    });
    useTimelineStore.getState().clear();
  });

  it("describes agent changes without treating normal job events as MCP activity", () => {
    expect(agentActivityFromEvent(event("/timeline/scenes/scene-1"))).toEqual({
      label: "timeline",
      path: "/timeline/scenes/scene-1",
    });
    expect(
      agentActivityFromEvent({ type: "job-progress", payload: {} }),
    ).toBeUndefined();
  });

  it("reloads project and timeline state after an MCP mutation", async () => {
    const project = {
      id: "project-1",
      name: "Agent Project",
      version: 1,
      path: "C:/projects/agent-project",
      created_at: "2026-10-04T10:00:00Z",
      updated_at: "2026-10-04T10:00:00Z",
      creative_brief: {
        concept: "",
        style: "",
        motifs: [],
        palette: [],
        narrative_arc: "",
        negative_guidance: "",
        visual_trajectory: [],
      },
      settings: { max_clip_length_seconds: 10 },
      audio_asset_id: "audio-1",
    };
    vi.mocked(api.projects.current).mockResolvedValue(project);
    vi.mocked(api.projects.recent).mockResolvedValue([]);
    vi.mocked(api.media.currentAudio).mockResolvedValue({
      project,
      asset: {
        id: "audio-1",
        kind: "audio",
        relative_path: "source/track.wav",
        filename: "track.wav",
        sha256: "hash",
        size_bytes: 1,
        media_metadata: {},
        created_at: "2026-10-04T10:00:00Z",
      },
      waveform: {
        source_sha256: "hash",
        sample_rate: 48_000,
        duration_seconds: 8,
        peaks: [],
        generated_at: "2026-10-04T10:00:00Z",
      },
    });
    vi.mocked(api.analysis.current).mockResolvedValue(null);
    vi.mocked(api.media.references).mockResolvedValue([]);
    vi.mocked(api.timeline.current).mockResolvedValue({
      duration_seconds: 8,
      scenes: [],
      keyframes: [],
      can_undo: false,
      can_redo: false,
    });

    await synchronizeBackendChange(event("/timeline/layout/apply"));

    expect(api.projects.current).toHaveBeenCalled();
    expect(api.timeline.current).toHaveBeenCalled();
    expect(useTimelineStore.getState().timeline?.duration_seconds).toBe(8);

    vi.mocked(api.projects.current).mockClear();
    vi.mocked(api.timeline.current).mockClear();
    await synchronizeBackendChange({ type: "job-complete", payload: {} });
    expect(api.projects.current).toHaveBeenCalled();
    expect(api.timeline.current).toHaveBeenCalled();
  });
});
