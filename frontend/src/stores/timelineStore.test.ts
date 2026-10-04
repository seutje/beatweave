import { beforeEach, describe, expect, it } from "vitest";

import type { Keyframe, Scene, Timeline } from "../api/types";
import { useTimelineStore } from "./timelineStore";

const keyframe = (id: string, time: number): Keyframe => ({
  id,
  time,
  prompt: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

const scene = (
  id: string,
  position: number,
  startKeyframeId: string,
  endKeyframeId: string,
): Scene => ({
  id,
  position,
  start_time: position * 5,
  end_time: (position + 1) * 5,
  start_keyframe_id: startKeyframeId,
  end_keyframe_id: endKeyframeId,
  concept: "",
  image_prompt: "",
  video_prompt: "",
  visual_energy: 0.5,
  motion_energy: 0.5,
  selected_video_take_id: null,
  selected_video_take_stale: false,
  approved: false,
  use_last_frame_conditioning: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

const timeline: Timeline = {
  duration_seconds: 10,
  scenes: [
    scene("scene-1", 0, "keyframe-0", "keyframe-1"),
    scene("scene-2", 1, "keyframe-1", "keyframe-2"),
  ],
  keyframes: [
    keyframe("keyframe-0", 0),
    keyframe("keyframe-1", 5),
    keyframe("keyframe-2", 10),
  ],
  can_undo: false,
  can_redo: false,
};

describe("timeline inspector tabs", () => {
  beforeEach(() => {
    useTimelineStore.setState({
      timeline,
      selectedSceneId: "scene-1",
      selectedKeyframeId: undefined,
      inspectorTab: "prompts",
    });
  });

  it("keeps the selected scene tab when switching scenes", () => {
    const store = useTimelineStore.getState();
    store.selectInspectorTab("video");
    store.selectScene("scene-2");

    expect(useTimelineStore.getState()).toMatchObject({
      inspectorTab: "video",
      selectedSceneId: "scene-2",
      selectedKeyframeId: undefined,
    });
  });

  it("moves a persistent frame tab to the same boundary of another scene", () => {
    const store = useTimelineStore.getState();
    store.selectInspectorTab("end-frame");
    expect(useTimelineStore.getState().selectedKeyframeId).toBe("keyframe-1");

    store.selectScene("scene-2");
    expect(useTimelineStore.getState()).toMatchObject({
      inspectorTab: "end-frame",
      selectedSceneId: "scene-2",
      selectedKeyframeId: "keyframe-2",
    });
  });

  it("opens a shared boundary as the following scene's start frame", () => {
    useTimelineStore.getState().selectKeyframe("keyframe-1");

    expect(useTimelineStore.getState()).toMatchObject({
      inspectorTab: "start-frame",
      selectedSceneId: "scene-2",
      selectedKeyframeId: "keyframe-1",
    });
  });

  it("opens the final boundary as the final scene's end frame", () => {
    useTimelineStore.getState().selectKeyframe("keyframe-2");

    expect(useTimelineStore.getState()).toMatchObject({
      inspectorTab: "end-frame",
      selectedSceneId: "scene-2",
      selectedKeyframeId: "keyframe-2",
    });
  });
});
