# Beatweave — Implementation Plan

This file is the execution checklist for Beatweave.

## Working Rules

- Tasks are completed in phase order unless a dependency requires otherwise.
- Do not mark a task complete until the implementation has been verified.
- Keep tasks small and focused.
- Update this file as work progresses.
- If implementation reveals that a task must change, update the wording rather than leaving the checklist inaccurate.
- Avoid starting large later-phase features before the current foundation is stable.
- When stopping a development session, leave the repository in a buildable/testable state whenever possible.

---

# Phase 0 — Repository and Tooling

## Goal

Create a clean repository that coding agents can understand and resume easily.

- [x] Create repository structure based on `DESIGN.md`.
- [x] Add `.gitignore`.
- [x] Add frontend formatting configuration.
- [x] Add frontend linting configuration.
- [x] Add Python formatting configuration.
- [x] Add Python linting configuration.
- [x] Add test commands for frontend and backend.
- [x] Add root-level development commands or scripts.
- [x] Document prerequisites in `README.md`.
- [x] Add a minimal `PROJECT_STATE.md` describing the current milestone and next task.
- [x] Verify a fresh clone can install dependencies using documented steps.

### Acceptance criteria

- Frontend lint/check command passes.
- Backend lint/check command passes.
- Test commands run even if the suites are initially empty.
- `README.md` contains enough information to start development.

---

# Phase 1 — Application Foundation

## Goal

Launch Beatweave as a desktop app with a functioning Python backend and persistent project database.

### Desktop shell

- [x] Create Tauri 2 application.
- [x] Create React + TypeScript frontend.
- [x] Create base application layout.
- [x] Add top-level navigation or workspace shell.
- [x] Add global error boundary.
- [x] Add basic application logging.

### Python backend

- [x] Create Python backend package.
- [x] Add FastAPI application.
- [x] Add `/health` endpoint.
- [x] Add backend logging.
- [x] Add structured error response model.
- [x] Add backend configuration model.
- [x] Launch backend automatically with the desktop app.
- [x] Shut backend down when the desktop app exits.
- [x] Detect and report backend startup failure.

### Frontend/backend communication

- [x] Add typed frontend API client.
- [x] Add backend connectivity status.
- [x] Add WebSocket event connection skeleton.
- [x] Display backend connection failure in the UI.

### Database

- [x] Add SQLite database.
- [x] Add schema migration mechanism.
- [x] Create initial project table.
- [x] Create application settings table.
- [x] Add database initialization on startup.

### Verification

- [x] Create a smoke test that launches or exercises the backend.
- [x] Verify the frontend can call `/health`.
- [x] Verify database creation on first launch.
- [x] Verify the app can restart without corrupting the database.

---

# Phase 2 — Project System

## Goal

Create, open, save, and reopen Beatweave projects.

### Project model

- [x] Implement canonical `Project` model.
- [x] Implement `CreativeBrief` model.
- [x] Implement asset metadata model.
- [x] Add project version field.
- [x] Add project creation timestamps.
- [x] Add project update timestamps.

### Project filesystem

- [x] Define project directory layout.
- [x] Create project folder on project creation.
- [x] Create `source/`.
- [x] Create `references/`.
- [x] Create `keyframes/`.
- [x] Create `previews/`.
- [x] Create `renders/`.
- [x] Create `cache/`.
- [x] Create `exports/`.

### Project API

- [x] Create project.
- [x] List recent projects.
- [x] Open project.
- [x] Close project.
- [x] Update project metadata.
- [x] Handle missing project files gracefully.

### UI

- [x] Add project launcher.
- [x] Add "New Project".
- [x] Add "Open Project".
- [x] Add recent-project list.
- [x] Display current project name.
- [x] Add unsaved/error state indicators if needed.

### Verification

- [x] Create a project.
- [x] Close Beatweave.
- [x] Reopen Beatweave.
- [x] Reopen the project successfully.
- [x] Confirm project folder structure is preserved.

---

# Phase 3 — Audio Import and Media Service

## Goal

Import a song and establish the media-processing foundation.

### Media service

- [x] Add ffprobe wrapper.
- [x] Add FFmpeg execution wrapper.
- [x] Centralize subprocess error handling.
- [x] Add media metadata model.
- [x] Add audio duration extraction.
- [x] Add sample rate/channel metadata extraction.

### Audio import

- [x] Add audio file picker.
- [x] Copy or register source audio in the project.
- [x] Prevent accidental source overwrite.
- [x] Store audio asset metadata in SQLite.
- [x] Display track duration.

### Waveform cache

- [x] Generate waveform data suitable for timeline rendering.
- [x] Cache generated waveform data.
- [x] Avoid regenerating unchanged waveform data.
- [x] Load cached waveform data on project reopen.

### Playback

- [x] Add audio playback.
- [x] Add play/pause.
- [x] Add seek.
- [x] Add playback position updates.
- [x] Add current-time display.

### Verification

- [x] Import at least two common audio formats.
- [x] Confirm waveform cache is reused.
- [x] Confirm playback remains in sync after seeking.

---

# Phase 4 — Beat and Energy Analysis

## Goal

Analyze musical timing and expose the results as reliable project data.

### Beat This integration

- [x] Add Beat This dependency or integration.
- [x] Run beat detection on imported track.
- [x] Store actual beat timestamps.
- [x] Store actual downbeat timestamps.
- [x] Store BPM estimate.
- [x] Persist analysis results.
- [x] Cache analysis based on source audio identity.

### Energy analysis

- [x] Compute RMS/loudness envelope.
- [x] Compute spectral flux.
- [x] Compute onset-density feature.
- [x] Normalize energy measurements.
- [x] Produce a continuous combined energy curve.
- [x] Store analysis parameters used.
- [x] Persist energy curve.

### Analysis API

- [x] Add start-analysis endpoint.
- [x] Execute analysis as a persisted job.
- [x] Report analysis progress.
- [x] Report analysis failures.
- [x] Re-run analysis on demand.

### UI

- [x] Add "Analyze Track" action.
- [x] Display BPM estimate.
- [x] Display detected beat count.
- [x] Display analysis progress.
- [x] Display analysis failure details.

### Verification

- [x] Confirm detected beat timestamps are not reconstructed from BPM.
- [x] Confirm beat/downbeat arrays survive project reopen.
- [x] Confirm energy values are normalized and bounded.
- [x] Test on at least three tracks with different tempos.

---

# Phase 5 — Timeline V1

## Goal

Create the primary Beatweave workspace.

### Timeline foundation

- [x] Define timeline coordinate transform.
- [x] Implement time-to-X mapping.
- [x] Implement X-to-time mapping.
- [x] Add horizontal scrolling.
- [x] Add zooming.
- [x] Add playback head.
- [x] Sync playback head to audio position.

### Musical overlays

- [x] Render waveform.
- [x] Render beat markers.
- [x] Render downbeat markers.
- [x] Render energy curve overlay.
- [x] Add visibility toggles for overlays.

### Scene model

- [x] Implement `Scene` model.
- [x] Implement `Keyframe` model.
- [x] Enforce shared keyframe invariant between adjacent scenes.
- [x] Add scene persistence.
- [x] Add keyframe persistence.

### Scene editing

- [x] Create scene.
- [x] Delete scene.
- [x] Resize scene boundary.
- [x] Move scene boundary.
- [x] Keep adjacent scenes contiguous where required.
- [x] Prevent invalid negative-duration scenes.

### Snapping

- [x] Snap boundaries to beat timestamps.
- [x] Snap boundaries to downbeats.
- [x] Add bar-based snap modes if bar information is available.
- [x] Add free mode.
- [x] Add temporary modifier to disable snapping.
- [x] Visually indicate the active snap target.

### Selection

- [x] Select scene.
- [x] Select keyframe.
- [x] Show selected scene metadata.
- [x] Show selected keyframe metadata.

### Verification

- [x] Dragging a boundary snaps to a real detected beat.
- [x] Disabling snapping allows free placement.
- [x] Playback head remains aligned while zooming.
- [x] Reopening the project restores scene timing exactly.

---

# Phase 6 — Suggested Scene Layout

## Goal

Generate useful empty clip layouts from musical structure while keeping the user in control.

### Scene suggestion engine

- [x] Define default preferred clip lengths.
- [x] Use downbeats as preferred boundaries.
- [x] Incorporate energy changes.
- [x] Incorporate track start/end.
- [x] Optionally incorporate detected sections.
- [x] Produce a proposed list of scene boundaries.
- [x] Keep proposal deterministic for identical settings.

### UI

- [x] Add "Suggest Layout".
- [x] Preview suggested boundaries before applying.
- [x] Apply suggested layout.
- [x] Restore previous layout using undo.
- [x] Allow user editing after application.

### Verification

- [x] Suggested scenes always cover the intended song range.
- [x] No zero-length scenes are produced.
- [x] Boundaries land on valid timeline positions.
- [x] Applying a suggestion creates correct shared keyframes.

---

# Phase 7 — Undo / Redo and Editing Reliability

## Goal

Make timeline experimentation safe.

- [x] Design command/history model.
- [x] Add undo for scene boundary changes.
- [x] Add redo for scene boundary changes.
- [x] Add undo for scene create/delete.
- [x] Add undo for prompt edits where practical.
- [x] Add keyboard shortcuts.
- [x] Define history invalidation rules.
- [x] Prevent render-job events from polluting user edit history.

### Verification

- [x] Repeated undo/redo restores exact timing state.
- [x] Shared-keyframe invariant survives undo/redo.
- [x] Project remains valid after undoing scene deletion.

---

# Phase 8 — Creative Brief and Visual Arc

## Goal

Let the user describe the video's global artistic direction.

### Models

- [x] Finalize `CreativeBrief`.
- [x] Add visual trajectory model.
- [x] Add optional motif list.
- [x] Add optional palette list.
- [x] Add negative guidance field.
- [x] Add global style-reference asset support.

### UI

- [x] Add creative brief editor.
- [x] Add style field.
- [x] Add concept field.
- [x] Add narrative/visual arc field.
- [x] Add reference-image import.
- [x] Add reference-image gallery.

### Verification

- [x] Brief edits persist.
- [x] Reference assets survive reopen.
- [x] Removing a reference does not delete an externally owned source file.

---

# Phase 9 — LLM Provider Layer

## Goal

Add model-independent structured creative planning.

### Provider abstraction

- [ ] Define `LLMProvider` interface.
- [ ] Define structured generation request.
- [ ] Define structured generation response.
- [ ] Add timeout handling.
- [ ] Add provider availability test.
- [ ] Add provider configuration persistence.

### Local provider

- [ ] Support an OpenAI-compatible local endpoint.
- [ ] Allow base URL configuration.
- [ ] Allow model-name configuration.
- [ ] Add connection test.
- [ ] Add request logging without leaking sensitive credentials.

### Structured output

- [ ] Define visual-plan schema.
- [ ] Define scene-plan schema.
- [ ] Validate LLM output with Pydantic.
- [ ] Reject malformed output safely.
- [ ] Support repair/retry strategy for invalid structured responses.
- [ ] Never commit invalid output to project state.

### Verification

- [ ] Provider can be changed without timeline changes.
- [ ] Invalid JSON does not corrupt the project.
- [ ] App remains usable with provider offline.

---

# Phase 10 — Project-Level Visual Planning

## Goal

Generate a coherent abstract visual trajectory across the track.

### Context construction

- [ ] Summarize track-level analysis.
- [ ] Summarize timeline scene boundaries.
- [ ] Calculate per-scene energy summaries.
- [ ] Include global creative brief.
- [ ] Include relevant style-reference metadata.

### Planning

- [ ] Generate global visual trajectory.
- [ ] Generate per-scene concepts.
- [ ] Generate visual-intensity values.
- [ ] Generate motion-intensity values.
- [ ] Generate image prompts.
- [ ] Generate video prompts.
- [ ] Preserve scene timing from the timeline.
- [ ] Never allow LLM output to create arbitrary renderer graphs.

### UI

- [ ] Add "Generate Visual Plan".
- [ ] Show generated global trajectory.
- [ ] Show scene concepts in inspector.
- [ ] Show editable image prompt.
- [ ] Show editable video prompt.
- [ ] Add per-scene regenerate action.
- [ ] Add explicit confirmation before overwriting edited prompts.

### Verification

- [ ] User timing is unchanged after planning.
- [ ] Prompts remain editable.
- [ ] Regenerating one scene leaves other scenes untouched.

---

# Phase 11 — Job System

## Goal

Create durable infrastructure for long-running operations before image/video rendering.

### Persistence

- [ ] Implement job database table.
- [ ] Implement job type.
- [ ] Implement job state.
- [ ] Store related project/entity IDs.
- [ ] Store backend identifier.
- [ ] Store timestamps.
- [ ] Store output metadata.
- [ ] Store error details.

### Execution

- [ ] Add backend worker loop.
- [ ] Add queued state.
- [ ] Add preparing state.
- [ ] Add running state.
- [ ] Add complete state.
- [ ] Add failed state.
- [ ] Add cancelled state.
- [ ] Add cancellation request mechanism.

### Events

- [ ] Publish job-created event.
- [ ] Publish job-progress event.
- [ ] Publish job-complete event.
- [ ] Publish job-failed event.
- [ ] Reconnect frontend event stream after temporary disconnect.

### Recovery

- [ ] Define behavior for jobs left "running" after app crash.
- [ ] Reconcile jobs on startup.
- [ ] Preserve output produced before app restart where detectable.

### Verification

- [ ] Simulate a failed job.
- [ ] Simulate app restart with queued jobs.
- [ ] Confirm failure details remain inspectable.

---

# Phase 12 — ComfyUI Backend

## Goal

Connect Beatweave to a running ComfyUI instance without leaking ComfyUI-specific details into the core project model.

### Connectivity

- [ ] Add ComfyUI backend configuration.
- [ ] Add ComfyUI health check.
- [ ] Detect unavailable ComfyUI.
- [ ] Display backend status in settings.

### Workflow configuration

- [ ] Define Qwen workflow profile configuration.
- [ ] Load workflow template.
- [ ] Map canonical request fields into workflow inputs.
- [ ] Keep node IDs inside the adapter/profile.
- [ ] Validate required workflow inputs before submission.

### Execution

- [ ] Submit workflow.
- [ ] Track prompt/job ID.
- [ ] Detect completion.
- [ ] Detect failure.
- [ ] Retrieve generated image output.
- [ ] Copy/register image into project storage.

### Verification

- [ ] Generate one test image through ComfyUI.
- [ ] Restart Beatweave without restarting ComfyUI and reconnect.
- [ ] Handle ComfyUI being offline gracefully.

---

# Phase 13 — Keyframe Generation

## Goal

Generate and manage chained visual endpoints.

### Data model

- [ ] Implement `KeyframeVariant`.
- [ ] Persist generation prompt.
- [ ] Persist backend settings.
- [ ] Persist source/reference assets.
- [ ] Support selected variant.

### Generation flow

- [ ] Generate initial keyframe.
- [ ] Generate next keyframe using previous selected keyframe.
- [ ] Include global style reference when configured.
- [ ] Include optional additional references.
- [ ] Store output as a variant.
- [ ] Do not delete old variants.

### UI

- [ ] Display selected keyframe image on timeline.
- [ ] Display keyframe variants.
- [ ] Generate new variant.
- [ ] Select a variant.
- [ ] Compare variants.
- [ ] Open keyframe file location.
- [ ] Show render failure details.

### Dependency handling

- [ ] Warn when changing a keyframe used by already-rendered adjacent scenes.
- [ ] Mark affected video takes stale when appropriate.
- [ ] Do not automatically delete stale renders.

### Verification

- [ ] Confirm one shared keyframe drives both adjacent scenes.
- [ ] Switching variants updates both adjacent scene references.
- [ ] Previously generated variants remain accessible.

---

# Phase 14 — Wan2GP Backend

## Goal

Reuse the existing Wan2GP installation for LTX video rendering.

### Configuration

- [ ] Add Wan2GP installation-path setting.
- [ ] Validate configured installation.
- [ ] Define LTX 2.3 distilled render profile.
- [ ] Define audio-reactive LoRA profile.
- [ ] Store configurable defaults separately from project scenes.

### Queue generation

- [ ] Define canonical `VideoRenderRequest`.
- [ ] Map canonical request to Wan2GP queue format.
- [ ] Generate valid queue data.
- [ ] Generate `queue.zip`.
- [ ] Keep queue-format details inside Wan2GP adapter.
- [ ] Include first frame.
- [ ] Include last frame.
- [ ] Include video prompt.
- [ ] Include duration/frame count.
- [ ] Include audio-reactive LoRA trigger/settings.

### Execution

- [ ] Decide and implement initial submission strategy:
  - [ ] automated submission if reliably supported, or
  - [ ] controlled queue export/import workflow.
- [ ] Detect or watch render output.
- [ ] Associate output with originating scene/job.
- [ ] Register completed video in project storage.

### Verification

- [ ] Render one known-good LTX clip through the existing Wan2GP setup.
- [ ] Confirm Beatweave correctly associates the result with its scene.
- [ ] Confirm queue details are not stored as canonical scene data.

---

# Phase 15 — Video Takes

## Goal

Make iterative scene rendering pleasant.

### Data model

- [ ] Implement `VideoTake`.
- [ ] Store prompt snapshot.
- [ ] Store backend profile/settings.
- [ ] Store output asset.
- [ ] Support selected take.

### UI

- [ ] Render scene preview.
- [ ] Render scene final.
- [ ] Display take list.
- [ ] Select preferred take.
- [ ] Delete unwanted take with confirmation.
- [ ] Preserve selected take while another render is running.
- [ ] Show stale status when keyframes/prompt changed.

### Verification

- [ ] Generate at least two takes for one scene.
- [ ] Switch selected take without rerendering.
- [ ] Failed third take does not remove previous successful takes.

---

# Phase 16 — Timeline Video Preview

## Goal

Preview generated scenes in context.

- [ ] Add video asset thumbnails.
- [ ] Add selected-take indicator.
- [ ] Add scene render-state indicator.
- [ ] Add clip preview player.
- [ ] Seek from timeline into video preview.
- [ ] Handle missing/unrendered clips.
- [ ] Handle stale clips visually.
- [ ] Play consecutive selected scene takes in timeline order if practical.
- [ ] Keep original audio as the master playback track.

### Verification

- [ ] User can inspect rendered clips without leaving Beatweave.
- [ ] Timeline clearly distinguishes unrendered, rendering, complete, failed, and stale clips.

---

# Phase 17 — Preview / Final Quality Profiles

## Goal

Support fast iteration on limited VRAM.

### Profiles

- [ ] Define image-preview profile.
- [ ] Define image-final profile.
- [ ] Define video-preview profile.
- [ ] Define video-final profile.
- [ ] Make profiles configurable.
- [ ] Keep project-level selection separate from backend internals.

### UI

- [ ] Add preview render action.
- [ ] Add final render action.
- [ ] Clearly label output quality.
- [ ] Allow rerendering final from an approved preview.

### Verification

- [ ] Preview outputs are stored separately from final outputs.
- [ ] Changing a profile does not mutate previously rendered take metadata.

---

# Phase 18 — Final Assembly and Export

## Goal

Produce a final video using selected scene takes.

### Validation

- [ ] Detect scenes with no selected take.
- [ ] Detect stale selected takes.
- [ ] Detect duration mismatches.
- [ ] Detect missing media.
- [ ] Display export readiness report.

### Assembly

- [ ] Build ordered selected-take list.
- [ ] Normalize required media properties.
- [ ] Concatenate clips.
- [ ] Mux original track.
- [ ] Preserve expected duration.
- [ ] Write final output to `exports/`.

### Export options

- [ ] Add final export action.
- [ ] Add output filename control.
- [ ] Add basic codec/profile configuration.
- [ ] Show export job progress.
- [ ] Open completed export location.

### Verification

- [ ] Assemble a multi-scene test project.
- [ ] Confirm audio sync.
- [ ] Confirm scene order.
- [ ] Confirm output duration is correct.

---

# Phase 19 — Reliability and Project Recovery

## Goal

Make Beatweave safe for long creative sessions.

- [ ] Add periodic safe persistence where appropriate.
- [ ] Add database backup strategy.
- [ ] Detect incomplete project migration.
- [ ] Add migration tests.
- [ ] Add missing-file diagnostics.
- [ ] Add backend-offline diagnostics.
- [ ] Add job retry action.
- [ ] Add project integrity check.
- [ ] Add structured application log viewer or export.

### Verification

- [ ] Force-close app during normal editing and reopen.
- [ ] Force a backend failure during render.
- [ ] Confirm previously successful media remains intact.
- [ ] Confirm project integrity diagnostics identify missing assets.

---

# Phase 20 — UX Polish

## Goal

Make the application feel like a creative tool rather than a technical demo.

- [ ] Keyboard shortcut pass.
- [ ] Context-menu pass.
- [ ] Timeline interaction polish.
- [ ] Drag threshold polish.
- [ ] Snap feedback polish.
- [ ] Loading-state polish.
- [ ] Empty-state polish.
- [ ] Error-message polish.
- [ ] Settings organization pass.
- [ ] Render queue usability pass.
- [ ] Variant/take comparison usability pass.
- [ ] Add tooltips for non-obvious controls.
- [ ] Add first-run setup guidance.
- [ ] Add backend connectivity/setup screen.

---

# Phase 21 — Packaging

## Goal

Make Beatweave straightforward to launch on the target Windows machine.

- [ ] Produce Windows development build.
- [ ] Produce Windows release build.
- [ ] Bundle or verify required FFmpeg strategy.
- [ ] Define Python runtime/dependency strategy.
- [ ] Validate path handling with spaces.
- [ ] Validate non-admin installation/run where practical.
- [ ] Validate startup with ComfyUI offline.
- [ ] Validate startup with Wan2GP offline.
- [ ] Document external backend setup.
- [ ] Document local LLM setup.

---

# Phase 22 — Optional MCP Control Surface

## Goal

Allow Codex or other MCP clients to control Beatweave without making MCP part of the core runtime.

Do not begin this phase until the normal Beatweave UI workflow is stable.

- [ ] Define read-only project MCP tools.
- [ ] Add `get_project`.
- [ ] Add `get_timeline`.
- [ ] Add `get_scenes`.
- [ ] Add `get_jobs`.
- [ ] Define safe mutation tools.
- [ ] Add `update_scene`.
- [ ] Add `generate_visual_plan`.
- [ ] Add `render_keyframe`.
- [ ] Add `render_scene`.
- [ ] Add `select_take`.
- [ ] Add `export_project`.
- [ ] Ensure all mutations use the same application services as the UI.
- [ ] Add clear MCP error responses.
- [ ] Add MCP integration tests.

---

# V1 Completion Checklist

Beatweave V1 is complete when all of the following are true:

- [ ] A user can create and reopen a project.
- [ ] A user can import and play a song.
- [ ] Beatweave detects and stores beats/downbeats.
- [ ] Beatweave computes and displays an energy curve.
- [ ] The timeline shows waveform, beats, scenes, and shared keyframes.
- [ ] Scene boundaries can be edited with beat snapping.
- [ ] Beatweave can suggest an initial scene layout.
- [ ] A user can enter a global creative brief.
- [ ] An LLM can generate editable per-scene concepts and prompts.
- [ ] Beatweave can generate chained keyframes through ComfyUI.
- [ ] Keyframes support multiple selectable variants.
- [ ] Beatweave can generate first/last-frame video through Wan2GP.
- [ ] Video scenes support multiple selectable takes.
- [ ] Render jobs are persisted and recoverable.
- [ ] Generated clips can be previewed from the timeline.
- [ ] Individual scenes can be regenerated without rebuilding the whole project.
- [ ] The selected sequence can be assembled with the source song.
- [ ] The final video can be exported.
