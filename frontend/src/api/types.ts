export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface BackendEvent {
  type: string;
  payload: Record<string, unknown>;
}
