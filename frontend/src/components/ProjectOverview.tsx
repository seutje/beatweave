import { open } from "@tauri-apps/plugin-dialog";
import { type FormEvent, useState } from "react";

import { useProjectStore } from "../stores/projectStore";
import { AudioPlayer } from "./AudioPlayer";

export function ProjectOverview() {
  const {
    current,
    audio,
    loading,
    error,
    closeProject,
    updateProject,
    importAudio,
    clearError,
  } = useProjectStore();
  const [name, setName] = useState(current?.name ?? "");

  if (!current) return null;
  const dirty = name.trim() !== current.name;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (dirty && name.trim()) await updateProject({ name: name.trim() });
  };

  const chooseAudio = async () => {
    const path = await open({
      multiple: false,
      directory: false,
      title: "Import source track",
      filters: [
        {
          name: "Audio",
          extensions: ["wav", "mp3", "flac", "m4a", "aac", "ogg", "opus"],
        },
      ],
    });
    if (path) await importAudio(path);
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
      {audio ? (
        <AudioPlayer audio={audio} />
      ) : (
        <section className="audio-empty">
          <div>
            <span className="eyebrow">Source track</span>
            <h2>Import the music that will drive this project.</h2>
            <p>
              Beatweave copies the source into the project and builds a reusable
              waveform cache.
            </p>
          </div>
          <button
            className="primary"
            onClick={() => void chooseAudio()}
            disabled={loading}
          >
            {loading ? "Importing…" : "Import Audio"}
          </button>
        </section>
      )}
    </div>
  );
}
