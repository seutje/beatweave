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

export interface CreativeBrief {
  concept: string;
  style: string;
  motifs: string[];
  palette: string[];
  narrative_arc: string;
  negative_guidance: string;
}

export interface ProjectSettings {
  max_clip_length_seconds: number;
}

export interface Project {
  id: string;
  name: string;
  version: number;
  path: string;
  created_at: string;
  updated_at: string;
  creative_brief: CreativeBrief;
  settings: ProjectSettings;
  audio_asset_id?: string;
}

export interface RecentProject {
  id: string;
  name: string;
  path: string;
  updated_at: string;
  exists: boolean;
}

export interface UpdateProject {
  name?: string;
  creative_brief?: CreativeBrief;
  settings?: ProjectSettings;
}

export interface AssetMetadata {
  id: string;
  kind: string;
  relative_path: string;
  original_path?: string;
  filename: string;
  mime_type?: string;
  sha256: string;
  size_bytes: number;
  media_metadata: Record<string, unknown>;
  created_at: string;
}

export interface WaveformData {
  source_sha256: string;
  sample_rate: number;
  duration_seconds: number;
  peaks: number[];
  generated_at: string;
}

export interface AudioState {
  project: Project;
  asset: AssetMetadata;
  waveform: WaveformData;
}
