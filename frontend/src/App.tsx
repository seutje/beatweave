import { useEffect } from "react";

import { ProjectLauncher } from "./components/ProjectLauncher";
import { ProjectOverview } from "./components/ProjectOverview";
import { useBackend } from "./hooks/useBackend";
import { useProjectStore } from "./stores/projectStore";

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
  const { current, load } = useProjectStore();

  useEffect(() => {
    if (backend.state === "connected") void load();
  }, [backend.state, load]);

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
          <strong>{current?.name ?? "No project open"}</strong>
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
              disabled={!current || index > 0}
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
        {current ? <ProjectOverview /> : <ProjectLauncher />}
      </main>
    </div>
  );
}
