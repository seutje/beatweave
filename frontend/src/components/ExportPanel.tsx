import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { AnalysisJob, ExportReadiness } from "../api/types";
import { formatTime } from "../lib/audioPlayback";

const wait = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function ExportPanel({ projectName }: { projectName: string }) {
  const [readiness, setReadiness] = useState<ExportReadiness>();
  const [filename, setFilename] = useState(
    `${projectName.replace(/[^a-z0-9_-]+/gi, "-")}-final.mp4`,
  );
  const [codec, setCodec] = useState<"h264" | "h265">("h264");
  const [crf, setCrf] = useState(18);
  const [job, setJob] = useState<AnalysisJob>();
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    setReadiness(await api.exports.readiness());
  }, []);

  useEffect(() => {
    let active = true;
    void api.exports
      .readiness()
      .then((value) => {
        if (active) setReadiness(value);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not validate export",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const start = async () => {
    setError(undefined);
    try {
      let current = (
        await api.exports.start({
          filename,
          codec,
          crf,
          frame_rate: 24,
          width: 1920,
          height: 1080,
        })
      ).job;
      setJob(current);
      while (!["complete", "failed", "cancelled"].includes(current.state)) {
        await wait(500);
        current = await api.jobs.get(current.id);
        setJob(current);
      }
      if (current.state === "failed") {
        setError(current.error?.message ?? "Export failed");
      }
      await refresh();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not start export",
      );
    }
  };

  const reveal = async () => {
    const assetId = job?.output.asset_id;
    if (typeof assetId !== "string") return;
    try {
      const { path } = await api.media.assetLocation(assetId);
      await invoke("reveal_file", { path });
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not reveal export",
      );
    }
  };

  const working =
    job && !["complete", "failed", "cancelled"].includes(job.state);

  return (
    <section className="details-panel export-panel">
      <div className="llm-settings__heading">
        <div>
          <span className="eyebrow">Final assembly</span>
          <h2>Export selected sequence</h2>
        </div>
        <span className={`provider-kind ${readiness?.ready ? "is-ready" : ""}`}>
          {readiness?.ready ? "Ready" : "Needs attention"}
        </span>
      </div>
      {readiness && (
        <p className="panel-description">
          {readiness.scene_count} scenes ·{" "}
          {formatTime(readiness.duration_seconds)} · original soundtrack
        </p>
      )}
      {readiness?.issues.length ? (
        <ul className="export-issues">
          {readiness.issues.map((issue, index) => (
            <li key={`${issue.code}-${issue.scene_id ?? index}`}>
              {issue.message}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="export-options">
        <label>
          Filename
          <input
            value={filename}
            onChange={(event) => setFilename(event.target.value)}
          />
        </label>
        <label>
          Codec
          <select
            value={codec}
            onChange={(event) =>
              setCodec(event.target.value as "h264" | "h265")
            }
          >
            <option value="h264">H.264 (compatible)</option>
            <option value="h265">H.265 (smaller)</option>
          </select>
        </label>
        <label>
          Quality (CRF)
          <input
            type="number"
            min="12"
            max="35"
            value={crf}
            onChange={(event) => setCrf(Number(event.target.value))}
          />
        </label>
      </div>
      {working && (
        <div className="video-render-progress" role="status">
          <span>{job.state}</span>
          <progress value={job.progress} max={1} />
          <strong>{Math.round(job.progress * 100)}%</strong>
        </div>
      )}
      <div className="llm-settings__actions">
        <button
          className="primary"
          disabled={!readiness?.ready || Boolean(working) || !filename.trim()}
          onClick={() => void start()}
        >
          Export 1080p
        </button>
        <button
          disabled={job?.state !== "complete"}
          onClick={() => void reveal()}
        >
          Open export location
        </button>
        <button disabled={Boolean(working)} onClick={() => void refresh()}>
          Recheck
        </button>
      </div>
      {error && <p className="keyframe-error">{error}</p>}
      {job?.state === "complete" && (
        <p className="settings-message">Export completed successfully.</p>
      )}
    </section>
  );
}
