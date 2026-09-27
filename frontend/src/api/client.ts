import type { ApiErrorBody, HealthResponse } from "./types";

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
};
