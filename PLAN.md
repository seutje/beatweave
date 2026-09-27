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

- [ ] Create Tauri 2 application.
- [ ] Create React + TypeScript frontend.
- [ ] Create base application layout.
- [ ] Add top-level navigation or workspace shell.
- [ ] Add global error boundary.
- [ ] Add basic application logging.

### Python backend

- [ ] Create Python backend package.
- [ ] Add FastAPI application.
- [ ] Add `/health` endpoint.
- [ ] Add backend logging.
- [ ] Add structured error response model.
- [ ] Add backend configuration model.
- [ ] Launch backend automatically with the desktop app.
- [ ] Shut backend down when the desktop app exits.
- [ ] Detect and report backend startup failure.

### Frontend/backend communication

- [ ] Add typed frontend API client.
- [ ] Add backend connectivity status.
- [ ] Add WebSocket event connection skeleton.
- [ ] Display backend connection failure in the UI.

### Database

- [ ] Add SQLite database.
- [ ] Add schema migration mechanism.
- [ ] Create initial project table.
- [ ] Create application settings table.
- [ ] Add database initialization on startup.

### Verification

- [ ] Create a smoke test that launches or exercises the backend.
- [ ] Verify the frontend can call `/health`.
- [ ] Verify database creation on first launch.
- [ ] Verify the app can restart without corrupting the database.

---

# Phase 2 — Project System

## Goal

Create, open, save, and reopen Beatweave projects.

### Project model

- [ ] Implement canonical `Project` model.
- [ ] Implement `CreativeBrief` model.
- [ ] Implement asset metadata model.
- [ ] Add project version field.
- [ ] Add project creation timestamps.
- [ ] Add project update timestamps.

### Project filesystem

- [ ] Define project directory layout.
- [ ] Create project folder on project creation.
- [ ] Create `source/`.
- [ ] Create `references/`.
- [ ] Create `keyframes/`.
- [ ] Create `previews/`.
- [ ] Create `renders/`.
- [ ] Create `cache/`.
- [ ] Create `exports/`.

### Project API

- [ ] Create project.
- [ ] List recent projects.
- [ ] Open project.
- [ ] Close project.
- [ ] Update project metadata.
- [ ] Handle missing project files gracefully.

### UI

- [ ] Add project launcher.
- [ ] Add "New Project".
- [ ] Add "Open Project".
- [ ] Add recent-project list.
- [ ] Display current project name.
- [ ] Add unsaved/error state indicators if needed.

### Verification

- [ ] Create a project.
- [ ] Close Beatweave.
- [ ] Reopen Beatweave.
- [ ] Reopen the project successfully.
- [ ] Confirm project folder structure is preserved.

---

# Phase 3 — Audio Import and Media Service

## Goal

Import a song and establish the media-processing foundation.

### Media service

- [ ] Add ffprobe wrapper.
- [ ] Add FFmpeg execution wrapper.
- [ ] Centralize subprocess error handling.
- [ ] Add media metadata model.
- [ ] Add audio duration extraction.
- [ ] Add sample rate/channel metadata extraction.

### Audio import

- [ ] Add audio file picker.
- [ ] Copy or register source audio in the project.
- [ ] Prevent accidental source overwrite.
- [ ] Store audio asset metadata in SQLite.
- [ ] Display track duration.

### Waveform cache

- [ ] Generate waveform data suitable for timeline rendering.
- [ ] Cache generated waveform data.
- [ ] Avoid regenerating unchanged waveform data.
- [ ] Load cached waveform data on project reopen.

### Playback

- [ ] Add audio playback.
- [ ] Add play/pause.
- [ ] Add seek.
- [ ] Add playback position updates.
- [ ] Add current-time display.

### Verification

- [ ] Import at least two common audio formats.
- [ ] Confirm waveform cache is reused.
- [ ] Confirm playback remains in sync after seeking.

---

# Phase 4 — Beat and Energy Analysis

## Goal

Analyze musical timing and expose the results as reliable project data.

### Beat This integration

- [ ] Add Beat This dependency or integration.
- [ ] Run beat detection on imported track.
- [ ] Store actual beat timestamps.
- [ ] Store actual downbeat timestamps.
- [ ] Store BPM estimate.
- [ ] Persist analysis results.
- [ ] Cache analysis based on source audio identity.

### Energy analysis

- [ ] Compute RMS/loudness envelope.
- [ ] Compute spectral flux.
- [ ] Compute onset-density feature.
- [ ] Normalize energy measurements.
- [ ] Produce a continuous combined energy curve.
- [ ] Store analysis parameters used.
- [ ] Persist energy curve.

### Analysis API

- [ ] Add start-analysis endpoint.
- [ ] Execute analysis as a persisted job.
- [ ] Report analysis progress.
- [ ] Report analysis failures.
- [ ] Re-run analysis on demand.

### UI

- [ ] Add "Analyze Track" action.
- [ ] Display BPM estimate.
- [ ] Display detected beat count.
- [ ] Display analysis progress.
- [ ] Display analysis failure details.

### Verification

- [ ] Confirm detected beat timestamps are not reconstructed from BPM.
- [ ] Confirm beat/downbeat arrays survive project reopen.
- [ ] Confirm energy values are normalized and bounded.
- [ ] Test on at least three tracks with different tempos.

---

# Phase 5 — Timeline V1

## Goal

Create the primary Beatweave workspace.

### Timeline foundation

- [ ] Define timeline coordinate transform.
- [ ] Implement time-to-X mapping.
- [ ] Implement X-to-time mapping.
- [ ] Add horizontal scrolling.
- [ ] Add zooming.
- [ ] Add playback head.
- [ ] Sync playback head to audio position.

### Musical overlays

- [ ] Render waveform.
- [ ] Render beat markers.
- [ ] Render downbeat markers.
- [ ] Render energy curve overlay.
- [ ] Add visibility toggles for overlays.

### Scene model

- [ ] Implement `Scene` model.
- [ ] Implement `Keyframe` model.
- [ ] Enforce shared keyframe invariant between adjacent scenes.
- [ ] Add scene persistence.
- [ ] Add keyframe persistence.

### Scene editing

- [ ] Create scene.
- [ ] Delete scene.
- [ ] Resize scene boundary.
- [ ] Move scene boundary.
- [ ] Keep adjacent scenes contiguous where required.
- [ ] Prevent invalid negative-duration scenes.

### Snapping

- [ ] Snap boundaries to beat timestamps.
- [ ] Snap boundaries to downbeats.
- [ ] Add bar-based snap modes if bar information is available.
- [ ] Add free mode.
- [ ] Add temporary modifier to disable snapping.
- [ ] Visually indicate the active snap target.

### Selection

- [ ] Select scene.
- [ ] Select keyframe.
- [ ] Show selected scene metadata.
- [ ] Show selected keyframe metadata.

### Verification

- [ ] Dragging a boundary snaps to a real detected beat.
- [ ] Disabling snapping allows free placement.
- [ ] Playback head remains aligned while zooming.
- [ ] Reopening the project restores scene timing exactly.

---

# Phase 6 — Suggested Scene Layout

## Goal

Generate useful empty clip layouts from musical structure while keeping the user in control.

### Scene suggestion engine

- [ ] Define default preferred clip lengths.
- [ ] Use downbeats as preferred boundaries.
- [ ] Incorporate energy changes.
- [ ] Incorporate track start/end.
- [ ] Optionally incorporate detected sections.
- [ ] Produce a proposed list of scene boundaries.
- [ ] Keep proposal deterministic for identical settings.

### UI

- [ ] Add "Suggest Layout".
- [ ] Preview suggested boundaries before applying.
- [ ] Apply suggested layout.
- [ ] Restore previous layout using undo.
- [ ] Allow user editing after application.

### Verification

- [ ] Suggested scenes always cover the intended song range.
- [ ] No zero-length scenes are produced.
- [ ] Boundaries land on valid timeline positions.
- [ ] Applying a suggestion creates correct shared keyframes.

---

# Phase 7 — Undo / Redo and Editing Reliability

## Goal

Make timeline experimentation safe.

- [ ] Design command/history model.
- [ ] Add undo for scene boundary changes.
- [ ] Add redo for scene boundary changes.
- [ ] Add undo for scene create/delete.
- [ ] Add undo for prompt edits where practical.
- [ ] Add keyboard shortcuts.
- [ ] Define history invalidation rules.
- [ ] Prevent render-job events from polluting user edit history.

### Verification

- [ ] Repeated undo/redo restores exact timing state.
- [ ] Shared-keyframe invariant survives undo/redo.
- [ ] Project remains valid after undoing scene deletion.

---

# Phase 8 — Creative Brief and Visual Arc

## Goal

Let the user describe the video's global artistic direction.

### Models

- [ ] Finalize `CreativeBrief`.
- [ ] Add visual trajectory model.
- [ ] Add optional motif list.
- [ ] Add optional palette list.
- [ ] Add negative guidance field.
- [ ] Add global style-reference asset support.

### UI

- [ ] Add creative brief editor.
- [ ] Add style field.
- [ ] Add concept field.
- [ ] Add narrative/visual arc field.
- [ ] Add reference-image import.
- [ ] Add reference-image gallery.

### Verification

- [ ] Brief edits persist.
- [ ] Reference assets survive reopen.
- [ ] Removing a reference does not delete an externally owned source file.

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
