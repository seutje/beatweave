# Beatweave

Beatweave is a local-first desktop workstation for turning music-aware scene timing into chained generative keyframes and video clips. The project is being built incrementally from the architecture in `DESIGN.md` and the milestones in `PLAN.md`.

## Install the Windows release

Run the generated `Beatweave_0.1.0_x64-setup.exe`. The installer is per-user, does not require
administrator rights, and includes the Beatweave Python runtime, locked backend dependencies,
FFmpeg, and ffprobe. Node.js, Rust, Python, `uv`, and a system FFmpeg installation are only needed
when building from source.

ComfyUI, Wan2GP, and a local LLM remain optional user-managed services. Beatweave opens and edits
projects while any of them are offline. See [Windows and backend setup](docs/WINDOWS_SETUP.md) for
release building and service configuration.

An optional local stdio MCP server can inspect and control the active project without becoming part
of the desktop runtime. See [MCP control surface](docs/MCP.md) for tools and host configuration.

## Development prerequisites

- Windows 10 or 11
- Node.js 20 or newer and npm
- Rust stable with Cargo (required by Tauri)
- [`uv`](https://docs.astral.sh/uv/) for the managed Python 3.12 environment
- FFmpeg and ffprobe available on `PATH`
- Microsoft C++ Build Tools and WebView2 for Tauri development

Python does not need to be installed separately when `uv` is available.
Beatweave downloads the configured Beat This checkpoint on the first analysis run and stores it in its application data directory. Model files are reused on subsequent runs and are never stored in a project or committed to this repository.

Video rendering uses [WanGP/Wan2GP](https://github.com/deepbeepmeep/Wan2GP) as an external
backend. Start your existing Wan2GP installation yourself (the default service URL is
`http://localhost:7860`); Beatweave connects to its Gradio API and does not manage that process.

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
npm run dev:mcp        # optional stdio MCP server
npm run check          # formatting, linting, and TypeScript checks
npm test               # frontend and backend tests
```

`npm run build:desktop` creates the per-user NSIS installer under
`src-tauri/target/release/bundle/nsis/`. The packaging step freezes the locked Python environment
and copies the builder-provided FFmpeg executables into the installer.

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
