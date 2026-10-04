import { useCallback, useEffect, useState } from "react";

import { ExportPanel } from "./components/ExportPanel";
import { ProjectLauncher } from "./components/ProjectLauncher";
import { ProjectOverview } from "./components/ProjectOverview";
import { RenderQueue } from "./components/RenderQueue";
import { SettingsWorkspace } from "./components/SettingsWorkspace";
import { TimelineWorkspace } from "./components/TimelineWorkspace";
import { useBackend } from "./hooks/useBackend";
import { isEditableTarget } from "./lib/interactions";
import { useProjectStore } from "./stores/projectStore";
import { useTimelineStore } from "./stores/timelineStore";

type View = "Overview" | "Timeline" | "Renders" | "Export" | "Settings";
const navigation: { label: View; icon: string; shortcut: string }[] = [
  { label: "Overview", icon: "◇", shortcut: "Alt+1" },
  { label: "Timeline", icon: "≡", shortcut: "Alt+2" },
  { label: "Renders", icon: "▷", shortcut: "Alt+3" },
  { label: "Export", icon: "↑", shortcut: "Alt+4" },
  { label: "Settings", icon: "⚙", shortcut: "Alt+5" },
];

export function App() {
  const backend = useBackend();
  const { current, load } = useProjectStore();
  const timelineLoading = useTimelineStore((state) => state.loading);
  const currentProjectId = current?.id;
  const [activeView, setActiveView] = useState<View>("Overview");
  const [timelineProjectId, setTimelineProjectId] = useState<string>();
  const [showShortcuts, setShowShortcuts] = useState(false);

  const navigate = useCallback(
    (view: View) => {
      if (view !== "Overview" && !currentProjectId) return;
      if (view === "Timeline") setTimelineProjectId(currentProjectId);
      setActiveView(view);
    },
    [currentProjectId],
  );

  useEffect(() => {
    if (backend.state === "connected") void load();
  }, [backend.state, load]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      if (event.key === "?") setShowShortcuts((value) => !value);
      if (event.altKey && ["1", "2", "3", "4", "5"].includes(event.key)) {
        event.preventDefault();
        navigate(navigation[Number(event.key) - 1].label);
      }
      if (event.key === "Escape") setShowShortcuts(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);

  return (
    <div className={`app-shell app-shell--${activeView.toLowerCase()}`}>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">⌁</span>
          <strong>Beatweave</strong>
          <small>v0.3.7</small>
        </div>
        <div className="topbar__project">
          <span>Project</span>
          <div className="topbar__project-title">
            <strong>{current?.name ?? "No project open"}</strong>
            {timelineLoading && (
              <span className="topbar__timeline-busy" role="status">
                <span className="spinner" /> Updating timeline…
              </span>
            )}
          </div>
        </div>
        <div className={`status status--${backend.state}`}>
          <span className="status__dot" />
          Backend {backend.state}
        </div>
      </header>

      <aside className="sidebar">
        <span className="eyebrow">Workspace</span>
        <nav>
          {navigation.map((item) => (
            <button
              className={item.label === activeView ? "active" : ""}
              disabled={!current}
              key={item.label}
              onClick={() => navigate(item.label)}
              title={`${item.label} (${item.shortcut})`}
            >
              <span>{item.icon}</span>
              {item.label}
              <kbd>{item.shortcut.replace("Alt+", "")}</kbd>
            </button>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="eyebrow">Local services</span>
          <p>
            <span className={`status__dot status__dot--${backend.state}`} />{" "}
            FastAPI
          </p>
          <button
            className="shortcut-help"
            onClick={() => setShowShortcuts(true)}
          >
            <kbd>?</kbd> Shortcuts
          </button>
        </div>
      </aside>

      <main className={`workspace workspace--${activeView.toLowerCase()}`}>
        {backend.state === "connecting" && (
          <section className="loading-card" role="status">
            <span className="spinner" /> Starting the local Beatweave service…
          </section>
        )}
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
        {backend.state !== "connecting" &&
          (current ? (
            <>
              {activeView === "Overview" && (
                <ProjectOverview onNavigate={navigate} />
              )}
              {timelineProjectId === current.id && (
                <div hidden={activeView !== "Timeline"}>
                  <TimelineWorkspace active={activeView === "Timeline"} />
                </div>
              )}
              {activeView === "Renders" && <RenderQueue />}
              {activeView === "Export" && (
                <div className="export-workspace">
                  <ExportPanel projectName={current.name} />
                </div>
              )}
              {activeView === "Settings" && <SettingsWorkspace />}
            </>
          ) : (
            <ProjectLauncher />
          ))}
      </main>
      {showShortcuts && (
        <div className="modal-backdrop" onClick={() => setShowShortcuts(false)}>
          <section
            className="shortcut-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="section-heading">
              <div>
                <span className="eyebrow">Keyboard</span>
                <h2>Shortcuts</h2>
              </div>
              <button
                onClick={() => setShowShortcuts(false)}
                aria-label="Close shortcuts"
              >
                ×
              </button>
            </div>
            <dl>
              <div>
                <dt>Play / pause</dt>
                <dd>
                  <kbd>Space</kbd>
                </dd>
              </div>
              <div>
                <dt>Split selected scene</dt>
                <dd>
                  <kbd>S</kbd>
                </dd>
              </div>
              <div>
                <dt>Delete selected scene</dt>
                <dd>
                  <kbd>Delete</kbd>
                </dd>
              </div>
              <div>
                <dt>Undo / redo</dt>
                <dd>
                  <kbd>Ctrl Z</kbd> <kbd>Ctrl Shift Z</kbd>
                </dd>
              </div>
              <div>
                <dt>Move playhead</dt>
                <dd>
                  <kbd>←</kbd> <kbd>→</kbd>
                </dd>
              </div>
              <div>
                <dt>Switch workspace</dt>
                <dd>
                  <kbd>Alt 1–5</kbd>
                </dd>
              </div>
              <div>
                <dt>Bypass snapping</dt>
                <dd>
                  <kbd>Alt</kbd> + drag
                </dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </div>
  );
}
