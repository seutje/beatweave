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

export interface QwenWorkflowProfile {
  name: string;
  diffusion_model: string;
  text_encoder: string;
  vae: string;
  weight_dtype: string;
  cache_device: string;
  cache_dtype: string;
  default_steps: number;
  default_cfg: number;
  sampler: string;
  scheduler: string;
}

export interface ComfyUIConfig {
  base_url: string;
  request_timeout_seconds: number;
  render_timeout_seconds: number;
  poll_interval_seconds: number;
  profile: QwenWorkflowProfile;
  preview_profile: ImageQualityProfile;
  final_profile: ImageQualityProfile;
}

export interface ImageQualityProfile {
  width: number;
  height: number;
  steps: number;
  cfg: number;
}

export interface ComfyUIStatus {
  available: boolean;
  profile_ready: boolean;
  message: string;
  version?: string;
  device?: string;
}

export interface LTX23DistilledProfile {
  name: string;
  model_type: string;
  settings_version: number;
  preview: VideoQualityProfile;
  final: VideoQualityProfile;
  default_frame_rate: number;
  minimum_frames: number;
  frame_step: number;
}

export interface VideoQualityProfile {
  resolution: string;
  inference_steps: number;
}

export interface AudioReactiveLoraProfile {
  name: string;
  filename: string;
  default_multiplier: number;
  trigger_phrase: string;
}

export interface Wan2GPConfig {
  base_url: string;
  request_timeout_seconds: number;
  render_timeout_seconds: number;
  poll_interval_seconds: number;
  profile: LTX23DistilledProfile;
  audio_reactive_profile: AudioReactiveLoraProfile;
}

export interface Wan2GPStatus {
  available: boolean;
  profile_ready: boolean;
  message: string;
  version?: string;
  api_endpoints: string[];
}

export interface VideoTake {
  id: string;
  scene_id: string;
  asset_id: string;
  source_job_id: string;
  prompt: string;
  backend: string;
  backend_settings: Record<string, unknown>;
  source_asset_ids: string[];
  created_at: string;
  asset: AssetMetadata;
  asset_path: string;
  selected: boolean;
  stale: boolean;
}

export interface SceneVideoTakes {
  scene_id: string;
  selected_take_id: string | null;
  selected_take_stale: boolean;
  takes: VideoTake[];
  render_jobs: AnalysisJob[];
}

export interface TimelineVideoTakes {
  scenes: SceneVideoTakes[];
}

export interface VisualPlanningResult {
  project: Project;
  timeline: Timeline;
}

export interface ApiErrorBody {
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  detail?: string | Array<Record<string, unknown>>;
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
  type: "audio_analysis" | "keyframe_render" | "video_render" | string;
  state:
    "queued" | "preparing" | "running" | "complete" | "failed" | "cancelled";
  progress: number;
  project_id: string;
  related_entity_type?: string;
  related_entity_id?: string;
  backend?: string;
  output: Record<string, unknown>;
  error?: { code: string; message: string; details?: Record<string, unknown> };
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  cancellation_requested_at?: string;
}

export interface Keyframe {
  id: string;
  time: number;
  prompt: string;
  selected_variant_id?: string;
  selected_variant_asset_id?: string;
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
  selected_video_take_id: string | null;
  selected_video_take_stale: boolean;
  created_at: string;
  updated_at: string;
}

export interface KeyframeVariant {
  id: string;
  keyframe_id: string;
  asset_id: string;
  source_job_id: string;
  prompt: string;
  negative_prompt: string;
  backend: string;
  backend_settings: Record<string, unknown>;
  source_asset_ids: string[];
  created_at: string;
  asset: AssetMetadata;
  asset_path: string;
}

export interface KeyframeDetail {
  keyframe: Keyframe;
  variants: KeyframeVariant[];
  render_jobs: AnalysisJob[];
  adjacent_scene_ids: string[];
  affected_render_scene_ids: string[];
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
