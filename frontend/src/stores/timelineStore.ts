import { create } from "zustand";

import { api } from "../api/client";
import type { Timeline } from "../api/types";

interface TimelineState {
  timeline?: Timeline;
  loading: boolean;
  error?: string;
  selectedSceneId?: string;
  selectedKeyframeId?: string;
  load: () => Promise<void>;
  createScene: (atTime?: number, beatIndex?: number) => Promise<void>;
  deleteScene: (id: string) => Promise<void>;
  moveBoundary: (id: string, time: number, beatIndex?: number) => Promise<void>;
  selectScene: (id?: string) => void;
  selectKeyframe: (id?: string) => void;
  clear: () => void;
  clearError: () => void;
}

const message = (reason: unknown) =>
  reason instanceof Error ? reason.message : "Timeline operation failed";

export const useTimelineStore = create<TimelineState>((set) => ({
  loading: false,
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
      set({ timeline, selectedSceneId: created?.id, loading: false });
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
  selectScene: (selectedSceneId) =>
    set({ selectedSceneId, selectedKeyframeId: undefined }),
  selectKeyframe: (selectedKeyframeId) =>
    set({ selectedKeyframeId, selectedSceneId: undefined }),
  clear: () =>
    set({
      timeline: undefined,
      selectedSceneId: undefined,
      selectedKeyframeId: undefined,
    }),
  clearError: () => set({ error: undefined }),
}));
