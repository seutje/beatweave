# Beatweave — Project State

## Current Phase

Phase 7 — Undo / Redo and Editing Reliability

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
- Reuse the existing Wan2GP installation before considering a native LTX pipeline.

## Next Recommended Task

- [ ] Implement Phase 7 general undo/redo and editing reliability.
