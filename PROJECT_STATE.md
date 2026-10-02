# Beatweave — Project State

## Current Phase

Phase 21 — Packaging

## Completed This Session

- Added a persisted per-scene approval state with approve/unapprove actions in the timeline
  context menu and scene inspector. Approved scenes override their displayed render state with a
  subtle purple timeline treatment; unapproving immediately reveals the underlying render state.
- Fixed workspace scrolling after visiting Timeline by applying fixed-height overflow constraints from the active navigation view instead of the still-mounted hidden Timeline DOM; added regression coverage for restoring Overview scroll behavior while preserving the Timeline mount.
- Fixed Wan2GP scene rendering when both boundaries use the same image; identical start/end asset IDs and manually imported image variants are now accepted as valid render inputs, with regression coverage.
- Aligned the Timeline workspace more closely with `design.png`: compact application chrome, a consolidated transport/command strip, an edge-to-edge editor canvas, and a persistent full-height inspector. The flattened timeline, preview, and inspector form one continuous square-cornered workstation; scene/status metadata overlays the video, redundant preview helper copy is removed, and the scene blocks end flush with the timeline. The complete Timeline is constrained to `100vh` with no page-level or visible horizontal scrollbar; only the inspector scrolls vertically. The preview container now strictly owns the remaining height and absolutely contains the video canvas, keeping the full fitted frame visible instead of clipping its bottom. Verified at 1680×945 and 1366×768 with Playwright CLI.
- Fixed timeline sequence-preview drift by sampling the authoritative audio element on animation frames, synchronizing scene video against that live clock, and avoiding repeated `play()` calls during clock updates.
- Limited full video preloading to the active and immediately upcoming scene instead of every selected take, reducing decoder, memory, and media-request pressure on longer timelines; added audio-clock regression coverage.
- Replaced the remounted timeline preview video with a persistent canvas backed by preloaded selected-take videos, retaining the last drawn frame while the next scene becomes drawable and doubling the preview's maximum displayed size.
- Fixed timeline playback after workspace navigation by ensuring only the active audio transport owns the shared playback element; added a regression test for deactivation and reactivation.
- Added native file-picker actions for manually assigning PNG/JPEG/WebP images to keyframes and MP4/MOV/MKV/WebM videos to scenes.
- Manual media is validated, copied into portable project storage, registered as immutable variants/takes, and selected immediately; shared-keyframe changes retain stale-render confirmation.
- Added regression coverage for manual image/video import, project-local copies, provenance, selection, and scene-duration freshness.
- Render-all video jobs now persist a select-on-completion intent; recovered jobs select their completed takes in the backend, so final clips appear on the timeline even when the app is closed and reopened mid-queue.
- Scene video controls now include Render all, which enqueues the selected scene and every subsequent clip at final resolution into the existing sequential backend render queue and reports aggregate completion.
- Rendered keyframe variants can now be removed with confirmation; managed image files are deleted, selected variants fall back to the newest remaining variant, and affected adjacent video takes are marked stale.
- Added a keyframe-inspector Render all action with a continuity dialog; it renders the clicked keyframe and every later keyframe at final/full-size quality, selecting each completed variant before starting the next so chained references attach to the newly rendered predecessor.
- Keyframe image generation now supplies the preceding scene's motion prompt as end-state context alongside the starting scene's image prompt at shared boundaries.
- Any keyframe can now be set to a locally generated pure-black selectable variant; changing a keyframe with adjacent rendered takes retains the existing stale-render confirmation behavior.
- Workspace navigation now keeps the timeline mounted after its first visit for the current project, preserving loaded keyframe images, video elements, canvas state, zoom, and scroll position when switching through the overview.
- Hidden timelines suspend polling, keyboard shortcuts, audio/video playback, and canvas drawing; a frontend regression test verifies Timeline → Overview → Timeline uses a single timeline mount.
- Phase 20 UX polish completed with workspace navigation shortcuts, timeline editing shortcuts, a discoverable shortcut reference, and timeline context menus.
- Added intentional drag thresholds, wheel zoom/scroll behavior, persistent snap feedback, actionable tooltips, polished loading/empty/error states, and clearer offline-backend guidance.
- Reorganized application settings into focused connection, planning, image, video, and recovery views with a consolidated local-service connectivity screen.
- Added a live render queue with active/all/failed filters, progress, cancellation, failure details, immutable retry, and empty/loading states.
- Added side-by-side A/B comparison for image variants and video takes while preserving explicit selection as a separate action.
- Added first-run workflow guidance on the launcher and an in-project path from audio import through analysis, timeline editing, and optional backend setup.
- Added focused interaction-helper tests for editable-target shortcut protection, shortcut matching, and pointer drag thresholds.
- Added a dark native color scheme and a high-contrast default style for every button, including consistent hover and keyboard-focus feedback, so unclassified controls no longer render white on white under dark system themes.
- Phase 19 reliability and project recovery completed with full-sync WAL persistence, periodic checkpoints, rotating project-database snapshots, and manual backups.
- Added pre-migration backups and explicit interrupted-migration markers so partial project upgrades cannot open silently.
- Added project integrity diagnostics for SQLite, schema, foreign keys, managed directories, and asset path/size/hash checks, plus exact-hash missing-media relinking.
- Added backend readiness diagnostics, immutable failed/cancelled-job retry, structured rotating JSONL application logs, recent-log viewing, and full-log export.
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

- The timeline workspace persistence and audio-clock regression tests pass; all 18 frontend tests, frontend lint/type-check/format checks, and the production frontend build pass.
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
- Recovery tests cover valid backups, interrupted and successful migrations, missing/corrupt asset detection, exact media relinking, immutable job retry, and structured log export.
- Phase 20 frontend checks cover drag-threshold behavior, shortcut protection, production compilation, and the complete repository regression suite.
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

- [ ] Implement Phase 21 packaging, starting with a reproducible Windows development build and documented runtime/FFmpeg strategy.
