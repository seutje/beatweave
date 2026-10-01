import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import type { Keyframe, KeyframeDetail, Timeline } from "../api/types";
import { formatTime } from "../lib/audioPlayback";

interface Props {
  keyframe: Keyframe;
  shared: boolean;
  onTimeline: (timeline: Timeline) => void;
}

const wait = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function KeyframeInspector({ keyframe, shared, onTimeline }: Props) {
  const [detail, setDetail] = useState<KeyframeDetail>();
  const [prompt, setPrompt] = useState(keyframe.prompt);
  const [globalStyle, setGlobalStyle] = useState(true);
  const [previousInfluence, setPreviousInfluence] = useState<
    "off" | "semantic" | "structural"
  >("semantic");
  const [lockSeed, setLockSeed] = useState(false);
  const [seed, setSeed] = useState(0);
  const [references, setReferences] = useState<string[]>([]);
  const [comparison, setComparison] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    const value = await api.keyframes.detail(keyframe.id);
    setDetail(value);
    setPrompt(value.keyframe.prompt);
  }, [keyframe.id]);

  useEffect(() => {
    let active = true;
    api.keyframes
      .detail(keyframe.id)
      .then((value) => {
        if (!active) return;
        setDetail(value);
        setPrompt(value.keyframe.prompt);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load keyframe",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [keyframe.id]);

  const latestFailure = useMemo(
    () => detail?.render_jobs.find((job) => job.state === "failed"),
    [detail],
  );

  const generate = async (qualityMode: "preview" | "final") => {
    setBusy(true);
    setError(undefined);
    try {
      const { job: created } = await api.keyframes.generate(keyframe.id, {
        prompt,
        include_global_style_references: globalStyle,
        include_previous_keyframe: previousInfluence !== "off",
        additional_reference_asset_ids: references,
        reference_mode:
          previousInfluence === "structural" ? "structural" : "semantic",
        quality_mode: qualityMode,
        ...(lockSeed ? { seed } : {}),
      });
      let job = created;
      while (!["complete", "failed", "cancelled"].includes(job.state)) {
        await wait(500);
        job = await api.jobs.get(job.id);
      }
      if (job.state !== "complete") {
        throw new Error(job.error?.message ?? `Render ${job.state}`);
      }
      await load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Keyframe generation failed",
      );
      await load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const select = async (variantId: string, confirm = false) => {
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.keyframes.select(
        keyframe.id,
        variantId,
        confirm,
      );
      setDetail(result.detail);
      onTimeline(result.timeline);
    } catch (reason) {
      if (
        reason instanceof ApiError &&
        reason.code === "keyframe_variant_affects_renders" &&
        window.confirm(
          "This keyframe is shared by adjacent scenes with rendered video. Switch variants and mark those takes stale?",
        )
      ) {
        await select(variantId, true);
        return;
      }
      setError(
        reason instanceof Error ? reason.message : "Could not select variant",
      );
    } finally {
      setBusy(false);
    }
  };

  const reveal = async (assetId: string) => {
    try {
      const { path } = await api.media.assetLocation(assetId);
      await invoke("reveal_file", { path });
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not open file location",
      );
    }
  };

  return (
    <>
      <h2>Keyframe</h2>
      <dl>
        <dt>Time</dt>
        <dd>{formatTime(keyframe.time)}</dd>
        <dt>Shared</dt>
        <dd>{shared ? "Both adjacent scenes" : "Track edge"}</dd>
        <dt>Variants</dt>
        <dd>{detail?.variants.length ?? 0}</dd>
      </dl>
      <div className="keyframe-generator">
        <label>
          Image prompt
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
        </label>
        <label className="keyframe-generator__check">
          <input
            type="checkbox"
            checked={globalStyle}
            onChange={(event) => setGlobalStyle(event.target.checked)}
          />
          Include global style references
        </label>
        <label>
          Previous keyframe influence
          <select
            value={previousInfluence}
            onChange={(event) =>
              setPreviousInfluence(
                event.target.value as "off" | "semantic" | "structural",
              )
            }
          >
            <option value="off">Off — new composition</option>
            <option value="semantic">Light continuity (recommended)</option>
            <option value="structural">Strong structural match</option>
          </select>
        </label>
        <label className="keyframe-generator__check">
          <input
            type="checkbox"
            checked={lockSeed}
            onChange={(event) => setLockSeed(event.target.checked)}
          />
          Lock seed for reproducible variants
        </label>
        {lockSeed && (
          <label>
            Seed
            <input
              type="number"
              min={0}
              max={Number.MAX_SAFE_INTEGER}
              step={1}
              value={seed}
              onChange={(event) =>
                setSeed(
                  Math.max(
                    0,
                    Math.min(
                      Number.MAX_SAFE_INTEGER,
                      Math.trunc(Number(event.target.value) || 0),
                    ),
                  ),
                )
              }
            />
          </label>
        )}
        <div className="keyframe-generator__actions">
          <button
            className="primary"
            disabled={busy || !prompt.trim()}
            onClick={() => void generate("preview")}
          >
            {busy ? "Working…" : "Generate preview"}
          </button>
          <button
            disabled={busy || !prompt.trim()}
            onClick={() => void generate("final")}
          >
            Generate final
          </button>
        </div>
      </div>
      {error && <p className="keyframe-error">{error}</p>}
      {latestFailure?.error && (
        <details className="keyframe-failure">
          <summary>Latest render failure</summary>
          <strong>{latestFailure.error.code}</strong>
          <p>{latestFailure.error.message}</p>
          {latestFailure.error.details && (
            <pre>{JSON.stringify(latestFailure.error.details, null, 2)}</pre>
          )}
        </details>
      )}
      {detail && detail.variants.length === 0 && (
        <div className="empty-state inspector-empty-state">
          <strong>No image variants yet</strong>
          <span>
            Generate a preview to create the first option for this boundary.
          </span>
        </div>
      )}
      {comparison.length > 0 && (
        <div className="variant-comparison" aria-label="Variant comparison">
          <div>
            <strong>Compare variants</strong>
            <button onClick={() => setComparison([])}>Clear</button>
          </div>
          <div>
            {comparison.map((id, index) => {
              const variant = detail?.variants.find((item) => item.id === id);
              return variant ? (
                <figure key={id}>
                  <span>{index === 0 ? "A" : "B"}</span>
                  <img
                    src={api.media.assetContentUrl(variant.asset_id)}
                    alt={`Comparison ${index === 0 ? "A" : "B"}`}
                  />
                  <figcaption>
                    {String(variant.backend_settings.quality_mode ?? "variant")}{" "}
                    · seed {String(variant.backend_settings.seed ?? "legacy")}
                  </figcaption>
                </figure>
              ) : null;
            })}
          </div>
        </div>
      )}
      <div className="keyframe-variants" aria-label="Keyframe variants">
        {detail?.variants.map((variant) => {
          const selected = detail.keyframe.selected_variant_id === variant.id;
          const usedAsReference = references.includes(variant.asset_id);
          return (
            <article key={variant.id} className={selected ? "is-selected" : ""}>
              <img
                src={api.media.assetContentUrl(variant.asset_id)}
                alt={variant.prompt}
              />
              <small>
                {selected
                  ? "Selected"
                  : new Date(variant.created_at).toLocaleString()}
              </small>
              <small>
                {String(variant.backend_settings.quality_mode ?? "legacy")} ·{" "}
                {String(variant.backend_settings.width)}×
                {String(variant.backend_settings.height)}
              </small>
              <small>
                Seed {String(variant.backend_settings.seed ?? "legacy")}
              </small>
              <div>
                <button
                  disabled={busy || selected}
                  onClick={() => void select(variant.id)}
                >
                  Select
                </button>
                <button onClick={() => void reveal(variant.asset_id)}>
                  Location
                </button>
              </div>
              <button
                className={
                  comparison.includes(variant.id) ? "is-comparing" : ""
                }
                onClick={() =>
                  setComparison((current) =>
                    current.includes(variant.id)
                      ? current.filter((id) => id !== variant.id)
                      : [...current.slice(-1), variant.id],
                  )
                }
                title="Place this variant in the A/B comparison"
              >
                {comparison.includes(variant.id)
                  ? `Comparing ${comparison.indexOf(variant.id) === 0 ? "A" : "B"}`
                  : "Compare"}
              </button>
              <label>
                <input
                  type="checkbox"
                  checked={usedAsReference}
                  onChange={() =>
                    setReferences((current) =>
                      usedAsReference
                        ? current.filter((id) => id !== variant.asset_id)
                        : [...current, variant.asset_id],
                    )
                  }
                />
                Use as extra reference
              </label>
            </article>
          );
        })}
      </div>
    </>
  );
}
