import { type FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { Wan2GPConfig, Wan2GPStatus } from "../api/types";

const modelLabels: Record<string, string> = {
  "ltx-2.3-distilled-1.1": "LTX 2.3 Distilled + audio-reactive LoRA",
  "minimax-h3-fl2va-33b": "MiniMax H3 FL2VA 33B",
  "minimax-h3-fl2va-pruned-20b": "MiniMax H3 FL2VA Pruned 20B",
  "minimax-h3-fl2va-pruned-20b-pdd": "MiniMax H3 FL2VA Pruned 20B · 8 step PDD",
};

const prunedDefault = "minimax-h3-fl2va-pruned-20b";
const prunedPdd = "minimax-h3-fl2va-pruned-20b-pdd";

export function Wan2GPSettingsPanel() {
  const [config, setConfig] = useState<Wan2GPConfig | null>(null);
  const [status, setStatus] = useState<Wan2GPStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const isLtx = config?.profile.name === "ltx-2.3-distilled-1.1";
  const isPdd = config?.profile.name === prunedPdd;
  const isPruned = isPdd || config?.profile.name === prunedDefault;

  useEffect(() => {
    void api.wan2gp
      .config()
      .then(setConfig)
      .catch((error: unknown) =>
        setMessage(
          error instanceof Error
            ? error.message
            : "Could not load Wan2GP settings.",
        ),
      );
  }, []);

  const update = <Key extends keyof Wan2GPConfig>(
    key: Key,
    value: Wan2GPConfig[Key],
  ) => setConfig((current) => (current ? { ...current, [key]: value } : null));

  const selectModel = (name: string) => {
    setConfig((current) => {
      if (!current || !current.profiles[name]) return current;
      return {
        ...current,
        profiles: {
          ...current.profiles,
          [current.profile.name]: current.profile,
        },
        profile: current.profiles[name],
      };
    });
    setStatus(null);
    setMessage("");
  };

  const updateQuality = (
    mode: "preview" | "final",
    key: "resolution" | "inference_steps",
    value: string | number,
  ) =>
    setConfig((current) =>
      current
        ? {
            ...current,
            profile: {
              ...current.profile,
              [mode]: { ...current.profile[mode], [key]: value },
            },
          }
        : null,
    );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setBusy(true);
    setMessage("");
    setStatus(null);
    try {
      setConfig(await api.wan2gp.updateConfig(config));
      setMessage("Wan2GP settings saved.");
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not save Wan2GP settings.",
      );
    } finally {
      setBusy(false);
    }
  };

  const testInstallation = async () => {
    setBusy(true);
    setMessage("");
    try {
      setStatus(await api.wan2gp.test());
    } catch (error) {
      setMessage(
        error instanceof ApiError ? error.message : "Could not test Wan2GP.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="details-panel llm-settings">
      <div className="llm-settings__heading">
        <div>
          <span className="eyebrow">Video rendering</span>
          <h2>Wan2GP backend</h2>
        </div>
        <span className="provider-kind">
          {config ? modelLabels[config.profile.name] : "Video renderer"}
        </span>
      </div>
      <p className="panel-description">
        Beatweave sends queue jobs to a Wan2GP instance started and managed by
        you. Projects remain editable while Wan2GP is offline.
      </p>
      {config && (
        <form
          className="settings-form settings-form--renderer"
          onSubmit={(event) => void save(event)}
        >
          <label>
            Video model
            <select
              value={isPdd ? prunedDefault : config.profile.name}
              onChange={(event) => selectModel(event.target.value)}
              disabled={busy}
            >
              {Object.keys(config.profiles)
                .filter((name) => name !== prunedPdd)
                .map((name) => (
                  <option key={name} value={name}>
                    {modelLabels[name] ?? name}
                  </option>
                ))}
            </select>
            <small>
              Each model keeps its own preview and final settings. Save to
              apply.
            </small>
          </label>
          {isPruned && (
            <label>
              Pruned 20B variant
              <select
                value={config.profile.name}
                onChange={(event) => selectModel(event.target.value)}
                disabled={busy}
              >
                <option value={prunedDefault}>Default</option>
                <option value={prunedPdd}>8 step PDD</option>
              </select>
              <small>
                {isPdd
                  ? "PDD uses exactly 8 steps and the Euler sampler for preview and final."
                  : "Default uses configurable inference steps and sampler."}{" "}
                Each variant keeps its own settings.
              </small>
            </label>
          )}
          <p className="panel-description">
            {isLtx
              ? "LTX uses the project soundtrack and its audio-reactive LoRA."
              : "H3 uses native soundtrack conditioning without the LTX LoRA. Scenes must be at least 4.46 seconds; durations use 17-frame increments at 24 fps."}
          </p>
          <label>
            Base URL
            <input
              type="url"
              value={config.base_url}
              onChange={(event) => update("base_url", event.target.value)}
              required
            />
          </label>
          <label>
            Wan2GP output folder (optional)
            <input
              value={config.output_directory ?? ""}
              onChange={(event) =>
                update("output_directory", event.target.value || null)
              }
              placeholder="Full path to Wan2GP's video output folder"
            />
            <small>
              Finds completed renders even after Wan2GP loses its session.
            </small>
          </label>
          <label>
            Request timeout (seconds)
            <input
              type="number"
              min="1"
              max="600"
              value={config.request_timeout_seconds}
              onChange={(event) =>
                update("request_timeout_seconds", Number(event.target.value))
              }
              required
            />
          </label>
          <label>
            Render timeout (seconds)
            <input
              type="number"
              min="10"
              max="86400"
              value={config.render_timeout_seconds}
              onChange={(event) =>
                update("render_timeout_seconds", Number(event.target.value))
              }
              required
            />
          </label>
          {(["preview", "final"] as const).map((mode) => (
            <fieldset className="quality-profile" key={mode}>
              <legend>{mode} video</legend>
              <label>
                Resolution
                <input
                  value={config.profile[mode].resolution}
                  pattern="[0-9]+x[0-9]+"
                  onChange={(event) =>
                    updateQuality(mode, "resolution", event.target.value)
                  }
                  required
                />
              </label>
              <label>
                Inference steps
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={config.profile[mode].inference_steps}
                  disabled={isPdd}
                  onChange={(event) =>
                    updateQuality(
                      mode,
                      "inference_steps",
                      Number(event.target.value),
                    )
                  }
                  required
                />
              </label>
            </fieldset>
          ))}
          {isLtx ? (
            <fieldset className="quality-profile">
              <legend>Audio-reactive LoRA</legend>
              <label>
                LoRA filename
                <input
                  value={config.audio_reactive_profile.filename}
                  onChange={(event) =>
                    update("audio_reactive_profile", {
                      ...config.audio_reactive_profile,
                      filename: event.target.value,
                    })
                  }
                  required
                />
              </label>
              <label>
                Strength
                <input
                  type="number"
                  min="-10"
                  max="10"
                  step="0.05"
                  value={config.audio_reactive_profile.default_multiplier}
                  onChange={(event) =>
                    update("audio_reactive_profile", {
                      ...config.audio_reactive_profile,
                      default_multiplier: Number(event.target.value),
                    })
                  }
                  required
                />
              </label>
              <label>
                Trigger phrase (optional)
                <input
                  value={config.audio_reactive_profile.trigger_phrase}
                  onChange={(event) =>
                    update("audio_reactive_profile", {
                      ...config.audio_reactive_profile,
                      trigger_phrase: event.target.value,
                    })
                  }
                />
              </label>
            </fieldset>
          ) : (
            <fieldset className="quality-profile">
              <legend>H3 sampling</legend>
              <label>
                Sampler
                <select
                  value={config.profile.sample_solver}
                  disabled={isPdd}
                  onChange={(event) =>
                    update("profile", {
                      ...config.profile,
                      sample_solver: event.target.value as
                        "euler" | "res_multistep" | "ralston_2s",
                    })
                  }
                >
                  <option value="euler">Euler</option>
                  <option value="res_multistep">RES Multistep</option>
                  <option value="ralston_2s">Ralston 2S</option>
                </select>
              </label>
              <label>
                Flow shift
                <input
                  type="number"
                  min="1"
                  max="25"
                  step="0.1"
                  value={config.profile.flow_shift}
                  onChange={(event) =>
                    update("profile", {
                      ...config.profile,
                      flow_shift: Number(event.target.value),
                    })
                  }
                  required
                />
              </label>
              <small>
                Dimensions must be multiples of 32. Precision, VAE and memory
                profile follow your WanGP configuration.
              </small>
            </fieldset>
          )}
          <div className="llm-settings__actions">
            <button className="primary" disabled={busy}>
              Save settings
            </button>
            <button
              type="button"
              onClick={() => void testInstallation()}
              disabled={busy}
            >
              Test connection
            </button>
          </div>
        </form>
      )}
      {config && (
        <dl className="backend-profile">
          <div>
            <dt>Model</dt>
            <dd>{config.profile.model_type}</dd>
          </div>
          <div>
            <dt>Preview / final</dt>
            <dd>
              {config.profile.preview.resolution} /{" "}
              {config.profile.final.resolution}
            </dd>
          </div>
          <div>
            <dt>Audio conditioning</dt>
            <dd>
              {isLtx
                ? config.audio_reactive_profile.filename
                : "Native soundtrack conditioning (soundtrack kept)"}
            </dd>
          </div>
        </dl>
      )}
      {message && <p className="settings-message">{message}</p>}
      {status && (
        <div
          className={
            status.available && status.profile_ready
              ? "provider-status is-online"
              : "provider-status is-offline"
          }
          role="status"
        >
          <strong>{status.message}</strong>
          {status.version && <span>Gradio {status.version}</span>}
        </div>
      )}
    </section>
  );
}
