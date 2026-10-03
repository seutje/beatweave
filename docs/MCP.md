# Beatweave MCP Control Surface

Beatweave's MCP server is an optional local stdio process. The desktop application and FastAPI
backend do not start it, import it, or depend on an MCP client. The stdio process bridges tool calls
to the running local Beatweave API, so every mutation goes through the exact services, job worker,
and event stream used by the normal UI.

## Start the server

Start the Beatweave desktop app (or `npm run dev:backend`), then install the locked optional group
and run the stdio entry point from the repository:

```powershell
uv sync --project backend --all-groups --locked
uv run --project backend --group mcp beatweave-mcp
```

The bridge connects to `http://127.0.0.1:8420` by default. `BEATWEAVE_HOST` and `BEATWEAVE_PORT`
may be set for a source backend using a different local address. The MCP process uses stdout only
for stdio protocol traffic.

An MCP host configuration has this shape (use absolute paths in real configuration):

```json
{
  "command": "uv",
  "args": [
    "run",
    "--project",
    "I:\\projects\\beatweave\\backend",
    "--group",
    "mcp",
    "beatweave-mcp"
  ]
}
```

## Tools

Read-only tools:

- `get_project` — return the active project, or `null` when no project is open.
- `get_timeline` — return authoritative scene timing and shared keyframes.
- `get_scenes` — list scenes or fetch one exact scene ID.
- `get_jobs` — inspect persisted jobs, optionally filtered by state.

Mutation tools:

- `update_scene` — edit concept, prompts, approval, or last-frame conditioning through timeline
  history. Prompt/conditioning changes preserve takes and mark affected selections stale.
- `generate_visual_plan` — run the validated planning pipeline without changing scene timing.
- `render_keyframe` — enqueue a durable ComfyUI keyframe job.
- `render_scene` — enqueue a durable Wan2GP video job.
- `select_take` — select an existing immutable video take.
- `export_project` — validate readiness and enqueue a durable FFmpeg export job.

Render and export tools return immediately with a job record. Poll `get_jobs` for progress,
completion, or inspectable failure information. The MCP layer does not wait synchronously for a
renderer. The desktop/backend process remains the only job worker, preventing duplicate claims and
ensuring MCP-created jobs produce the same WebSocket events and recovery behavior as UI-created
jobs.

## Safety and errors

MCP clients should inspect the project and timeline before mutation and ask for user approval before
costly renders or exports. The surface intentionally exposes no project deletion, media deletion,
timeline-boundary mutation, arbitrary file write, backend configuration, or raw renderer graph/queue
operations.

Expected application failures are returned as MCP tool errors containing JSON with a stable
Beatweave `code`, human-readable `message`, and optional `details`. Examples include
`project_not_open`, `scene_not_found`, `overwrite_confirmation_required`, and
`export_not_ready`. Jobs remain persisted and visible to the UI even when they were created by MCP.
