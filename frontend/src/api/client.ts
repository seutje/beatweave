import type {
  ApiErrorBody,
  AudioState,
  HealthResponse,
  Project,
  RecentProject,
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
  },
};
