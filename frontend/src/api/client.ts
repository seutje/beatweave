import type {
  ApiErrorBody,
  AnalysisJob,
  AssetMetadata,
  AudioAnalysis,
  AudioState,
  HealthResponse,
  LayoutProposal,
  LLMProviderConfig,
  LLMProviderConfigUpdate,
  ProviderAvailability,
  VisualPlanningResult,
  Project,
  RecentProject,
  Timeline,
  UpdateProject,
} from "./types";

export const API_BASE_URL = "http://127.0.0.1:8420";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "request_failed",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // The status text is the useful fallback for non-JSON proxy errors.
    }
    throw new ApiError(
      body?.error.message ?? response.statusText,
      response.status,
      body?.error.code,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: (): Promise<HealthResponse> => request("/health"),
  llm: {
    config: (): Promise<LLMProviderConfig> => request("/llm/config"),
    updateConfig: (
      config: LLMProviderConfigUpdate,
    ): Promise<LLMProviderConfig> =>
      request("/llm/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
    test: (): Promise<ProviderAvailability> =>
      request("/llm/test", { method: "POST" }),
  },
  planning: {
    generate: (confirmOverwrite = false): Promise<VisualPlanningResult> =>
      request("/planning/visual-plan", {
        method: "POST",
        body: JSON.stringify({ confirm_overwrite: confirmOverwrite }),
      }),
    regenerateScene: (
      sceneId: string,
      confirmOverwrite = false,
    ): Promise<VisualPlanningResult> =>
      request(`/planning/scenes/${encodeURIComponent(sceneId)}/regenerate`, {
        method: "POST",
        body: JSON.stringify({ confirm_overwrite: confirmOverwrite }),
      }),
  },
  projects: {
    current: (): Promise<Project | null> => request("/projects/current"),
    recent: (): Promise<RecentProject[]> => request("/projects/recent"),
    create: (name: string, parentDirectory: string): Promise<Project> =>
      request("/projects", {
        method: "POST",
        body: JSON.stringify({ name, parent_directory: parentDirectory }),
      }),
    open: (path: string): Promise<Project> =>
      request("/projects/open", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    close: (): Promise<{ status: "closed" }> =>
      request("/projects/close", { method: "POST" }),
    update: (id: string, update: UpdateProject): Promise<Project> =>
      request(`/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(update),
      }),
  },
  media: {
    currentAudio: (): Promise<AudioState> => request("/media/audio"),
    importAudio: (path: string): Promise<AudioState> =>
      request("/media/audio/import", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    audioContentUrl: `${API_BASE_URL}/media/audio/content`,
    references: (): Promise<AssetMetadata[]> => request("/media/references"),
    importReference: (path: string): Promise<AssetMetadata> =>
      request("/media/references", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    removeReference: (id: string): Promise<{ status: "removed" }> =>
      request(`/media/references/${id}`, { method: "DELETE" }),
    referenceContentUrl: (id: string): string =>
      `${API_BASE_URL}/media/references/${encodeURIComponent(id)}/content`,
  },
  analysis: {
    current: (): Promise<AudioAnalysis | null> => request("/analysis"),
    start: (force = false): Promise<AnalysisJob> =>
      request(`/analysis?force=${force}`, { method: "POST" }),
    job: (id: string): Promise<AnalysisJob> => request(`/analysis/jobs/${id}`),
  },
  timeline: {
    current: (): Promise<Timeline> => request("/timeline"),
    createScene: (atTime?: number, beatIndex?: number): Promise<Timeline> =>
      request("/timeline/scenes", {
        method: "POST",
        body: JSON.stringify({ at_time: atTime, beat_index: beatIndex }),
      }),
    deleteScene: (id: string): Promise<Timeline> =>
      request(`/timeline/scenes/${id}`, { method: "DELETE" }),
    updateScene: (
      id: string,
      update: {
        concept?: string;
        image_prompt?: string;
        video_prompt?: string;
      },
    ): Promise<Timeline> =>
      request(`/timeline/scenes/${id}`, {
        method: "PATCH",
        body: JSON.stringify(update),
      }),
    moveBoundary: (
      id: string,
      time: number,
      beatIndex?: number,
    ): Promise<Timeline> =>
      request(`/timeline/keyframes/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ time, beat_index: beatIndex }),
      }),
    suggestLayout: (
      preferredLengthSeconds: number,
      minimumLengthSeconds: number,
    ): Promise<LayoutProposal> =>
      request("/timeline/layout/suggest", {
        method: "POST",
        body: JSON.stringify({
          preferred_length_seconds: preferredLengthSeconds,
          minimum_length_seconds: minimumLengthSeconds,
        }),
      }),
    applyLayout: (proposal: LayoutProposal): Promise<Timeline> =>
      request("/timeline/layout/apply", {
        method: "POST",
        body: JSON.stringify({ boundaries: proposal.boundaries }),
      }),
    undoLayout: (): Promise<Timeline> =>
      request("/timeline/layout/undo", { method: "POST" }),
    undo: (): Promise<Timeline> =>
      request("/timeline/history/undo", { method: "POST" }),
    redo: (): Promise<Timeline> =>
      request("/timeline/history/redo", { method: "POST" }),
  },
};
