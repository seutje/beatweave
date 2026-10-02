import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { connectToEvents } from "../api/events";
import type { AnalysisJob, ExportReadiness } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import { trackedJobFromEvent } from "./exportJobTracking";
import { EXPORT_PRESETS, type ExportPreset } from "./exportPresets";

const terminalStates = new Set(["complete", "failed", "cancelled"]);

export function ExportPanel({ projectName }: { projectName: string }) {
  const [readiness, setReadiness] = useState<ExportReadiness>();
  const [filename, setFilename] = useState(
    `${projectName.replace(/[^a-z0-9_-]+/gi, "-")}-final.mp4`,
  );
  const [codec, setCodec] = useState<"h264" | "h265">("h264");
  const [preset, setPreset] = useState<ExportPreset>("1080p");
  const [crf, setCrf] = useState<number>(EXPORT_PRESETS["1080p"].crf);
  const [job, setJob] = useState<AnalysisJob>();
  const [error, setError] = useState<string>();
  const jobId = job?.id;
  const jobState = job?.state;

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

  useEffect(() => {
    if (!jobId || !jobState || terminalStates.has(jobState)) return;

    let active = true;
    const synchronize = async () => {
      try {
        const current = await api.jobs.get(jobId);
        if (!active) return;
        setJob(current);
        if (current.state === "failed") {
          setError(current.error?.message ?? "Export failed");
        }
        if (terminalStates.has(current.state)) await refresh();
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not refresh export progress",
          );
        }
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void synchronize();
    };
    const disconnect = connectToEvents(
      (event) => {
        const current = trackedJobFromEvent(event, jobId);
        if (!current || !active) return;
        setJob(current);
        if (current.state === "failed") {
          setError(current.error?.message ?? "Export failed");
        }
        if (terminalStates.has(current.state)) void refresh();
      },
      (connected) => {
        if (connected) void synchronize();
      },
    );
    const pollId = window.setInterval(() => void synchronize(), 1500);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", synchronize);
    void synchronize();
    return () => {
      active = false;
      disconnect();
      window.clearInterval(pollId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", synchronize);
    };
  }, [jobId, jobState, refresh]);

  const start = async () => {
    setError(undefined);
    try {
      const exportProfile = EXPORT_PRESETS[preset];
      const current = (
        await api.exports.start({
          filename,
          codec,
          crf,
          frame_rate: 24,
          width: exportProfile.width,
          height: exportProfile.height,
        })
      ).job;
      setJob(current);
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
    job && !terminalStates.has(job.state);

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
          Resolution
          <select
            value={preset}
            onChange={(event) => {
              const nextPreset = event.target.value as ExportPreset;
              setPreset(nextPreset);
              setCrf(EXPORT_PRESETS[nextPreset].crf);
            }}
          >
            <option value="1080p">1080p (1920×1080)</option>
            <option value="4k">4K UHD (3840×2160)</option>
          </select>
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
          <small>
            Lower is higher quality. The 4K preset uses CRF 16; 1080p uses CRF
            18.
          </small>
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
          Export {EXPORT_PRESETS[preset].label}
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
