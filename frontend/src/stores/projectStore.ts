import { create } from "zustand";

import { api } from "../api/client";
import type {
  AnalysisJob,
  AssetMetadata,
  AudioAnalysis,
  AudioState,
  Project,
  RecentProject,
  UpdateProject,
} from "../api/types";

interface ProjectState {
  current?: Project;
  recent: RecentProject[];
  audio?: AudioState;
  analysis?: AudioAnalysis;
  analysisJob?: AnalysisJob;
  styleReferences: AssetMetadata[];
  loading: boolean;
  error?: string;
  load: () => Promise<void>;
  createProject: (name: string, parentDirectory: string) => Promise<void>;
  openProject: (path: string) => Promise<void>;
  closeProject: () => Promise<void>;
  updateProject: (update: UpdateProject) => Promise<void>;
  importAudio: (path: string) => Promise<void>;
  importStyleReference: (path: string) => Promise<void>;
  removeStyleReference: (id: string) => Promise<void>;
  analyze: (force?: boolean) => Promise<void>;
  clearError: () => void;
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "The project operation failed";
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  recent: [],
  styleReferences: [],
  loading: false,
  load: async () => {
    set({ loading: true, error: undefined });
    try {
      const [current, recent] = await Promise.all([
        api.projects.current(),
        api.projects.recent(),
      ]);
      const audio = current?.audio_asset_id
        ? await api.media.currentAudio()
        : undefined;
      const analysis = audio ? await api.analysis.current() : undefined;
      const styleReferences = current ? await api.media.references() : [];
      set({
        current: current ?? undefined,
        recent,
        audio,
        analysis: analysis ?? undefined,
        styleReferences,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  createProject: async (name, parentDirectory) => {
    set({ loading: true, error: undefined });
    try {
      const current = await api.projects.create(name, parentDirectory);
      const recent = await api.projects.recent();
      set({
        current,
        recent,
        audio: undefined,
        analysis: undefined,
        styleReferences: [],
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
      throw reason;
    }
  },
  openProject: async (path) => {
    set({ loading: true, error: undefined });
    try {
      const current = await api.projects.open(path);
      const audio = current.audio_asset_id
        ? await api.media.currentAudio()
        : undefined;
      const analysis = audio ? await api.analysis.current() : undefined;
      const styleReferences = await api.media.references();
      const recent = await api.projects.recent();
      set({
        current,
        recent,
        audio,
        analysis: analysis ?? undefined,
        styleReferences,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  closeProject: async () => {
    set({ loading: true, error: undefined });
    try {
      await api.projects.close();
      set({
        current: undefined,
        audio: undefined,
        analysis: undefined,
        analysisJob: undefined,
        styleReferences: [],
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  updateProject: async (update) => {
    const current = get().current;
    if (!current) return;
    set({ loading: true, error: undefined });
    try {
      const updated = await api.projects.update(current.id, update);
      const recent = await api.projects.recent();
      set({ current: updated, recent, loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  importAudio: async (path) => {
    set({ loading: true, error: undefined });
    try {
      const audio = await api.media.importAudio(path);
      const recent = await api.projects.recent();
      set({
        current: audio.project,
        audio,
        analysis: undefined,
        analysisJob: undefined,
        recent,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  importStyleReference: async (path) => {
    set({ loading: true, error: undefined });
    try {
      await api.media.importReference(path);
      set({ styleReferences: await api.media.references(), loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  removeStyleReference: async (id) => {
    set({ loading: true, error: undefined });
    try {
      await api.media.removeReference(id);
      set({ styleReferences: await api.media.references(), loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  analyze: async (force = false) => {
    set({ loading: true, error: undefined });
    try {
      let job = await api.analysis.start(force);
      set({ analysisJob: job });
      while (job.state === "queued" || job.state === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        job = await api.analysis.job(job.id);
        set({ analysisJob: job });
      }
      if (job.state === "failed") {
        set({
          loading: false,
          error: job.error?.message ?? "Track analysis failed",
        });
        return;
      }
      const analysis = await api.analysis.current();
      set({
        analysis: analysis ?? undefined,
        analysisJob: job,
        loading: false,
      });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  clearError: () => set({ error: undefined }),
}));
