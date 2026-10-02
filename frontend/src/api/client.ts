import type {
  ApiErrorBody,
  AnalysisJob,
  ApplicationLogs,
  AssetMetadata,
  AudioAnalysis,
  AudioState,
  ComfyUIConfig,
  ComfyUIStatus,
  ExportReadiness,
  HealthResponse,
  LayoutProposal,
  KeyframeDetail,
  LLMProviderConfig,
  LLMProviderConfigUpdate,
  ProviderAvailability,
  VisualPlanningResult,
  Project,
  ProjectBackup,
  ProjectIntegrityReport,
  RecentProject,
  SceneVideoTakes,
  TimelineVideoTakes,
  Timeline,
  UpdateProject,
  Wan2GPConfig,
  Wan2GPStatus,
} from "./types";

export const API_BASE_URL = "http://127.0.0.1:8420";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "request_failed",
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (reason) {
    throw new ApiError(
      "Beatweave could not reach its local backend. Keep the project open, then retry once the service is running.",
      0,
      "backend_unavailable",
      { cause: reason instanceof Error ? reason.message : "Network failure" },
    );
  }
  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // The status text is the useful fallback for non-JSON proxy errors.
    }
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : response.statusText || `Request failed (${response.status})`;
    throw new ApiError(
      body?.error?.message ?? detail,
      response.status,
      body?.error?.code,
      body?.error?.details,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: (): Promise<HealthResponse> => request("/health"),
  comfyui: {
    config: (): Promise<ComfyUIConfig> => request("/comfyui/config"),
    updateConfig: (config: ComfyUIConfig): Promise<ComfyUIConfig> =>
      request("/comfyui/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
    test: (): Promise<ComfyUIStatus> =>
      request("/comfyui/test", { method: "POST" }),
  },
  wan2gp: {
    config: (): Promise<Wan2GPConfig> => request("/wan2gp/config"),
    updateConfig: (config: Wan2GPConfig): Promise<Wan2GPConfig> =>
      request("/wan2gp/config", {
        method: "PUT",
        body: JSON.stringify(config),
      }),
    test: (): Promise<Wan2GPStatus> =>
      request("/wan2gp/test", { method: "POST" }),
  },
  videoTakes: {
    timeline: (): Promise<TimelineVideoTakes> => request("/scenes/takes"),
    detail: (sceneId: string): Promise<SceneVideoTakes> =>
      request(`/scenes/${encodeURIComponent(sceneId)}/takes`),
    render: (
      sceneId: string,
      qualityMode: "preview" | "final",
      sourceTakeId?: string,
      selectOnComplete = false,
    ): Promise<{ job: AnalysisJob }> =>
      request(`/scenes/${encodeURIComponent(sceneId)}/renders`, {
        method: "POST",
        body: JSON.stringify({
          quality_mode: qualityMode,
          source_take_id: sourceTakeId,
          select_on_complete: selectOnComplete,
        }),
      }),
    select: (
      sceneId: string,
      takeId: string,
    ): Promise<{ detail: SceneVideoTakes }> =>
      request(
        `/scenes/${encodeURIComponent(sceneId)}/takes/${encodeURIComponent(takeId)}/select`,
        { method: "POST" },
      ),
    delete: (sceneId: string, takeId: string): Promise<SceneVideoTakes> =>
      request(
        `/scenes/${encodeURIComponent(sceneId)}/takes/${encodeURIComponent(takeId)}`,
        { method: "DELETE" },
      ),
  },
  exports: {
    readiness: (): Promise<ExportReadiness> => request("/exports/readiness"),
    start: (body: {
      filename: string;
      codec: "h264" | "h265";
      crf: number;
      frame_rate: number;
      width: number;
      height: number;
    }): Promise<{ job: AnalysisJob }> =>
      request("/exports", { method: "POST", body: JSON.stringify(body) }),
  },
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
    integrity: (verifyHashes = false): Promise<ProjectIntegrityReport> =>
      request(`/projects/integrity?verify_hashes=${verifyHashes}`),
    backup: (): Promise<ProjectBackup> =>
      request("/projects/backup", { method: "POST" }),
    relinkAsset: (
      assetId: string,
      path: string,
    ): Promise<{ asset: AssetMetadata; path: string }> =>
      request(`/projects/assets/${encodeURIComponent(assetId)}/relink`, {
        method: "POST",
        body: JSON.stringify({ path }),
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
    assetContentUrl: (id: string): string =>
      `${API_BASE_URL}/media/assets/${encodeURIComponent(id)}/content`,
    assetLocation: (id: string): Promise<{ path: string }> =>
      request(`/media/assets/${encodeURIComponent(id)}/location`),
  },
  jobs: {
    list: (): Promise<AnalysisJob[]> => request("/jobs"),
    get: (id: string): Promise<AnalysisJob> =>
      request(`/jobs/${encodeURIComponent(id)}`),
    retry: (id: string): Promise<{ job: AnalysisJob }> =>
      request(`/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
    cancel: (id: string): Promise<{ job: AnalysisJob }> =>
      request(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  },
  diagnostics: {
    logs: (): Promise<ApplicationLogs> => request("/diagnostics/logs"),
    logExportUrl: `${API_BASE_URL}/diagnostics/logs/export`,
  },
  keyframes: {
    detail: (id: string): Promise<KeyframeDetail> =>
      request(`/keyframes/${encodeURIComponent(id)}`),
    generate: (
      id: string,
      body: {
        prompt: string;
        include_global_style_references: boolean;
        include_previous_keyframe: boolean;
        additional_reference_asset_ids: string[];
        reference_mode: "semantic" | "structural";
        quality_mode: "preview" | "final";
        seed?: number;
      },
    ): Promise<{ job: AnalysisJob }> =>
      request(`/keyframes/${encodeURIComponent(id)}/generate`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    select: (
      id: string,
      variantId: string,
      confirmStaleRenders = false,
    ): Promise<{
      detail: KeyframeDetail;
      timeline: Timeline;
      stale_scene_ids: string[];
    }> =>
      request(
        `/keyframes/${encodeURIComponent(id)}/variants/${encodeURIComponent(variantId)}/select`,
        {
          method: "POST",
          body: JSON.stringify({ confirm_stale_renders: confirmStaleRenders }),
        },
      ),
    deleteVariant: (
      id: string,
      variantId: string,
    ): Promise<{
      detail: KeyframeDetail;
      timeline: Timeline;
      stale_scene_ids: string[];
    }> =>
      request(
        `/keyframes/${encodeURIComponent(id)}/variants/${encodeURIComponent(variantId)}`,
        { method: "DELETE" },
      ),
    setBlack: (
      id: string,
      confirmStaleRenders = false,
    ): Promise<{
      detail: KeyframeDetail;
      timeline: Timeline;
      stale_scene_ids: string[];
    }> =>
      request(`/keyframes/${encodeURIComponent(id)}/black`, {
        method: "POST",
        body: JSON.stringify({ confirm_stale_renders: confirmStaleRenders }),
      }),
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
