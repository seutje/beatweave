import { open } from "@tauri-apps/plugin-dialog";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  AnalysisJob,
  ApplicationLogs,
  ProjectIntegrityReport,
} from "../api/types";

interface ServiceDiagnostic {
  name: string;
  available: boolean;
  message: string;
}

export function ReliabilityPanel() {
  const [integrity, setIntegrity] = useState<ProjectIntegrityReport>();
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [logs, setLogs] = useState<ApplicationLogs>();
  const [services, setServices] = useState<ServiceDiagnostic[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const load = useCallback(async (verifyHashes = false) => {
    setBusy(true);
    setError(undefined);
    try {
      const [report, recentJobs, recentLogs, comfyui, wan2gp, llm] =
        await Promise.all([
          api.projects.integrity(verifyHashes),
          api.jobs.list(),
          api.diagnostics.logs(),
          api.comfyui.test(),
          api.wan2gp.test(),
          api.llm.test(),
        ]);
      setIntegrity(report);
      setJobs(recentJobs);
      setLogs(recentLogs);
      setServices([
        {
          name: "ComfyUI",
          available: comfyui.available && comfyui.profile_ready,
          message: comfyui.message,
        },
        {
          name: "Wan2GP",
          available: wan2gp.available && wan2gp.profile_ready,
          message: wan2gp.message,
        },
        { name: "LLM", available: llm.available, message: llm.message },
      ]);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Diagnostics could not run",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  const backup = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.projects.backup();
      setMessage(`Backup created: ${result.path}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Backup failed");
    } finally {
      setBusy(false);
    }
  };

  const relink = async (assetId: string) => {
    const path = await open({
      multiple: false,
      directory: false,
      title: "Locate the original media file",
    });
    if (!path) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.projects.relinkAsset(assetId, path);
      setMessage("Media restored to its managed project location.");
      setIntegrity(await api.projects.integrity());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Relink failed");
    } finally {
      setBusy(false);
    }
  };

  const retry = async (jobId: string) => {
    setBusy(true);
    setError(undefined);
    try {
      const { job } = await api.jobs.retry(jobId);
      setJobs((current) => [job, ...current]);
      setMessage(
        "A new retry job was queued; the failed job remains in history.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  };

  const failedJobs = jobs.filter(
    (job) => job.state === "failed" || job.state === "cancelled",
  );

  return (
    <section className="reliability-panel">
      <div className="reliability-panel__heading">
        <div>
          <span className="eyebrow">Recovery &amp; diagnostics</span>
          <h2>Project health</h2>
          <p>
            Beatweave checkpoints edits continuously and keeps rotating database
            snapshots in the project folder.
          </p>
        </div>
        <div className="reliability-panel__actions">
          <button onClick={() => void load(true)} disabled={busy}>
            {busy ? "Checking…" : "Run checks"}
          </button>
          <button
            className="primary"
            onClick={() => void backup()}
            disabled={busy}
          >
            Create backup
          </button>
        </div>
      </div>

      {error && <div className="inline-error">{error}</div>}
      {message && <p className="reliability-panel__message">{message}</p>}

      <div className="reliability-panel__grid">
        <div>
          <h3>Integrity</h3>
          <strong className={integrity?.ok ? "health-ok" : "health-error"}>
            {integrity
              ? integrity.ok
                ? "Healthy"
                : "Needs attention"
              : "Checking…"}
          </strong>
          <small>
            {integrity
              ? `${integrity.asset_count} assets · schema ${integrity.schema_version}`
              : "Database and managed files"}
          </small>
        </div>
        <div>
          <h3>Render services</h3>
          {services.map((service) => (
            <p key={service.name} title={service.message}>
              <span
                className={`status__dot status__dot--${service.available ? "connected" : "offline"}`}
              />{" "}
              {service.name}: {service.available ? "ready" : "offline"}
            </p>
          ))}
        </div>
      </div>

      {integrity && integrity.issues.length > 0 && (
        <div className="diagnostic-list">
          {integrity.issues.map((issue, index) => (
            <div key={`${issue.code}-${issue.asset_id ?? index}`}>
              <span className={`diagnostic-list__${issue.severity}`}>
                {issue.severity}
              </span>
              <span>
                <strong>{issue.message}</strong>
                {issue.path && <small>{issue.path}</small>}
              </span>
              {issue.code === "asset_file_missing" && issue.asset_id && (
                <button
                  onClick={() => void relink(issue.asset_id!)}
                  disabled={busy}
                >
                  Relink
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {failedJobs.length > 0 && (
        <div className="failed-jobs">
          <h3>Retryable jobs</h3>
          {failedJobs.slice(0, 8).map((job) => (
            <div key={job.id}>
              <span>
                <strong>{job.type.replaceAll("_", " ")}</strong>
                <small>{job.error?.message ?? job.state}</small>
              </span>
              <button onClick={() => void retry(job.id)} disabled={busy}>
                Retry
              </button>
            </div>
          ))}
        </div>
      )}

      <details className="application-logs">
        <summary>
          Application log ({logs?.entries.length ?? 0} recent entries)
        </summary>
        <a href={api.diagnostics.logExportUrl} download>
          Export full log
        </a>
        <div>
          {logs?.entries.slice(-20).map((entry, index) => (
            <p key={`${entry.timestamp}-${index}`}>
              <time>{new Date(entry.timestamp).toLocaleTimeString()}</time>
              <strong>{entry.level}</strong>
              <span>{entry.message}</span>
            </p>
          ))}
        </div>
      </details>
    </section>
  );
}
