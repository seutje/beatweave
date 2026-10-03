import { type FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { Wan2GPConfig, Wan2GPStatus } from "../api/types";

export function Wan2GPSettingsPanel() {
  const [config, setConfig] = useState<Wan2GPConfig | null>(null);
  const [status, setStatus] = useState<Wan2GPStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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
          {config?.profile.name ?? "LTX 2.3 Distilled"}
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
            Base URL
            <input
              type="url"
              value={config.base_url}
              onChange={(event) => update("base_url", event.target.value)}
              required
            />
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
            <dt>Audio-reactive LoRA</dt>
            <dd>{config.audio_reactive_profile.filename}</dd>
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
