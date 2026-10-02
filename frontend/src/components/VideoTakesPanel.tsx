import { open } from "@tauri-apps/plugin-dialog";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AnalysisJob, Scene, SceneVideoTakes } from "../api/types";

interface Props {
  scene: Scene;
  scenes: Scene[];
  onTimelineRefresh: () => Promise<void>;
}

const TERMINAL_STATES = new Set(["complete", "failed", "cancelled"]);
const notifyTimeline = () =>
  window.dispatchEvent(new Event("beatweave:video-takes-changed"));

export function VideoTakesPanel({ scene, scenes, onTimelineRefresh }: Props) {
  const [detail, setDetail] = useState<SceneVideoTakes>();
  const [activeJob, setActiveJob] = useState<AnalysisJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [comparison, setComparison] = useState<string[]>([]);
  const [batchJobIds, setBatchJobIds] = useState<string[]>([]);
  const [batchProgress, setBatchProgress] = useState<string>();

  const applyDetail = useCallback((value: SceneVideoTakes) => {
    setDetail(value);
    setActiveJob(
      value.render_jobs.find((job) => !TERMINAL_STATES.has(job.state)),
    );
  }, []);

  const load = useCallback(async () => {
    applyDetail(await api.videoTakes.detail(scene.id));
  }, [applyDetail, scene.id]);

  useEffect(() => {
    let active = true;
    api.videoTakes
      .detail(scene.id)
      .then((value) => {
        if (active) applyDetail(value);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load video takes",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [applyDetail, scene.id]);

  useEffect(() => {
    if (!activeJob || TERMINAL_STATES.has(activeJob.state)) return;
    let active = true;
    const poll = window.setInterval(() => {
      void api.jobs
        .get(activeJob.id)
        .then(async (job) => {
          if (!active) return;
          setActiveJob(job);
          if (TERMINAL_STATES.has(job.state)) {
            window.clearInterval(poll);
            if (job.state === "failed") {
              setError(job.error?.message ?? "Video render failed");
            }
            await load();
            await onTimelineRefresh();
            notifyTimeline();
          }
        })
        .catch((reason: unknown) => {
          if (active) {
            setError(
              reason instanceof Error
                ? reason.message
                : "Could not read render job",
            );
          }
        });
    }, 750);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [activeJob, load, onTimelineRefresh]);

  useEffect(() => {
    if (batchJobIds.length === 0) return;
    let active = true;
    const poll = window.setInterval(() => {
      void Promise.all(batchJobIds.map((id) => api.jobs.get(id)))
        .then(async (jobs) => {
          if (!active) return;
          const complete = jobs.filter((job) =>
            TERMINAL_STATES.has(job.state),
          ).length;
          setBatchProgress(`Rendering ${complete} of ${jobs.length} clips…`);
          if (complete === jobs.length) {
            window.clearInterval(poll);
            const failure = jobs.find((job) => job.state === "failed");
            if (failure) {
              setError(failure.error?.message ?? "A video render failed");
            }
            setBatchJobIds([]);
            setBatchProgress(undefined);
            await load();
            await onTimelineRefresh();
            notifyTimeline();
          }
        })
        .catch((reason: unknown) => {
          if (active) {
            setError(
              reason instanceof Error
                ? reason.message
                : "Could not read batch render jobs",
            );
          }
        });
    }, 750);
    return () => {
      active = false;
      window.clearInterval(poll);
    };
  }, [batchJobIds, load, onTimelineRefresh]);

  const selected = useMemo(
    () => detail?.takes.find((take) => take.selected),
    [detail],
  );
  const latestFailure = useMemo(
    () => detail?.render_jobs.find((job) => job.state === "failed"),
    [detail],
  );

  const render = async (
    qualityMode: "preview" | "final",
    sourceTakeId?: string,
  ) => {
    setBusy(true);
    setError(undefined);
    try {
      const { job } = await api.videoTakes.render(
        scene.id,
        qualityMode,
        sourceTakeId,
      );
      setActiveJob(job);
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not start render",
      );
    } finally {
      setBusy(false);
    }
  };

  const renderAll = async () => {
    const targets = [...scenes]
      .sort((left, right) => left.position - right.position)
      .filter((item) => item.position >= scene.position);
    setBusy(true);
    setError(undefined);
    const queued: string[] = [];
    try {
      for (const target of targets) {
        const { job } = await api.videoTakes.render(
          target.id,
          "final",
          undefined,
          true,
        );
        queued.push(job.id);
      }
      setBatchJobIds(queued);
      setBatchProgress(`Rendering 0 of ${queued.length} clips…`);
    } catch (reason) {
      if (queued.length > 0) {
        setBatchJobIds(queued);
        setBatchProgress(`Rendering 0 of ${queued.length} queued clips…`);
      }
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not queue all video renders",
      );
    } finally {
      setBusy(false);
    }
  };

  const select = async (takeId: string) => {
    setBusy(true);
    setError(undefined);
    try {
      applyDetail((await api.videoTakes.select(scene.id, takeId)).detail);
      await onTimelineRefresh();
      notifyTimeline();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not select take",
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (takeId: string) => {
    if (!window.confirm("Delete this generated video take permanently?"))
      return;
    setBusy(true);
    setError(undefined);
    try {
      applyDetail(await api.videoTakes.delete(scene.id, takeId));
      await onTimelineRefresh();
      notifyTimeline();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not delete take",
      );
    } finally {
      setBusy(false);
    }
  };

  const importVideo = async () => {
    const path = await open({
      multiple: false,
      title: "Use video for scene",
      filters: [{ name: "Videos", extensions: ["mp4", "mov", "mkv", "webm"] }],
    });
    if (typeof path !== "string") return;
    setBusy(true);
    setError(undefined);
    try {
      applyDetail(await api.videoTakes.import(scene.id, path));
      await onTimelineRefresh();
      notifyTimeline();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not import video",
      );
    } finally {
      setBusy(false);
    }
  };

  const working =
    busy ||
    batchJobIds.length > 0 ||
    Boolean(activeJob && !TERMINAL_STATES.has(activeJob.state));

  return (
    <section className="video-takes" aria-label="Video takes">
      <div className="video-takes__heading">
        <div>
          <span className="eyebrow">Wan2GP</span>
          <h3>Video takes</h3>
        </div>
        {selected?.stale && <span className="take-status is-stale">Stale</span>}
      </div>
      <div className="video-takes__actions">
        <button
          className="primary"
          disabled={working || !scene.video_prompt.trim()}
          onClick={() => void render("preview")}
        >
          Render preview
        </button>
        <button
          disabled={working || !scene.video_prompt.trim()}
          onClick={() => void render("final")}
        >
          Render final 1080p
        </button>
        <button
          disabled={working || !scene.video_prompt.trim()}
          onClick={() => void renderAll()}
        >
          Render all
        </button>
        <button disabled={working} onClick={() => void importVideo()}>
          Use video file
        </button>
      </div>
      {batchProgress && (
        <div className="video-render-progress" role="status">
          <span>{batchProgress}</span>
        </div>
      )}
      {activeJob && !TERMINAL_STATES.has(activeJob.state) && (
        <div className="video-render-progress" role="status">
          <span>{activeJob.state.replace("_", " ")}</span>
          <progress value={activeJob.progress} max={1} />
          <strong>{Math.round(activeJob.progress * 100)}%</strong>
        </div>
      )}
      {selected && (
        <video
          className="video-takes__player"
          src={api.media.assetContentUrl(selected.asset_id)}
          controls
          preload="metadata"
        />
      )}
      {comparison.length > 0 && (
        <div className="take-comparison" aria-label="Video take comparison">
          <div>
            <strong>A/B comparison</strong>
            <button onClick={() => setComparison([])}>Clear</button>
          </div>
          <div>
            {comparison.map((id, index) => {
              const take = detail?.takes.find((item) => item.id === id);
              return take ? (
                <figure key={id}>
                  <span>{index === 0 ? "A" : "B"}</span>
                  <video
                    src={api.media.assetContentUrl(take.asset_id)}
                    controls
                    muted
                    preload="metadata"
                  />
                  <figcaption>
                    {String(take.backend_settings.quality_mode ?? "take")} ·{" "}
                    {String(take.backend_settings.resolution ?? "")}
                  </figcaption>
                </figure>
              ) : null;
            })}
          </div>
        </div>
      )}
      {error && <p className="keyframe-error">{error}</p>}
      {latestFailure?.error && (
        <details className="keyframe-failure">
          <summary>Latest render failure</summary>
          <strong>{latestFailure.error.code}</strong>
          <p>{latestFailure.error.message}</p>
        </details>
      )}
      <div className="video-takes__list">
        {detail?.takes.map((take) => (
          <article key={take.id} className={take.selected ? "is-selected" : ""}>
            <div>
              <strong>
                {String(take.backend_settings.quality_mode ?? "take")}
                {take.stale ? " - stale" : ""}
              </strong>
              <small>{new Date(take.created_at).toLocaleString()}</small>
              <small>{String(take.backend_settings.resolution ?? "")}</small>
              <small>
                {take.backend_settings.audio_conditioning
                  ? "Soundtrack conditioned"
                  : "No soundtrack conditioning"}
              </small>
            </div>
            <div>
              {take.backend_settings.quality_mode === "preview" &&
                !take.stale && (
                  <button
                    disabled={working}
                    onClick={() => void render("final", take.id)}
                  >
                    Render final
                  </button>
                )}
              <button
                disabled={busy || take.selected}
                onClick={() => void select(take.id)}
              >
                {take.selected ? "Selected" : "Select"}
              </button>
              <button
                className={comparison.includes(take.id) ? "is-comparing" : ""}
                disabled={busy}
                onClick={() =>
                  setComparison((current) =>
                    current.includes(take.id)
                      ? current.filter((id) => id !== take.id)
                      : [...current.slice(-1), take.id],
                  )
                }
                title="Place this take in the A/B comparison"
              >
                {comparison.includes(take.id)
                  ? comparison.indexOf(take.id) === 0
                    ? "A"
                    : "B"
                  : "Compare"}
              </button>
              <button disabled={busy} onClick={() => void remove(take.id)}>
                Delete
              </button>
            </div>
          </article>
        ))}
        {detail?.takes.length === 0 && (
          <p className="panel-description">No video takes yet.</p>
        )}
      </div>
    </section>
  );
}
