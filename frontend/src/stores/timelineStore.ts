import { create } from "zustand";

import { api } from "../api/client";
import type { LayoutProposal, Timeline } from "../api/types";
import { useProjectStore } from "./projectStore";

export type TimelineInspectorTab =
  "prompts" | "video" | "start-frame" | "end-frame";

interface TimelineState {
  timeline?: Timeline;
  proposal?: LayoutProposal;
  loading: boolean;
  error?: string;
  selectedSceneId?: string;
  selectedKeyframeId?: string;
  inspectorTab: TimelineInspectorTab;
  load: () => Promise<void>;
  createScene: (atTime?: number, beatIndex?: number) => Promise<void>;
  deleteScene: (id: string) => Promise<void>;
  moveBoundary: (id: string, time: number, beatIndex?: number) => Promise<void>;
  suggestLayout: (
    preferredLength: number,
    minimumLength: number,
  ) => Promise<void>;
  applyLayout: () => Promise<void>;
  cancelProposal: () => void;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  updateScene: (
    id: string,
    update: {
      concept?: string;
      image_prompt?: string;
      video_prompt?: string;
      approved?: boolean;
      use_last_frame_conditioning?: boolean;
    },
  ) => Promise<void>;
  generateVisualPlan: (confirmOverwrite?: boolean) => Promise<void>;
  regenerateScene: (id: string, confirmOverwrite?: boolean) => Promise<void>;
  selectScene: (id?: string) => void;
  selectKeyframe: (id?: string) => void;
  selectInspectorTab: (tab: TimelineInspectorTab) => void;
  clear: () => void;
  clearError: () => void;
}

const message = (reason: unknown) =>
  reason instanceof Error ? reason.message : "Timeline operation failed";

export const useTimelineStore = create<TimelineState>((set) => ({
  loading: false,
  inspectorTab: "prompts",
  load: async () => {
    set({ loading: true, error: undefined });
    try {
      set({ timeline: await api.timeline.current(), loading: false });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  createScene: async (atTime, beatIndex) => {
    set({ loading: true, error: undefined });
    try {
      const timeline = await api.timeline.createScene(atTime, beatIndex);
      const created =
        atTime === undefined
          ? timeline.scenes[0]
          : timeline.scenes.find(
              (scene) => Math.abs(scene.start_time - atTime) < 0.000_001,
            );
      const inspectorTab = useTimelineStore.getState().inspectorTab;
      const selectedKeyframeId =
        inspectorTab === "start-frame"
          ? created?.start_keyframe_id
          : inspectorTab === "end-frame"
            ? created?.end_keyframe_id
            : undefined;
      set({
        timeline,
        selectedSceneId: created?.id,
        selectedKeyframeId,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  deleteScene: async (id) => {
    set({ loading: true, error: undefined });
    try {
      const timeline = await api.timeline.deleteScene(id);
      set({
        timeline,
        selectedSceneId: undefined,
        selectedKeyframeId: undefined,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  moveBoundary: async (id, time, beatIndex) => {
    set({ loading: true, error: undefined });
    try {
      set({
        timeline: await api.timeline.moveBoundary(id, time, beatIndex),
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  suggestLayout: async (preferredLength, minimumLength) => {
    set({ loading: true, error: undefined });
    try {
      set({
        proposal: await api.timeline.suggestLayout(
          preferredLength,
          minimumLength,
        ),
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  applyLayout: async () => {
    const proposal = useTimelineStore.getState().proposal;
    if (!proposal) return;
    set({ loading: true, error: undefined });
    try {
      set({
        timeline: await api.timeline.applyLayout(proposal),
        proposal: undefined,
        selectedSceneId: undefined,
        selectedKeyframeId: undefined,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  cancelProposal: () => set({ proposal: undefined }),
  undo: async () => {
    set({ loading: true, error: undefined });
    try {
      set({
        timeline: await api.timeline.undo(),
        proposal: undefined,
        selectedSceneId: undefined,
        selectedKeyframeId: undefined,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  redo: async () => {
    set({ loading: true, error: undefined });
    try {
      set({
        timeline: await api.timeline.redo(),
        proposal: undefined,
        selectedSceneId: undefined,
        selectedKeyframeId: undefined,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  updateScene: async (id, update) => {
    set({ loading: true, error: undefined });
    try {
      set({
        timeline: await api.timeline.updateScene(id, update),
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  generateVisualPlan: async (confirmOverwrite = false) => {
    set({ loading: true, error: undefined });
    try {
      const result = await api.planning.generate(confirmOverwrite);
      useProjectStore.setState({ current: result.project });
      set({ timeline: result.timeline, loading: false });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  regenerateScene: async (id, confirmOverwrite = false) => {
    set({ loading: true, error: undefined });
    try {
      const result = await api.planning.regenerateScene(id, confirmOverwrite);
      useProjectStore.setState({ current: result.project });
      set({ timeline: result.timeline, loading: false });
    } catch (reason) {
      set({ loading: false, error: message(reason) });
    }
  },
  selectScene: (selectedSceneId) =>
    set((state) => {
      const scene = state.timeline?.scenes.find(
        (item) => item.id === selectedSceneId,
      );
      const selectedKeyframeId =
        state.inspectorTab === "start-frame"
          ? scene?.start_keyframe_id
          : state.inspectorTab === "end-frame"
            ? scene?.end_keyframe_id
            : undefined;
      return { selectedSceneId, selectedKeyframeId };
    }),
  selectKeyframe: (selectedKeyframeId) =>
    set((state) => {
      if (!selectedKeyframeId) return { selectedKeyframeId: undefined };
      const startScene = state.timeline?.scenes.find(
        (scene) => scene.start_keyframe_id === selectedKeyframeId,
      );
      if (startScene) {
        return {
          selectedSceneId: startScene.id,
          selectedKeyframeId,
          inspectorTab: "start-frame",
        };
      }
      const endScene = state.timeline?.scenes.find(
        (scene) => scene.end_keyframe_id === selectedKeyframeId,
      );
      return {
        selectedSceneId: endScene?.id,
        selectedKeyframeId,
        inspectorTab: "end-frame",
      };
    }),
  selectInspectorTab: (inspectorTab) =>
    set((state) => {
      const scene = state.timeline?.scenes.find(
        (item) => item.id === state.selectedSceneId,
      );
      const selectedKeyframeId =
        inspectorTab === "start-frame"
          ? scene?.start_keyframe_id
          : inspectorTab === "end-frame"
            ? scene?.end_keyframe_id
            : undefined;
      return { inspectorTab, selectedKeyframeId };
    }),
  clear: () =>
    set({
      timeline: undefined,
      selectedSceneId: undefined,
      selectedKeyframeId: undefined,
      proposal: undefined,
    }),
  clearError: () => set({ error: undefined }),
}));
