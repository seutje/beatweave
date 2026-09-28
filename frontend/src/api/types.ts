export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface LLMProviderConfig {
  provider: "openai_compatible";
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key_configured: boolean;
}

export interface LLMProviderConfigUpdate {
  provider: "openai_compatible";
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key?: string;
}

export interface ProviderAvailability {
  available: boolean;
  message: string;
}

export interface VisualPlanningResult {
  project: Project;
  timeline: Timeline;
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
  visual_trajectory: VisualTrajectoryStage[];
}

export interface VisualTrajectoryStage {
  position: number;
  description: string;
  intensity: number;
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

export interface EnergySample {
  time: number;
  value: number;
  rms: number;
  spectral_flux: number;
  onset_density: number;
}

export interface AudioAnalysis {
  id: string;
  asset_id: string;
  source_sha256: string;
  bpm_estimate?: number;
  beats: number[];
  downbeats: number[];
  energy_curve: EnergySample[];
  parameters: {
    beat_analyzer: string;
    beat_model: string;
    beat_device: string;
    energy_sample_rate: number;
    frame_length: number;
    hop_length: number;
    energy_weights: Record<string, number>;
    normalization_percentiles: [number, number];
  };
  created_at: string;
}

export interface AnalysisJob {
  id: string;
  type: "audio_analysis";
  state: "queued" | "running" | "complete" | "failed";
  progress: number;
  related_entity_id: string;
  output: Record<string, unknown>;
  error?: { code: string; message: string };
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface Keyframe {
  id: string;
  time: number;
  prompt: string;
  selected_variant_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  position: number;
  start_time: number;
  end_time: number;
  start_beat_index?: number;
  end_beat_index?: number;
  start_keyframe_id: string;
  end_keyframe_id: string;
  concept: string;
  image_prompt: string;
  video_prompt: string;
  visual_energy: number;
  motion_energy: number;
  selected_video_take_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Timeline {
  duration_seconds: number;
  scenes: Scene[];
  keyframes: Keyframe[];
  can_undo: boolean;
  can_redo: boolean;
}

export interface ProposedBoundary {
  time: number;
  beat_index?: number;
  reason: string;
  energy_change: number;
}

export interface LayoutProposal {
  duration_seconds: number;
  preferred_length_seconds: number;
  minimum_length_seconds: number;
  maximum_length_seconds: number;
  default_preferred_lengths: number[];
  boundaries: ProposedBoundary[];
}
