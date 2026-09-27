import { open } from "@tauri-apps/plugin-dialog";
import { type FormEvent, useState } from "react";

import { useProjectStore } from "../stores/projectStore";

export function ProjectLauncher() {
  const { recent, loading, error, createProject, openProject, clearError } =
    useProjectStore();
  const [parentDirectory, setParentDirectory] = useState<string>();
  const [name, setName] = useState("");

  const chooseNewLocation = async () => {
    clearError();
    const directory = await open({
      directory: true,
      multiple: false,
      title: "Project location",
    });
    if (directory) setParentDirectory(directory);
  };

  const chooseExistingProject = async () => {
    clearError();
    const directory = await open({
      directory: true,
      multiple: false,
      title: "Open project",
    });
    if (directory) await openProject(directory);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!parentDirectory || !name.trim()) return;
    await createProject(name.trim(), parentDirectory);
  };

  return (
    <div className="launcher">
      <section className="hero-card launcher__hero">
        <span className="hero-card__icon">⌁</span>
        <span className="eyebrow">Local-first generative video</span>
        <h1>Shape music into motion.</h1>
        <p>
          Create or open a portable Beatweave project. Its database and media
          stay together in the folder you choose.
        </p>
        <div className="hero-card__actions">
          <button
            className="primary"
            onClick={() => void chooseNewLocation()}
            disabled={loading}
          >
            New Project
          </button>
          <button
            onClick={() => void chooseExistingProject()}
            disabled={loading}
          >
            Open Project
          </button>
        </div>
      </section>

      {parentDirectory && (
        <form className="project-form" onSubmit={(event) => void submit(event)}>
          <div>
            <span className="eyebrow">Create project</span>
            <p>{parentDirectory}</p>
          </div>
          <input
            autoFocus
            value={name}
            maxLength={200}
            placeholder="Project name"
            onChange={(event) => setName(event.target.value)}
          />
          <button className="primary" disabled={!name.trim() || loading}>
            {loading ? "Creating…" : "Create"}
          </button>
          <button type="button" onClick={() => setParentDirectory(undefined)}>
            Cancel
          </button>
        </form>
      )}

      {error && (
        <div className="inline-error" role="alert">
          <span>{error}</span>
          <button onClick={clearError}>Dismiss</button>
        </div>
      )}

      <section className="recent-projects">
        <div className="section-heading">
          <span className="eyebrow">Recent projects</span>
          <span>{recent.length}</span>
        </div>
        {recent.length === 0 ? (
          <div className="empty-state">
            Your recently opened projects will appear here.
          </div>
        ) : (
          <div className="recent-projects__list">
            {recent.map((project) => (
              <button
                key={project.id}
                disabled={!project.exists || loading}
                onClick={() => void openProject(project.path)}
              >
                <span className="recent-projects__mark">◇</span>
                <span>
                  <strong>{project.name}</strong>
                  <small>{project.path}</small>
                </span>
                {!project.exists && <em>Missing</em>}
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
