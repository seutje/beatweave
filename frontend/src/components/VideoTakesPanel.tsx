import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { AnalysisJob, Scene, SceneVideoTakes } from "../api/types";

interface Props {
  scene: Scene;
  onTimelineRefresh: () => Promise<void>;
}

const TERMINAL_STATES = new Set(["complete", "failed", "cancelled"]);

export function VideoTakesPanel({ scene, onTimelineRefresh }: Props) {
  const [detail, setDetail] = useState<SceneVideoTakes>();
  const [activeJob, setActiveJob] = useState<AnalysisJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

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

  const selected = useMemo(
    () => detail?.takes.find((take) => take.selected),
    [detail],
  );
  const latestFailure = useMemo(
    () => detail?.render_jobs.find((job) => job.state === "failed"),
    [detail],
  );

  const render = async (qualityMode: "preview" | "final") => {
    setBusy(true);
    setError(undefined);
    try {
      const { job } = await api.videoTakes.render(scene.id, qualityMode);
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

  const select = async (takeId: string) => {
    setBusy(true);
    setError(undefined);
    try {
      applyDetail((await api.videoTakes.select(scene.id, takeId)).detail);
      await onTimelineRefresh();
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
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not delete take",
      );
    } finally {
      setBusy(false);
    }
  };

  const working =
    busy || Boolean(activeJob && !TERMINAL_STATES.has(activeJob.state));

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
      </div>
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
              <button
                disabled={busy || take.selected}
                onClick={() => void select(take.id)}
              >
                {take.selected ? "Selected" : "Select"}
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
