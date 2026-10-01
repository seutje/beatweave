# Beatweave — Project State

## Current Phase

Phase 19 — Recovery and Resilience

## Completed This Session

- Initial product architecture documented in `DESIGN.md`.
- Initial phased implementation plan created in `PLAN.md`.
- Coding-agent workflow documented in `AGENTS.md`.
- Phase 0 repository structure and reproducible frontend/backend tooling completed.
- Added locked dependency installation, formatting, linting, type-checking, and test commands.
- Phase 1 application foundation completed with Tauri 2, React/TypeScript, and FastAPI.
- Added lifecycle-managed backend startup/shutdown, typed health API, reconnecting event socket, and visible connectivity state.
- Added SQLite initialization and Alembic migrations for projects and application settings.
- Added the initial design-aligned workspace shell and application icon.
- Phase 2 project system completed with portable, versioned per-project SQLite databases.
- Added project creation/open/close/update APIs, recent-project registry, native folder pickers, and launcher/overview UI.
- Project creation builds `source/`, `references/`, `keyframes/`, `previews/`, `renders/`, `cache/`, and `exports/` without overwriting existing paths.
- Phase 3 media foundation completed with centralized FFmpeg/ffprobe execution and structured failures.
- Added hashed audio import, SQLite asset metadata, waveform cache, byte-range media delivery, and React playback controls.
- Phase 4 beat/downbeat and energy analysis completed using the official Beat This adapter.
- Analysis runs as persisted project jobs with progress, failure details, source-hash caching, and forced reruns.
- Stored analysis includes real timestamp arrays, BPM metadata, normalized RMS/spectral-flux/onset-density curves, and reproducibility parameters.
- Added analysis status, BPM, beat count, progress, failure, and rerun controls to the project UI.
- Phase 5 Timeline V1 completed with a canvas-based, horizontally scrollable and zoomable workspace.
- Added persisted scene/keyframe models, transactional split/delete/boundary edits, and validation of the shared-keyframe invariant.
- Added waveform, beat, downbeat, and energy overlays with visibility controls and an audio-synchronized playback head.
- Added beat/downbeat/bar/free snapping, Alt-key bypass, active snap-target feedback, and scene/keyframe inspectors.
- Beatweave now downloads missing Beat This checkpoints into its application-data model cache, validates completed transfers, reuses cached files, and reports actionable download failures.
- Windows desktop shutdown now terminates the full `uv`/Python backend process tree so development restarts cannot reconnect to stale code.
- Phase 6 suggested scene layout completed with deterministic downbeat-, energy-, section-, and interval-aware boundary planning.
- Added non-mutating layout previews, transactional apply, shared-keyframe reconstruction, and persisted one-level layout undo.
- Phase 7 editing reliability completed with persisted multi-step timeline command history and exact snapshot restoration.
- Added undo/redo for scene creation, deletion, boundary moves, layout application, and scene prompt edits, plus keyboard shortcuts and redo-branch invalidation.
- Phase 8 creative direction completed with a persisted brief, visual-trajectory model, motifs, palette, narrative arc, and negative guidance.
- Added project-owned style-reference import, gallery, reopen persistence, and safe removal that never deletes external source files.
- Phase 9 LLM provider layer completed with persisted app-level configuration and an OpenAI-compatible local adapter.
- Added strict visual-plan and scene-plan schemas, validated structured generation, one repair retry, timeout handling, safe offline status, and credential-redacted logging/API responses.
- Added UI controls for endpoint, model, timeout, optional API key, configuration persistence, and connection testing.
- Phase 10 project-level visual planning completed with analysis, timeline, energy, creative-brief, and style-reference context construction.
- Added validated global trajectories and per-scene concepts, image/video prompts, visual/motion intensity, editable inspectors, overwrite confirmation, and isolated scene regeneration.
- Ollama planning keeps the model resident between related calls and sends `keep_alive: 0` on the final call so VRAM is released afterward.
- Creative-brief list fields now preserve spaces and commas while typing, and new LLM settings default to Ollama at `http://localhost:11434/v1` with `qwen3:8b`.
- Ollama structured planning now disables model reasoning so hidden thinking cannot exhaust the response budget, and generates scene plans in batches of three for predictable output size.
- Phase 11 durable job infrastructure completed with a generic per-project jobs table, typed lifecycle states, related entity/backend metadata, timestamps, output metadata, and inspectable errors.
- Added a sequential backend worker with cooperative cancellation, startup/open-project reconciliation, and preservation of detectable partial output across restarts.
- Added job list/detail/cancel APIs and WebSocket events for job creation, progress, completion, and failure; audio analysis now runs through the generic worker.
- Phase 12 ComfyUI integration completed with persisted application-level configuration, health/profile checks, and an offline-safe settings panel.
- Added a canonical image-render request, packaged Qwen Image 2.1 workflow profile, private adapter node map, required-node/model/input validation, workflow submission, history polling, and structured failure capture.
- Generated ComfyUI images are downloaded through its API, copied into project `keyframes/`, hashed, registered as `generated_image` assets, and associated with durable render jobs.
- A live 256×256 Qwen Image 2.1 render completed through ComfyUI 0.37.0 on the RTX 4070; Beatweave then restarted, reconnected without restarting ComfyUI, reopened the project, and found the persisted output.
- Phase 13 keyframe generation completed with immutable `KeyframeVariant` records, persisted prompts/backend settings/reference assets, selected variants, and chained previous-keyframe conditioning.
- Added Qwen Image 2.1 reference-image uploads, global and optional reference composition, durable render failure inspection, and automatic first-variant selection without deleting prior variants.
- Added keyframe generation, comparison, selection, file-location, and failure controls plus selected-image thumbnails on the canvas timeline.
- Shared-boundary variant changes warn when adjacent rendered scenes are affected, mark their selected takes stale after confirmation, and preserve those take IDs and every generated image.
- Visual planning copies each scene image prompt onto that scene's start keyframe; shared boundaries therefore use the following scene's prompt, with overwrite confirmation protecting edited keyframe text.
- Project keyframe generation defaults to 1920×1088, the nearest Qwen-compatible 16:9 size to 1080p; reference renders use matching conditioning latents, light semantic influence by default, optional structural influence, and explicit progression instructions.
- Keyframe variants now randomize their persisted seed by default, allow an explicitly locked seed, expose off/light/structural previous-keyframe influence, and use Qwen-native `<image1>` progression instructions to avoid near-duplicate chained frames.
- Phase 14 Wan2GP integration completed against a user-managed Gradio service at a configurable URL.
- Added persisted service settings and endpoint readiness checks without taking ownership of Wan2GP startup or shutdown.
- Added the canonical video-render request, LTX 2.3 Distilled 1.1 preview/final profiles, audio-reactive LoRA settings, and private queue ZIP serialization with first/end frames.
- Added durable video-render jobs that submit through Wan2GP's stateful queue API, download the result, associate it with the originating scene/job, and register it as a project `generated_video` asset.
- A live 17-frame LTX 2.3 render completed through the running Wan2GP service and passed end-to-end asset association checks.
- Desktop startup now rejects an occupied backend port instead of silently connecting the new UI to stale backend code, and standard FastAPI errors render safely in settings panels.
- Phase 15 video takes completed with immutable prompt/backend/source snapshots, output assets, persistent selection, and stale-state tracking.
- Added preview and final render controls, in-inspector playback, take history, selection, confirmed deletion, job progress, and inspectable failures.
- Final Wan2GP renders now target 1920×1088, the nearest multiple-of-32 LTX resolution to 1080p 16:9; preview renders remain 768×448.
- Verified two-take selection and failed-third-render preservation in the automated lifecycle test, plus a live persisted take through the running Wan2GP service.
- Wan2GP scene renders now extract the matching project-soundtrack range, attach it as an LTX audio guide, and select soundtrack-conditioned video generation; older unconditioned takes are reported stale.
- Phase 16 timeline video preview completed with canvas thumbnails, selected-take markers, and distinct unrendered/rendering/complete/failed/stale/missing scene states.
- Added a playhead-synchronized selected-take monitor that advances across scene clips while keeping the original project audio as the sole playback master.
- Phase 17 preview/final profiles completed for ComfyUI images and Wan2GP video with independently configurable dimensions and inference settings.
- Preview assets now live under project `previews/` while final images/videos use `keyframes/` and `renders/`; immutable variant/take snapshots retain the resolved quality settings.
- Added explicit image preview/final actions and promotion of a non-stale approved video preview into a final render without changing the selected take automatically.
- Phase 18 final assembly and export completed with readiness checks for absent, stale, duration-mismatched, and missing selected-take media.
- Added persisted FFmpeg export jobs that normalize and concatenate selected takes in timeline order, mux the original soundtrack, preserve timeline duration, and register the finished file under project `exports/`.
- Added overview export controls for output filename, H.264/H.265, CRF, readiness issues, progress, failures, and opening the completed export location.
- Repeated exports now preserve existing files and automatically use incrementing names such as `video (2).mp4` and `video (3).mp4`.

## Known-Good State

- `npm run check` and `npm test` pass from the repository root.
- Fresh dependency installation is verified with `npm ci --prefix frontend` and `uv sync --project backend --all-groups --locked`.
- `cargo check --manifest-path src-tauri/Cargo.toml` and the production frontend build pass.
- A Tauri development smoke launch created the database, served `/health`, and stopped the backend on exit.
- Project lifecycle tests verify creation, metadata persistence, application restart, reopen, missing paths, and overwrite protection.
- Media integration tests cover WAV/MP3 import, metadata probing, waveform reuse, bounded peaks, range requests, and reopen.
- Analysis tests cover three tempos, exact timestamp persistence, bounded energy, caching, forced reruns, and persisted failures.
- Timeline tests cover coordinate round-trips, real-timestamp snapping, modifier/free placement, shared boundaries, invalid durations, deletion, and exact reopen timing.
- Checkpoint tests cover first-use download, cache reuse, interrupted transfers, and cleanup of partial files.
- Layout tests cover deterministic proposals, musical inputs, full-track coverage, duration constraints, preview isolation, shared keyframes, reopen, and exact undo restoration.
- History tests cover repeated undo/redo, prompt restoration, divergent-edit invalidation, deletion recovery, reopen persistence, shared boundaries, and job-event isolation.
- Creative-direction tests cover full brief persistence and style-reference import, reopen, content delivery, and external-source preservation.
- LLM tests cover configuration persistence, project isolation, offline behavior, strict schemas, repair retries, malformed output rejection, and credential redaction.
- Visual-planning tests cover context summaries, exact timing preservation, overwrite protection, invalid-ID rollback, per-scene isolation, bounded scene batches, native Ollama schemas, and model release behavior.
- Job-system tests cover legacy migration, lifecycle transitions, persisted metadata, failure inspection, restart recovery, cooperative cancellation, WebSocket delivery, and job APIs.
- ComfyUI tests cover configuration persistence, offline behavior, canonical workflow mapping, model/input validation, submission, prompt tracking, completion/failure detection, output download, asset registration, and live restart/reconnect behavior.
- Keyframe tests cover previous/global/optional reference chaining, immutable variant history, shared-boundary selection, stale-render confirmation, and preservation of selected video takes.
- Wan2GP tests cover offline-safe configuration, canonical queue mapping, queue ZIP attachments, stateful Gradio submission, output association, and a live LTX 2.3 render.
- Video-take tests cover preview/final snapshots, automatic first selection, explicit switching, stale prompts, deletion fallback, and preservation after render failure.
- Wan2GP queue tests verify the scene audio guide, soundtrack conditioning mode, and normalized stereo WAV attachment.
- Timeline video-state aggregation is covered by the video-take lifecycle test; frontend checks cover the typed monitor and canvas integration.
- Quality-profile tests cover persisted settings, separate preview/final storage, promotion snapshots, and immutability after configuration changes.
- Final-export integration tests use real FFmpeg media to cover readiness failures, normalization, multi-scene order, soundtrack muxing, and expected output duration.
- The real Beat This `small0` checkpoint was verified on generated 80, 120, and 160 BPM tracks.
- Architecture currently targets Tauri + React/TypeScript + Python/FastAPI + SQLite.
- Initial render backends are ComfyUI for keyframes and the existing Wan2GP installation for LTX 2.3 video generation.

## Known Issues / Blockers

- The system `python.exe` launcher is unusable on this workstation; backend commands use the managed `uv` environment.
- Beat This downloads its selected checkpoint on first use; existing projects remain openable if that download is unavailable.

## Important Implementation Notes

- Keep the timeline as the central user experience.
- Preserve the shared-keyframe invariant between adjacent scenes.
- Keep renderer-specific formats inside backend adapters.
- Reuse the user-managed Wan2GP service before considering a native LTX pipeline; Beatweave does not own its process lifecycle.

## Next Recommended Task

- [ ] Implement Phase 19 crash recovery, missing-media relinking, and resilience validation.
