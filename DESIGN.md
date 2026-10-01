# Beatweave — Design

## 1. Product Vision

Beatweave is a local-first desktop application for creating abstract, music-driven generative videos.

The central workflow is:

1. Import a song.
2. Analyze its musical structure, beats, downbeats, and energy.
3. Lay suggested scene boundaries onto a timeline.
4. Let the user refine scene timing with beat snapping.
5. Define a global visual direction, style, and abstract narrative arc.
6. Expand that direction into per-scene image prompts and video-motion prompts.
7. Generate chained keyframes, where the final keyframe of one scene is the starting keyframe of the next.
8. Render first-frame/last-frame video clips between adjacent keyframes.
9. Return generated media to the timeline for preview, comparison, prompt editing, and re-rendering.
10. Assemble or export the final sequence.

Beatweave is not intended to be a general-purpose NLE. It is a purpose-built generative music-video workstation centered on beat-aware timing, chained keyframes, prompt-driven rendering, and iterative scene regeneration.

---

## 2. Core User Experience

The primary interface is a timeline.

A typical session should feel like:

> Drop in a song → analyze → adjust scene boundaries → describe the visual arc → generate scene ideas and prompts → generate keyframes → render previews → refine weak scenes → render final clips → export.

The user should be able to work at different levels of granularity:

- Project level: regenerate or revise the overall visual arc.
- Section level: revise a group of scenes.
- Scene level: regenerate prompts or motion direction.
- Keyframe level: generate alternatives and select a preferred take.
- Clip level: render multiple video takes and select one.
- Timeline level: adjust timing without rewriting the rest of the project.

Generated content must remain editable. Beatweave should never silently replace a user-edited prompt or selected take.

---

## 3. Goals

### 3.1 Creative goals

- Make abstract generative music-video creation feel like editing rather than scripting.
- Let musical structure influence scene timing and visual intensity.
- Encourage subtle beat-aligned cuts by sharing keyframes between adjacent clips.
- Make it easy to iterate on one scene without regenerating the whole project.
- Keep prompt generation transparent and editable.
- Separate still-image intent from motion/video intent.
- Support a global visual trajectory across the entire track.

### 3.2 Technical goals

- Run locally on a Windows workstation as the default mode.
- Target development initially around:
  - NVIDIA RTX 4070 12 GB VRAM
  - 64 GB system RAM
- Allow setting a max clip length
- Reuse existing working rendering systems where practical.
- Treat Wan2GP as the initial video-render backend.
- Treat ComfyUI as the initial image-render backend.
- Keep backend-specific formats out of the core project model.
- Allow future render backends to be added without changing the timeline model.
- Persist all important state so an interrupted or closed session can resume.
- Make project files understandable and inspectable by developers and coding agents.

### 3.3 Development goals

- Support incremental implementation.
- Keep tasks small enough for coding-agent sessions.
- Make the repo easy to resume after context loss.
- Require validation before implementation tasks are marked complete.
- Prefer clear interfaces and boring boundaries over tightly coupled abstractions.

---

## 4. Non-Goals

Beatweave is not intended to become:

- A full Premiere Pro / DaVinci Resolve replacement.
- A general multitrack NLE.
- A DAW.
- A node-based ComfyUI replacement.
- A general-purpose AI agent interface.
- A character-consistency system.
- A cloud-first application.
- A model-training application.
- A generic workflow graph editor.

The initial product should remain opinionated around one workflow:

**music analysis → scene timing → visual planning → chained keyframes → first/last-frame video generation → timeline review → export**

---

## 5. Product Principles

### 5.1 Timeline-first

The timeline is the main creative workspace.

Prompt editors, scene metadata, takes, render controls, and analysis views support the timeline rather than replace it.

### 5.2 Shared keyframes

A keyframe between two adjacent scenes is one shared entity.

Conceptually:

```text
KF0 ───── Scene 1 ───── KF1 ───── Scene 2 ───── KF2
```

`KF1` is simultaneously:

- the final frame of Scene 1
- the first frame of Scene 2

The application must not duplicate that media or state across scenes.

### 5.3 Semantic project model

The core project model describes creative intent, not renderer implementation.

A scene may describe:

- timing
- concept
- visual energy
- image prompt
- motion prompt
- start keyframe
- end keyframe
- selected take

It should not contain raw ComfyUI node IDs or Wan2GP-specific queue structures as primary project data.

### 5.4 Backends are adapters

Render systems translate the canonical project model into backend-specific jobs.

Initial adapters:

- ComfyUI image backend
- Wan2GP video backend

Possible future adapters:

- native image backend
- native LTX backend
- remote GPU backend
- additional ComfyUI workflows

### 5.5 Local-first

The app must remain useful without cloud services.

Cloud LLM or image providers may be optional enhancements, not requirements for opening, editing, or rendering existing projects.

---

## 6. Proposed Technology Stack

### Desktop shell

- Tauri 2

### Frontend

- React
- TypeScript
- Zustand for transient UI state
- Canvas or PixiJS for the custom timeline renderer
- Peaks.js may be used initially for waveform display if useful

### Backend

- Python 3.12+
- FastAPI
- WebSocket event stream
- Pydantic models
- SQLite
- SQLAlchemy, SQLModel, or a thin direct SQLite layer

### Media

- FFmpeg
- ffprobe

### Audio analysis

- Beat This for beat/downbeat detection
- librosa / scipy / NumPy for additional features
- energy analysis using a combination of:
  - loudness / RMS
  - spectral flux
  - onset density
  - optional spectral centroid or related features

### Image generation

- ComfyUI as the initial execution environment
- Qwen Image workflow adapter
- support for reference images and reusable global style references

### Video generation

- existing Wan2GP installation
- LTX 2.3 distilled workflow
- first-frame / last-frame generation
- audio-reactive LoRA support
- Wan2GP queue generation as the initial integration path

### LLM integration

Use a provider abstraction.

Initial targets may include:

- local OpenAI-compatible server
- Ollama
- LM Studio
- llama.cpp server
- optional OpenAI provider later

The project must not depend on Codex or a coding-agent session for normal runtime operation.

---

## 7. High-Level Architecture

```text
┌──────────────────────────────────────────────┐
│                Tauri Desktop App             │
│                                              │
│  React / TypeScript                          │
│  ├─ Timeline                                 │
│  ├─ Waveform                                 │
│  ├─ Storyboard / keyframes                   │
│  ├─ Prompt editor                            │
│  ├─ Preview player                           │
│  ├─ Render queue                             │
│  └─ Settings                                 │
└──────────────────────┬───────────────────────┘
                       │
                local API / IPC
                       │
┌──────────────────────▼───────────────────────┐
│                Python Backend                │
│                                              │
│  ├─ Project service                          │
│  ├─ Audio analysis                           │
│  ├─ Creative planning                        │
│  ├─ LLM providers                            │
│  ├─ Job system                               │
│  ├─ Media service                            │
│  ├─ ComfyUI adapter                          │
│  └─ Wan2GP adapter                           │
└───────────────┬─────────────────────┬────────┘
                │                     │
                ▼                     ▼
            ComfyUI                 Wan2GP
           Qwen Image              LTX 2.3
```

---

## 8. Project Model

### 8.1 Project

A project represents one music-video production.

Suggested fields:

```ts
type Project = {
  id: string;
  name: string;
  version: number;
  createdAt: string;
  updatedAt: string;

  audioAssetId: string;
  creativeBrief: CreativeBrief;
  analysisId?: string;

  keyframeIds: string[];
  sceneIds: string[];

  settings: ProjectSettings;
};
```

### 8.2 Creative brief

```ts
type CreativeBrief = {
  concept: string;
  style: string;
  motifs?: string[];
  palette?: string[];
  narrativeArc?: string;
  negativeGuidance?: string;
};
```

For abstract projects, "narrative" means a visual or emotional trajectory rather than literal story events.

Examples:

- order → instability → fragmentation → silence → reconstruction
- organic growth → mechanical interruption → collapse → luminous rebirth

### 8.3 Scene

```ts
type Scene = {
  id: string;

  startTime: number;
  endTime: number;

  startBeatIndex?: number;
  endBeatIndex?: number;

  startKeyframeId: string;
  endKeyframeId: string;

  concept: string;

  imagePrompt: string;
  videoPrompt: string;

  visualEnergy: number;
  motionEnergy: number;

  selectedVideoTakeId?: string;
};
```

### 8.4 Keyframe

```ts
type Keyframe = {
  id: string;
  time: number;

  prompt?: string;

  variantIds: string[];
  selectedVariantId?: string;

  referenceAssetIds?: string[];
};
```

### 8.5 Keyframe variant

```ts
type KeyframeVariant = {
  id: string;
  keyframeId: string;

  assetId: string;
  prompt: string;

  backend: string;
  backendSettings: Record<string, unknown>;

  createdAt: string;
};
```

### 8.6 Video take

```ts
type VideoTake = {
  id: string;
  sceneId: string;

  assetId: string;

  prompt: string;
  backend: string;
  backendSettings: Record<string, unknown>;

  createdAt: string;
};
```

### 8.7 Audio analysis

Persist real detected timestamps rather than reconstructing the grid from BPM.

```ts
type AudioAnalysis = {
  bpmEstimate?: number;

  beats: number[];
  downbeats: number[];

  energyCurve: EnergySample[];

  sections?: AudioSection[];
};
```

---

## 9. Data Invariants

The following rules are architectural invariants and should not be violated casually.

1. A keyframe between two adjacent scenes is one shared entity.
2. Scene boundaries are explicit timeline positions.
3. Detected beat timestamps are stored as actual timestamps.
4. BPM is metadata and must not replace the real beat grid.
5. Timeline timing is authoritative.
6. Prompts remain user-editable.
7. User-edited prompts are never silently overwritten.
8. A selected render is always represented as a take/variant selection.
9. Render history is preserved unless the user explicitly deletes it.
10. Backend-specific queue formats stay inside backend adapters.
11. LLM output never directly controls arbitrary renderer node graphs.
12. All long-running work is represented as a persisted job.
13. Rendering must be resumable after an application restart when feasible.
14. The project must remain openable without any external render backend running.
15. Core editing must remain available without cloud services.

---

## 10. Audio Analysis

### 10.1 Beat grid

Beat This should provide:

- beat timestamps
- downbeat timestamps
- BPM estimate when available

The real timestamps are used for snapping.

### 10.2 Energy analysis

Energy should be represented as a normalized continuous curve.

Possible features:

- RMS / loudness
- spectral flux
- onset density
- optional spectral centroid

The first implementation should favor simple, explainable measurements over a large music-understanding model.

### 10.3 Section detection

Section detection may initially be heuristic or optional.

Possible future labels:

- intro
- build
- verse
- chorus
- drop
- bridge
- outro

Beatweave should not depend on labels being musically perfect.

### 10.4 Scene suggestions

Beatweave may propose scene boundaries using:

- downbeats
- bar structure
- energy changes
- detected section boundaries
- preferred clip lengths

The user always has final control.

---

## 11. Timeline Semantics

The timeline should support:

- waveform
- beat markers
- downbeat markers
- optional energy curve
- scene blocks
- shared keyframe boundaries
- playback head
- zoom
- horizontal scrolling
- clip resizing
- snapping
- visual selection states

Suggested snap modes:

- beat
- downbeat
- 1 bar
- 2 bars
- 4 bars
- free

Holding a modifier key should temporarily disable snapping.

The timeline should not initially support arbitrary stacked video/audio tracks.

---

## 12. Creative Planning

### 12.1 Inputs

The planning system receives:

- creative brief
- track analysis summary
- timeline scene boundaries
- per-scene energy summaries
- optional global style references

### 12.2 Responsibilities

The LLM may generate:

- project-wide visual trajectory
- section-level creative progression
- scene concepts
- image prompts
- video/motion prompts
- visual intensity suggestions
- motion intensity suggestions

### 12.3 Non-responsibilities

The LLM must not be the authority for:

- clip timing
- beat locations
- renderer node wiring
- backend-specific filenames
- database identities
- job state

### 12.4 Image prompts vs video prompts

Each scene should have separate prompt intent.

Image prompt:

> What should the scene's starting keyframe look like?

Video prompt:

> How should motion evolve from that starting keyframe toward the next boundary?

When a visual plan is generated, a scene's image prompt is copied to its start keyframe.
At a shared boundary, that means the following scene owns the prompt for the shared keyframe.

This distinction is core to Beatweave.

---

## 13. Keyframe Generation

### 13.1 Chaining model

Initial frame:

```text
KF0
```

Scene 1 generates toward:

```text
KF1
```

`KF0` uses Scene 1's image prompt. Because `KF1` is Scene 2's starting keyframe, it uses
Scene 2's image prompt while remaining the exact same shared entity as Scene 1's end keyframe.

Scene 2 begins from that exact same:

```text
KF1
```

and generates:

```text
KF2
```

The chain continues throughout the sequence.

### 13.2 Reference strategy

A keyframe generation request may include:

- previous keyframe
- global style reference
- motif reference
- palette reference
- additional user-selected references

Because Beatweave targets abstract visuals, strict character identity preservation is not a primary requirement.

Project keyframes default to 1920×1088, the nearest 32-pixel-aligned size to 1080p, so their
native aspect ratio matches the 16:9 video timeline and Qwen reference-latent dimensions remain
aligned. Backends may use another nearby 16:9 resolution only when required by the model.

Chained keyframes use light semantic reference conditioning by default. Previous-keyframe
conditioning can be disabled to create a new composition, while strong structural conditioning
is an explicit option. Keyframe seeds are randomized by default and can be locked for reproducible
variants. Reference-aware workflows must sample from the conditioning node's matching latent
output, and chained prompts must identify references with the model's native image tokens and
explicitly request compositional progress rather than a sharpened redraw of the previous frame.

### 13.3 Variants

Every keyframe can have multiple generated variants.

The timeline references the selected variant.

Regenerating a keyframe must not delete previous variants by default.

---

## 14. Video Rendering

### 14.1 Initial backend

Wan2GP is the initial video backend.

Beatweave should reuse an existing working Wan2GP installation rather than embedding LTX immediately.
The user owns the Wan2GP process lifecycle: they start it separately, and Beatweave connects to
its configurable local Gradio URL. Beatweave must not launch or terminate Wan2GP.

### 14.2 Canonical request

Beatweave should create a generic video request containing:

- scene ID
- start keyframe asset
- end keyframe asset
- project soundtrack asset and scene start time
- prompt
- duration
- frame rate
- model profile
- motion parameters
- audio-reactive LoRA parameters
- quality mode

The Wan2GP adapter converts this into the required queue format.

### 14.3 Preview vs final

Preview and final render settings should be first-class.

Preview:

- lower resolution
- lower cost
- fast iteration

Final:

- production resolution
- production parameters
- final output path

---

## 15. Job System

Long-running operations must be jobs.

Examples:

- audio analysis
- project planning
- keyframe generation
- clip rendering
- proxy generation
- final assembly

Suggested states:

```text
queued
preparing
running
complete
failed
cancelled
```

Persist:

- job type
- related project/scene/keyframe ID
- current state
- timestamps
- backend
- progress if available
- output references
- error details

The frontend should receive job events through WebSocket or equivalent push updates.

---

## 16. GPU / Resource Strategy

The initial target machine has 12 GB VRAM, so Beatweave must assume that large models cannot remain resident simultaneously.

Model execution should be sequential where needed:

```text
local LLM
   ↓ unload / release
Qwen Image
   ↓ unload / release
LTX / Wan2GP
```

The application should not make assumptions that all services share one Python process.

Backend processes may own their own memory management.

Beatweave should expose backend availability and errors clearly without making the project unusable.

---

## 17. Project Storage

Suggested project folder:

```text
MyBeatweaveProject/
├─ project.db
├─ source/
│  └─ song.wav
├─ references/
├─ keyframes/
├─ previews/
├─ renders/
├─ cache/
└─ exports/
```

Use SQLite for structured metadata.

Store media as files.

Do not store large binary media blobs inside SQLite.

The application may support exporting a portable JSON manifest for debugging, migration, or interoperability.

---

## 18. Media Service

FFmpeg/ffprobe should be wrapped behind one service.

Responsibilities may include:

- probing media
- waveform/proxy preparation
- audio conversion
- frame extraction
- preview generation
- clip concatenation
- audio muxing
- final export

Do not scatter raw FFmpeg subprocess commands throughout the codebase.

---

## 19. LLM Provider Interface

Use a provider abstraction.

Example conceptual interface:

```ts
interface LLMProvider {
  generateStructured<T>(
    request: StructuredGenerationRequest<T>
  ): Promise<T>;
}
```

The rest of the app should not care whether the provider is:

- local llama.cpp
- LM Studio
- Ollama
- another OpenAI-compatible local endpoint
- optional OpenAI cloud integration

Structured output should be validated before being committed to project state.

---

## 20. Backend Interfaces

Conceptual image renderer:

```ts
interface ImageBackend {
  submit(request: ImageRenderRequest): Promise<JobId>;
  cancel(jobId: JobId): Promise<void>;
}
```

Conceptual video renderer:

```ts
interface VideoBackend {
  submit(request: VideoRenderRequest): Promise<JobId>;
  cancel(jobId: JobId): Promise<void>;
}
```

Status should be represented by the central job system rather than backend-specific frontend state.

---

## 21. Failure and Recovery

Beatweave should assume external renderers can fail.

Requirements:

- Save project changes frequently.
- Persist job state.
- Preserve failed-job error messages.
- Allow retrying a render without rebuilding a scene.
- Never delete the previously selected successful take when a new render fails.
- Detect unavailable ComfyUI or Wan2GP cleanly.
- Let users continue non-rendering work while a backend is offline.

---

## 22. Future MCP Surface

Beatweave may eventually expose an MCP server so Codex or another agent can control the application.

Possible tools:

```text
create_project
analyze_track
get_timeline
generate_visual_plan
get_scenes
update_scene
render_keyframe
render_scene
select_take
export_project
```

The Beatweave application remains the source of truth.

MCP is an optional control surface, not the core architecture.

---

## 23. Suggested Repository Layout

```text
beatweave/
├─ AGENTS.md
├─ DESIGN.md
├─ PLAN.md
│
├─ app/
│  ├─ src/
│  │  ├─ timeline/
│  │  ├─ waveform/
│  │  ├─ storyboard/
│  │  ├─ prompts/
│  │  ├─ player/
│  │  ├─ jobs/
│  │  └─ settings/
│  └─ src-tauri/
│
├─ backend/
│  ├─ api/
│  ├─ analysis/
│  ├─ planning/
│  ├─ llm/
│  ├─ rendering/
│  ├─ media/
│  ├─ jobs/
│  ├─ project/
│  └─ tests/
│
├─ shared/
│  └─ schemas/
│
└─ scripts/
```

The exact structure may evolve. Maintain the architectural boundaries even if directory names change.

---

## 24. Definition of a Successful V1

Beatweave V1 is successful when a user can:

1. Create a project.
2. Import a song.
3. Analyze beats/downbeats and energy.
4. View the waveform and beat grid.
5. Create and edit beat-snapped scene boundaries.
6. Enter a creative brief.
7. Generate a scene-level visual plan and editable prompts.
8. Generate chained keyframes.
9. Generate video clips between adjacent keyframes.
10. Preview generated clips in the timeline.
11. Create multiple takes and choose preferred ones.
12. Re-render individual scenes without disturbing the rest of the project.
13. Save, close, and reopen the project.
14. Export or assemble the selected sequence.

Anything beyond that is secondary to making this workflow pleasant and reliable.
