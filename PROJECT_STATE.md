# Beatweave — Project State

## Current Phase

Phase 0 — Repository and Tooling

## Completed This Session

- Initial product architecture documented in `DESIGN.md`.
- Initial phased implementation plan created in `PLAN.md`.
- Coding-agent workflow documented in `AGENTS.md`.

## Known-Good State

- No application code has been created yet.
- Architecture currently targets Tauri + React/TypeScript + Python/FastAPI + SQLite.
- Initial render backends are ComfyUI for keyframes and the existing Wan2GP installation for LTX 2.3 video generation.

## Known Issues / Blockers

- None yet.

## Important Implementation Notes

- Keep the timeline as the central user experience.
- Preserve the shared-keyframe invariant between adjacent scenes.
- Keep renderer-specific formats inside backend adapters.
- Reuse the existing Wan2GP installation before considering a native LTX pipeline.

## Next Recommended Task

- [ ] Create the repository structure based on `DESIGN.md`.
