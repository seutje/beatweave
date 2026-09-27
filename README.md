# Beatweave

Beatweave is a local-first desktop workstation for turning music-aware scene timing into chained generative keyframes and video clips. The project is being built incrementally from the architecture in `DESIGN.md` and the milestones in `PLAN.md`.

## Prerequisites

- Windows 10 or 11
- Node.js 20 or newer and npm
- Rust stable with Cargo (required by Tauri)
- [`uv`](https://docs.astral.sh/uv/) for the managed Python 3.12 environment
- FFmpeg and ffprobe available on `PATH`
- Microsoft C++ Build Tools and WebView2 for Tauri development

Python does not need to be installed separately when `uv` is available.
Beat This downloads its configured model checkpoint on the first analysis run; subsequent runs use the local cache.

## Install

From the repository root:

```powershell
npm install --prefix frontend
uv sync --project backend --all-groups
```

Both commands use lockfiles once they have been generated, so a fresh clone installs the same dependency graph.

## Development commands

```powershell
npm run dev:frontend   # Vite development server
npm run dev:backend    # FastAPI development server
npm run dev            # Tauri desktop app (starts and stops the backend automatically)
npm run build          # production frontend build
npm run build:desktop  # desktop build
npm run check          # formatting, linting, and TypeScript checks
npm test               # frontend and backend tests
```

Desktop development and packaging commands will be added with the Tauri application foundation in Phase 1.

## Repository layout

```text
backend/      Python application and tests
frontend/     React/TypeScript application and tests
src-tauri/    Tauri desktop shell (introduced in Phase 1)
DESIGN.md     product and architecture source of truth
PLAN.md       phased implementation plan and acceptance criteria
PROJECT_STATE.md current known-good state and next task
```

## Working on Beatweave

Read `AGENTS.md`, `DESIGN.md`, `PLAN.md`, and `PROJECT_STATE.md` before making implementation changes. Keep generated media outside SQLite, preserve real detected beat timestamps, and keep render-backend details behind adapters.
