# Beatweave

Beatweave is a local-first desktop workstation for turning music-aware scene timing into chained generative keyframes and video clips. The project is being built incrementally from the architecture in `DESIGN.md` and the milestones in `PLAN.md`.

## Install the Windows release

Run the generated `Beatweave_0.3.8_x64-setup.exe`. The installer is per-user, does not require
administrator rights, and includes the Beatweave Python runtime, locked backend dependencies,
FFmpeg, and ffprobe. Node.js, Rust, Python, `uv`, and a system FFmpeg installation are only needed
when building from source.

ComfyUI, Wan2GP, and a local LLM remain optional user-managed services. Beatweave opens and edits
projects while any of them are offline. See [Windows and backend setup](docs/WINDOWS_SETUP.md) for
release building and service configuration.

An optional local MCP server can be started from the desktop settings to create, inspect, and
control projects end to end. A stdio development entry point remains available. See
[MCP control surface](docs/MCP.md) for tools and client configuration.

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

Settings > Video offers **LTX 2.3 Distilled + audio-reactive LoRA**, **MiniMax H3 FL2VA 33B**,
and **MiniMax H3 FL2VA Pruned 20B**. Choose a model and save to apply it. Each model keeps its
own preview/final settings. H3 conditions on the project soundtrack natively and does not load
the LTX LoRA. H3 generates at least 4.46 seconds; shorter timeline scenes use trimmed clips.
Generation uses 24 fps and 17-frame increments. H3 dimensions must be multiples of 32
(final defaults to 1920x1088). Precision,
VAE selection, and memory profiles are configured in WanGP. New queued jobs and retries retain
their renderer settings; promoting a preview retains its model even after switching Settings.
Pruned 20B also offers **Default** and **8 step PDD** variants. PDD fixes preview/final sampling
to eight steps with Euler. Each variant retains independent quality settings.

For a password-protected remote WanGP instance, enter its HTTPS service URL and **Web password**
in Settings > Video, save, then use **Test connection**. This supports WanGP's password-only
`--auth` login, including uploads and downloads. Leave the password blank to keep the saved
value, or select **Remove saved web password when saving** to clear it. Passwords are stored
locally per service URL and never included in project/job snapshots.

SSH tunnels to RunPod can use `http://127.0.0.1:7860`, including when forwarded through WSL.
For HTTP `localhost` URLs, Beatweave prefers a reachable IPv4 relay to avoid Windows IPv6
connection delays. Saved URLs/password scope and HTTPS hostnames remain unchanged. The remote
server does not need to share a filesystem with Beatweave; matching outputs download through
its Gradio API. Keep the tunnel open through upload and download. Failed connection attempts
before submission can resume safely after restart. A dropped render stream switches to output
polling; an ambiguous submission is monitored rather than submitted again. Queue upload and
gallery calls use the configured request timeout and remain cancellable.

Render filenames include a scene number and unique job ID, such as
`bw_scene_01_<compact-job-id>.mp4`, short enough for WanGP's Windows filename limit.
Earlier names truncated by WanGP are recognized during recovery. Restarting Beatweave resumes
the original submitted render instead of submitting it again. In Settings → Video, optionally
set **Wan2GP output folder**
to the full path of Wan2GP's video output folder. Beatweave also learns this folder from
locally accessible matching gallery outputs; it can also reuse already downloaded completed media
without contacting WanGP. Gallery polling downloads only the current job's output. Beatweave
can recover finished videos exposed by its remote gallery even without the original session.
For older renders that the gallery no longer exposes, use an accessible output folder or manual
video linking. Recovery preserves existing takes and only imports readable completed media.

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

## Publish a release

Push a stable semantic-version tag to build and publish the Windows installer through GitHub
Actions:

```powershell
git tag v0.3.8
git push origin v0.3.8
```

The tag version must match `package.json`, `frontend/package.json`, `backend/pyproject.toml`,
`src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json`. The workflow runs the repository checks and
tests, builds and smoke-tests the packaged runtime, then creates a GitHub release containing the
NSIS installer, its SHA-256 checksum, and generated release notes.

If a tag already exists but its push event did not start a run, open **Actions > Release Windows
installer > Run workflow** and enter that tag. The manual run checks out the tagged commit rather
than the current branch, so it produces the same release artifact without moving the tag.

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
