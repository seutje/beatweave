# Beatweave — Project State

## Current Phase

Phase 4 — Beat and Energy Analysis

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

## Known-Good State

- `npm run check` and `npm test` pass from the repository root.
- Fresh dependency installation is verified with `npm ci --prefix frontend` and `uv sync --project backend --all-groups --locked`.
- `cargo check --manifest-path src-tauri/Cargo.toml` and the production frontend build pass.
- A Tauri development smoke launch created the database, served `/health`, and stopped the backend on exit.
- Project lifecycle tests verify creation, metadata persistence, application restart, reopen, missing paths, and overwrite protection.
- Media integration tests cover WAV/MP3 import, metadata probing, waveform reuse, bounded peaks, range requests, and reopen.
- Architecture currently targets Tauri + React/TypeScript + Python/FastAPI + SQLite.
- Initial render backends are ComfyUI for keyframes and the existing Wan2GP installation for LTX 2.3 video generation.

## Known Issues / Blockers

- The system `python.exe` launcher is unusable on this workstation; backend commands use the managed `uv` environment.

## Important Implementation Notes

- Keep the timeline as the central user experience.
- Preserve the shared-keyframe invariant between adjacent scenes.
- Keep renderer-specific formats inside backend adapters.
- Reuse the existing Wan2GP installation before considering a native LTX pipeline.

## Next Recommended Task

- [ ] Implement Phase 4 persisted beat/downbeat and energy analysis jobs with progress UI.
