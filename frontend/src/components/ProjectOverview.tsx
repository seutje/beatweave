import { type FormEvent, useState } from "react";

import { useProjectStore } from "../stores/projectStore";

export function ProjectOverview() {
  const { current, loading, error, closeProject, updateProject, clearError } =
    useProjectStore();
  const [name, setName] = useState(current?.name ?? "");

  if (!current) return null;
  const dirty = name.trim() !== current.name;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (dirty && name.trim()) await updateProject({ name: name.trim() });
  };

  return (
    <div className="project-overview">
      {error && (
        <div className="inline-error" role="alert">
          <span>{error}</span>
          <button onClick={clearError}>Dismiss</button>
        </div>
      )}
      <section className="project-banner">
        <div>
          <span className="eyebrow">Project overview</span>
          <h1>{current.name}</h1>
          <p>{current.path}</p>
        </div>
        <button onClick={() => void closeProject()} disabled={loading}>
          Close Project
        </button>
      </section>
      <section className="details-panel">
        <h2>Project details</h2>
        <form onSubmit={(event) => void save(event)}>
          <label>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <button
            className="primary"
            disabled={!dirty || !name.trim() || loading}
          >
            {loading ? "Saving…" : "Save changes"}
          </button>
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
        </form>
        <dl>
          <div>
            <dt>Project version</dt>
            <dd>{current.version}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{new Date(current.created_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Max clip length</dt>
            <dd>{current.settings.max_clip_length_seconds}s</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
