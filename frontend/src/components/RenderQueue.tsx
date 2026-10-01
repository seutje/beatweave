import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AnalysisJob } from "../api/types";

type Filter = "active" | "all" | "failed";
const activeStates = new Set(["queued", "preparing", "running"]);

export function RenderQueue() {
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [filter, setFilter] = useState<Filter>("active");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setJobs(await api.jobs.list());
      setError(undefined);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not load jobs",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialId = window.setTimeout(() => void load(), 0);
    const id = window.setInterval(() => void load(), 1500);
    return () => {
      window.clearTimeout(initialId);
      window.clearInterval(id);
    };
  }, [load]);

  const visible = useMemo(
    () =>
      jobs.filter(
        (job) =>
          filter === "all" ||
          (filter === "active"
            ? activeStates.has(job.state)
            : job.state === "failed"),
      ),
    [filter, jobs],
  );
  const retry = async (id: string) => {
    try {
      await api.jobs.retry(id);
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not retry the job",
      );
    }
  };
  const cancel = async (id: string) => {
    try {
      await api.jobs.cancel(id);
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not cancel the job",
      );
    }
  };

  return (
    <div className="render-queue">
      <header className="render-queue__header">
        <div>
          <span className="eyebrow">Render queue</span>
          <h1>Jobs &amp; progress</h1>
          <p>
            Rendering continues in the background. Completed and failed work
            stays inspectable.
          </p>
        </div>
        <button onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </header>
      <div className="queue-filters" role="group" aria-label="Job filters">
        {(["active", "all", "failed"] as const).map((value) => (
          <button
            key={value}
            className={filter === value ? "active" : ""}
            onClick={() => setFilter(value)}
          >
            {value}{" "}
            {value === "all"
              ? jobs.length
              : jobs.filter((job) =>
                  value === "active"
                    ? activeStates.has(job.state)
                    : job.state === "failed",
                ).length}
          </button>
        ))}
      </div>
      {error && (
        <div className="inline-error" role="alert">
          <span>{error}</span>
          <button onClick={() => void load()}>Try again</button>
        </div>
      )}
      {loading ? (
        <div className="loading-card">
          <span className="spinner" /> Loading render history…
        </div>
      ) : visible.length === 0 ? (
        <div className="empty-state empty-state--large">
          <strong>No {filter === "all" ? "" : filter} jobs</strong>
          <span>
            {filter === "active"
              ? "New renders will appear here with live progress."
              : "There is nothing to show in this view."}
          </span>
        </div>
      ) : (
        <div className="queue-list">
          {visible.map((job) => (
            <article key={job.id} className={`job-card is-${job.state}`}>
              <div className="job-card__main">
                <span className="job-state">{job.state}</span>
                <div>
                  <strong>{job.type.replaceAll("_", " ")}</strong>
                  <small>
                    {job.backend ?? "Beatweave"} ·{" "}
                    {new Date(job.created_at).toLocaleString()}
                  </small>
                </div>
              </div>
              <div className="job-card__progress">
                <progress value={job.progress} max={1} />
                <span>{Math.round(job.progress * 100)}%</span>
              </div>
              {job.error && (
                <p>
                  <strong>{job.error.code}</strong> {job.error.message}
                </p>
              )}
              {job.state === "failed" && (
                <button onClick={() => void retry(job.id)}>
                  Retry as new job
                </button>
              )}
              {activeStates.has(job.state) && (
                <button onClick={() => void cancel(job.id)}>Cancel</button>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
