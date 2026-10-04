# Beatweave MCP Control Surface

Beatweave's MCP server is an optional local process. The FastAPI backend does not import it or
depend on an MCP client. The process bridges tool calls
to the running local Beatweave API, so every mutation goes through the exact services, job worker,
and event stream used by the normal UI.

## Start the server from Beatweave

Open **Settings → MCP** and select **Start MCP server**. The desktop app starts a local-only
Streamable HTTP endpoint at `http://127.0.0.1:8421/mcp`. It remains off by default and stops when
Beatweave exits. Configure HTTP-capable MCP clients with that URL.

## Start a stdio server for development

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
- `get_analysis` — return the current beat/downbeat/energy analysis.
- `get_timeline` — return authoritative scene timing and shared keyframes.
- `get_scenes` — list scenes or fetch one exact scene ID.
- `get_keyframe` — inspect a keyframe, imported variants, adjacency, and render jobs.
- `get_jobs` — inspect persisted jobs, optionally filtered by state.
- `get_job` — inspect one exact job for reliable polling.
- `suggest_layout` — calculate a beat-aware layout proposal without applying it.
- `get_video_takes` — inspect video takes and render jobs for one scene or the timeline.
- `check_wan2gp` — verify that the configured Wan2GP service is ready.
- `get_export_readiness` — diagnose missing, stale, mismatched, or unavailable selected takes.

Mutation tools:

- `create_project` — create and open a project under an existing parent directory.
- `open_project` — open an existing project directory or `project.db` path.
- `import_audio` — copy a source track into the project and generate its waveform.
- `start_analysis` — enqueue beat, downbeat, and energy analysis.
- `apply_layout` — apply reviewed proposed boundaries as contiguous scenes and shared keyframes.
- `update_scene` — edit concept, prompts, approval, or last-frame conditioning through timeline
  history. Prompt/conditioning changes preserve takes and mark affected selections stale.
- `update_keyframe` — set a shared keyframe's editable image prompt through timeline history.
- `import_keyframe_image` — copy and select an agent-generated PNG, JPEG, or WebP variant.
- `generate_visual_plan` — run the optional validated LLM planning pipeline.
- `render_keyframe` — enqueue an optional ComfyUI keyframe job.
- `render_scene` — enqueue a durable Wan2GP video job.
- `select_take` — select an existing immutable video take.
- `export_project` — validate readiness and enqueue a durable FFmpeg export job.

Analysis, render, and export tools return immediately with a job record. Poll `get_job` for precise
progress, completion, or inspectable failure information. The MCP layer does not wait synchronously for a
renderer. The desktop/backend process remains the only job worker, preventing duplicate claims and
ensuring MCP-created jobs produce the same WebSocket events and recovery behavior as UI-created
jobs.

## Agent-authored workflow without an LLM or ComfyUI

An MCP agent can complete the normal workflow while supplying its own prompts and images:

1. Call `create_project`, then `import_audio`.
2. Call `start_analysis` and poll its returned ID with `get_job` until it is terminal.
3. Call `get_analysis`, then `suggest_layout`. Review the proposal and pass its complete
   `boundaries` array to `apply_layout`.
4. Call `get_timeline`. Use `update_scene` for every scene's concept, image prompt, video prompt,
   approval, and last-frame-conditioning choice.
5. Use `update_keyframe` for every shared keyframe prompt. Generate images outside Beatweave, then
   call `import_keyframe_image` once per keyframe. The imported image becomes a selected immutable
   variant; one shared boundary image serves both adjacent scenes.
6. Call `check_wan2gp`, then `render_scene` for each scene. Pass `select_on_complete: true` when the
   completed take should become selected automatically. Poll each returned job with `get_job`.
7. Inspect results with `get_video_takes` and `get_export_readiness`. Once every scene has a
   non-stale selected take, call `export_project` and poll its job with `get_job`.

The agent must use filesystem paths visible to the local Beatweave process. Project creation never
overwrites an existing path, and imported source media and keyframe images are copied into the
portable project directory.

## Safety and errors

MCP clients should inspect proposed layout changes before applying them and ask for user approval
before costly renders or exports. Project creation and media import write only to the explicitly
provided project parent and source paths through the same validated application services as the UI.
The surface intentionally exposes no project deletion, media deletion, arbitrary boundary editing,
backend configuration, or raw renderer graph/queue operations.

Expected application failures are returned as MCP tool errors containing JSON with a stable
Beatweave `code`, human-readable `message`, and optional `details`. Examples include
`project_not_open`, `scene_not_found`, `overwrite_confirmation_required`, and
`export_not_ready`. Jobs remain persisted and visible to the UI even when they were created by MCP.
