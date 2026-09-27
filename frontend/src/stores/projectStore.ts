import { create } from "zustand";

import { api } from "../api/client";
import type { Project, RecentProject, UpdateProject } from "../api/types";

interface ProjectState {
  current?: Project;
  recent: RecentProject[];
  loading: boolean;
  error?: string;
  load: () => Promise<void>;
  createProject: (name: string, parentDirectory: string) => Promise<void>;
  openProject: (path: string) => Promise<void>;
  closeProject: () => Promise<void>;
  updateProject: (update: UpdateProject) => Promise<void>;
  clearError: () => void;
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "The project operation failed";
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  recent: [],
  loading: false,
  load: async () => {
    set({ loading: true, error: undefined });
    try {
      const [current, recent] = await Promise.all([
        api.projects.current(),
        api.projects.recent(),
      ]);
      set({ current: current ?? undefined, recent, loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  createProject: async (name, parentDirectory) => {
    set({ loading: true, error: undefined });
    try {
      const current = await api.projects.create(name, parentDirectory);
      const recent = await api.projects.recent();
      set({ current, recent, loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
      throw reason;
    }
  },
  openProject: async (path) => {
    set({ loading: true, error: undefined });
    try {
      const current = await api.projects.open(path);
      const recent = await api.projects.recent();
      set({ current, recent, loading: false });
    } catch (reason) {
      set({ loading: false, error: errorMessage(reason) });
    }
  },
  closeProject: async () => {
    set({ loading: true, error: undefined });
    try {
      await api.projects.close();
      set({ current: undefined, loading: false });
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
  clearError: () => set({ error: undefined }),
}));
