import { useBackend } from "./hooks/useBackend";

const navigation = [
  "Overview",
  "Timeline",
  "Scenes",
  "Keyframes",
  "Renders",
  "Prompts",
];

export function App() {
  const backend = useBackend();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">⌁</span>
          <strong>Beatweave</strong>
          <small>v0.1.0</small>
        </div>
        <div className="topbar__project">
          <span>Project</span>
          <strong>No project open</strong>
        </div>
        <div className={`status status--${backend.state}`}>
          <span className="status__dot" />
          Backend {backend.state}
        </div>
      </header>

      <aside className="sidebar">
        <span className="eyebrow">Workspace</span>
        <nav>
          {navigation.map((item, index) => (
            <button
              className={index === 0 ? "active" : ""}
              disabled={index > 0}
              key={item}
            >
              <span>{index === 0 ? "◇" : "·"}</span>
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="eyebrow">Local services</span>
          <p>
            <span className={`status__dot status__dot--${backend.state}`} />{" "}
            FastAPI
          </p>
        </div>
      </aside>

      <main className="workspace">
        {backend.state === "offline" && (
          <section className="connection-alert" role="alert">
            <div>
              <strong>Backend connection failed</strong>
              <p>
                {backend.error}. Beatweave will keep your local project files
                untouched.
              </p>
            </div>
            <button onClick={() => void backend.retry()}>Retry</button>
          </section>
        )}

        <section className="hero-card">
          <span className="hero-card__icon">⌁</span>
          <span className="eyebrow">Local-first generative video</span>
          <h1>Shape music into motion.</h1>
          <p>
            Create or open a project to start building a beat-aware visual
            timeline with shared keyframes and editable prompts.
          </p>
          <div className="hero-card__actions">
            <button className="primary" disabled>
              New Project
            </button>
            <button disabled>Open Project</button>
          </div>
          <small>
            {backend.health
              ? `Backend ${backend.health.version} ready`
              : "Waiting for the local backend"}
          </small>
        </section>

        <section className="foundation-grid">
          <article>
            <span>01</span>
            <h2>Import a track</h2>
            <p>Source audio and waveform tools arrive in Phase 3.</p>
          </article>
          <article>
            <span>02</span>
            <h2>Analyze rhythm</h2>
            <p>Real beat timestamps and energy drive the timeline.</p>
          </article>
          <article>
            <span>03</span>
            <h2>Build the visual arc</h2>
            <p>Chained keyframes keep every scene connected.</p>
          </article>
        </section>
      </main>
    </div>
  );
}
