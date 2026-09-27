# AGENTS.md

This file defines how coding agents should work in the Beatweave repository.

## 1. Start Here

Before making code changes:

1. Read `DESIGN.md`.
2. Read `PLAN.md`.
3. Read `PROJECT_STATE.md` if it exists.
4. Inspect the relevant existing code before proposing architecture changes.
5. Identify the next unchecked task in the current phase unless the user explicitly asks for different work.

Do not assume that later-phase features already exist.

---

## 2. Source of Truth

Use these files for different purposes:

- `DESIGN.md`
  - Product intent
  - Architecture
  - Core concepts
  - Invariants
  - Goals and non-goals

- `PLAN.md`
  - Implementation sequence
  - Current completion state
  - Acceptance criteria

- `PROJECT_STATE.md`
  - Current known-good state
  - Active milestone
  - Known blockers
  - Important implementation notes
  - Recommended next task

- `design.png`
  - UI design direction

If code and documentation disagree, investigate before changing either.

---

## 3. Working Process

For each implementation task:

1. Read the relevant design section.
2. Read the relevant plan item and acceptance criteria.
3. Inspect existing implementation.
4. Make the smallest coherent change that completes the task.
5. Add or update tests where appropriate.
6. Run relevant checks.
7. Fix failures.
8. Verify acceptance criteria.
9. Mark the `PLAN.md` checkbox complete only after verification.
10. Update `PROJECT_STATE.md` when the project state, blocker list, or next task changes.

Never mark partially implemented work as complete.

---

## 4. Session Boundaries

Beatweave is intentionally developed in phases so work can resume cleanly after context resets or usage limits.

Before ending a substantial coding session:

- Ensure modified files are saved.
- Run relevant tests/checks.
- Update completed checkboxes in `PLAN.md`.
- Update `PROJECT_STATE.md`.
- Record known failures or blockers.
- Record the next recommended task.
- Avoid leaving undocumented half-migrations or hidden manual setup.

A future coding-agent session should be able to resume by reading the repository documentation.

---

## 5. Architectural Invariants

Do not violate these without an explicit design decision.

### Timeline and scene model

- The timeline is the primary source of scene timing.
- Real detected beat timestamps are stored and used for snapping.
- BPM is metadata, not a substitute for detected beat positions.
- Adjacent scenes share a single boundary keyframe entity.

Conceptually:

```text
KF0 ───── Scene 1 ───── KF1 ───── Scene 2 ───── KF2
```

Do not duplicate `KF1` as separate "end" and "start" images.

### Prompts

- Image prompts and video prompts are separate concepts.
- Generated prompts are editable.
- User-edited prompts must not be silently overwritten.
- Regenerating one scene should not modify unrelated scenes.

### Rendering

- Core project models are renderer-agnostic.
- ComfyUI node IDs belong inside ComfyUI adapters/profiles.
- Wan2GP queue details belong inside the Wan2GP adapter.
- Do not spread backend-specific data throughout the UI or database model.
- Render outputs are stored as variants/takes.
- Generating a new take does not delete previous takes.
- A failed render never removes an existing successful selected take.

### Jobs

- Long-running operations are jobs.
- Jobs are persisted.
- The UI must not directly await multi-minute rendering as a synchronous request.
- Job errors must remain inspectable.

### Local-first

- Projects must open without internet access.
- Projects must open even when ComfyUI or Wan2GP is offline.
- Cloud services must not become a hidden requirement for editing existing projects.

---

## 6. Scope Discipline

Beatweave is not a general-purpose NLE.

Do not add general video-editor features unless they directly serve the defined workflow.

Examples of features that are out of scope unless explicitly requested:

- arbitrary multitrack compositing
- title designer
- color grading suite
- keyframe animation system for arbitrary UI parameters
- DAW functionality
- node editor
- general plugin marketplace

Prefer specialized Beatweave functionality over broad editor abstractions.

---

## 7. Frontend Guidance

Primary stack:

- React
- TypeScript
- Tauri
- Zustand for transient UI state

The backend/database remains the durable source of truth.

Use frontend state for things such as:

- selection
- zoom
- scroll
- temporary edits
- playback state
- open panels

Do not make the entire persisted project model live only inside React state.

### Timeline

Avoid implementing thousands of timeline primitives as deeply nested React DOM nodes.

Prefer:

- Canvas
- PixiJS
- another explicit high-performance renderer

Keep timeline math separate from rendering.

For example:

```ts
interface TimelineTransform {
  timeToX(time: number): number;
  xToTime(x: number): number;
}
```

Snapping should also remain independent from drawing.

---

## 8. Backend Guidance

Primary stack:

- Python
- FastAPI
- Pydantic
- SQLite
- FFmpeg/ffprobe
- Beat This
- audio-analysis libraries as needed

Keep services separated by responsibility.

Preferred conceptual modules:

```text
analysis/
planning/
llm/
rendering/
media/
jobs/
project/
api/
```

Avoid a single oversized application service.

---

## 9. API Guidance

Frontend/backend APIs should use explicit typed request and response models.

Do not return arbitrary unvalidated dictionaries from important application endpoints.

Long-running tasks should return a job ID.

Example:

```text
POST /projects/{id}/analyze
→ { "job_id": "..." }
```

Progress/completion should arrive through the job/event system.

---

## 10. Database Guidance

Use migrations.

Do not casually mutate the schema without a migration.

Large media files should remain files on disk.

SQLite stores:

- project metadata
- scenes
- keyframes
- variants
- takes
- prompts
- jobs
- settings
- media metadata

Do not store full video/image binaries as SQLite blobs.

---

## 11. Media Guidance

All FFmpeg and ffprobe execution should flow through a central media service.

Do not scatter raw command construction throughout unrelated modules.

The media service should own:

- process execution
- argument construction
- error capture
- probing
- frame extraction
- audio conversion
- clip concatenation
- audio muxing
- proxy generation

---

## 12. Audio Analysis Guidance

Beat detection must store actual timestamp arrays.

Do not derive beat timestamps later from:

```text
60 / BPM
```

Energy analysis should initially favor simple, explainable features over large ML models.

Keep raw/derived feature parameters recorded so analysis results can be reproduced.

---

## 13. LLM Guidance

LLMs are creative planning tools, not authorities over application state.

LLMs may propose:

- visual trajectory
- scene concepts
- image prompts
- video prompts
- visual intensity
- motion intensity

LLMs do not control:

- scene boundaries
- database IDs
- file paths
- raw ComfyUI node graphs
- Wan2GP queue structure
- job state

All structured LLM output must be validated before persistence.

Do not allow malformed model output to partially update the project.

---

## 14. Rendering Guidance

### ComfyUI

Treat ComfyUI as an image-render backend.

The adapter owns:

- URL/configuration
- workflow template
- node mapping
- submission
- completion tracking
- output retrieval

The canonical project model must not depend on specific node IDs.

### Wan2GP

Reuse the user's existing working Wan2GP installation initially.

The adapter owns:

- installation configuration
- LTX profile
- audio-reactive LoRA settings
- queue structure
- queue ZIP generation
- submission/export behavior
- output association

Do not embed a native LTX pipeline until Wan2GP is proven to be a limitation.

---

## 15. Resource Constraints

The initial target system has:

- RTX 4070
- 12 GB VRAM
- 64 GB system RAM

Assume that large models may need to run sequentially.

Do not build architecture that requires the local LLM, Qwen image model, and LTX renderer to remain resident on the GPU simultaneously.

Prefer:

- backend process isolation
- explicit availability/status
- preview quality modes
- sequential heavy jobs

---

## 16. Testing Expectations

Add tests at the level where bugs would be expensive.

High-priority test areas:

- project schema
- migrations
- shared-keyframe invariant
- scene timing
- snapping
- audio-analysis persistence
- LLM structured-output validation
- job-state transitions
- adapter request generation
- queue serialization
- project reopen/recovery

UI pixel-perfect tests are lower priority than domain and persistence correctness during early phases.

---

## 17. Definition of Done for a Plan Item

A checkbox may be marked complete only when:

- the implementation exists,
- relevant tests/checks pass,
- acceptance criteria are satisfied,
- obvious error paths are handled,
- documentation is updated if behavior changed.

"Code written" is not the same as "done."

---

## 18. Refactoring Rules

Refactor when it supports the current task or removes clear friction.

Avoid speculative large-scale refactors.

Before changing an established architectural boundary:

1. Explain why the current design is insufficient.
2. Check whether the change conflicts with `DESIGN.md`.
3. Update `DESIGN.md` if the architectural decision genuinely changes.
4. Record important decisions in `PROJECT_STATE.md` or a future `DECISIONS.md`.

---

## 19. Dependency Rules

Prefer mature, focused dependencies.

Before adding a major dependency:

- Confirm it solves a real current problem.
- Prefer libraries already compatible with the selected stack.
- Avoid dependencies that duplicate existing framework capabilities.
- Avoid introducing another runtime unless necessary.

Do not add cloud dependencies for functionality that is intentionally local-first.

---

## 20. Coding-Agent Behavior

When the user asks to "continue", "work on the next task", or similar:

1. Read `PROJECT_STATE.md`.
2. Read the relevant current section of `PLAN.md`.
3. Inspect git/worktree state.
4. Continue from the first appropriate unchecked task.
5. Do not restart completed phases.

When the user asks for a feature outside the current phase:

- implement it if explicitly requested,
- note any prerequisite work,
- keep architecture consistent,
- update `PLAN.md` if the implementation order has materially changed.

Do not ask the user to repeat information already documented in the repository.

---

## 21. Documentation Maintenance

Keep documentation concise and factual.

Update `DESIGN.md` only when product or architecture intent changes.

Update `PLAN.md` whenever implementation completion state changes.

Update `PROJECT_STATE.md` frequently during active development.

Suggested `PROJECT_STATE.md` template:

```md
# Beatweave — Project State

## Current Phase

Phase X — ...

## Completed This Session

- ...

## Known-Good State

- ...

## Known Issues / Blockers

- ...

## Important Implementation Notes

- ...

## Next Recommended Task

- [ ] ...
```

This file exists to help the next development session resume immediately.

---

## 22. Final Reminder

The value of Beatweave is not that it wraps AI models.

The value is the creative workflow:

**music-aware timeline → visual arc → chained keyframes → generative motion → rapid local iteration**

Preserve that workflow when making implementation decisions.
