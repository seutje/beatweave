import { type FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { ComfyUIConfig, ComfyUIStatus } from "../api/types";

export function ComfyUISettingsPanel() {
  const [config, setConfig] = useState<ComfyUIConfig | null>(null);
  const [status, setStatus] = useState<ComfyUIStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.comfyui
      .config()
      .then(setConfig)
      .catch((error: unknown) =>
        setMessage(
          error instanceof Error
            ? error.message
            : "Could not load ComfyUI settings.",
        ),
      );
  }, []);

  const update = <Key extends keyof ComfyUIConfig>(
    key: Key,
    value: ComfyUIConfig[Key],
  ) => setConfig((current) => (current ? { ...current, [key]: value } : null));

  const updateQuality = (
    mode: "preview_profile" | "final_profile",
    key: "width" | "height" | "steps" | "cfg",
    value: number,
  ) =>
    setConfig((current) =>
      current
        ? { ...current, [mode]: { ...current[mode], [key]: value } }
        : null,
    );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setBusy(true);
    setMessage("");
    setStatus(null);
    try {
      setConfig(await api.comfyui.updateConfig(config));
      setMessage("ComfyUI settings saved.");
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not save ComfyUI settings.",
      );
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setMessage("");
    try {
      setStatus(await api.comfyui.test());
    } catch (error) {
      setMessage(
        error instanceof ApiError ? error.message : "Could not test ComfyUI.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="details-panel llm-settings">
      <div className="llm-settings__heading">
        <div>
          <span className="eyebrow">Image rendering</span>
          <h2>ComfyUI backend</h2>
        </div>
        <span className="provider-kind">
          {config?.profile.name ?? "Qwen Image 2.1"}
        </span>
      </div>
      <p className="panel-description">
        Beatweave submits canonical image requests to this local ComfyUI
        instance. Projects remain editable while it is offline.
      </p>
      {config && (
        <form onSubmit={(event) => void save(event)}>
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
            Request timeout
            <input
              type="number"
              min="1"
              max="6000"
              value={config.request_timeout_seconds}
              onChange={(event) =>
                update("request_timeout_seconds", Number(event.target.value))
              }
              required
            />
          </label>
          <label>
            Render timeout
            <input
              type="number"
              min="10"
              max="7200"
              value={config.render_timeout_seconds}
              onChange={(event) =>
                update("render_timeout_seconds", Number(event.target.value))
              }
              required
            />
          </label>
          {(["preview_profile", "final_profile"] as const).map((mode) => (
            <fieldset className="quality-profile" key={mode}>
              <legend>
                {mode === "preview_profile" ? "Preview" : "Final"} image
              </legend>
              {(["width", "height", "steps", "cfg"] as const).map((key) => (
                <label key={key}>
                  {key}
                  <input
                    type="number"
                    min={key === "steps" ? 1 : key === "cfg" ? 0 : 256}
                    max={key === "steps" || key === "cfg" ? 100 : 2048}
                    step={key === "cfg" ? 0.1 : key === "steps" ? 1 : 8}
                    value={config[mode][key]}
                    onChange={(event) =>
                      updateQuality(mode, key, Number(event.target.value))
                    }
                    required
                  />
                </label>
              ))}
            </fieldset>
          ))}
          <div className="llm-settings__actions">
            <button className="primary" disabled={busy}>
              Save settings
            </button>
            <button
              type="button"
              onClick={() => void testConnection()}
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
            <dt>Diffusion model</dt>
            <dd>{config.profile.diffusion_model}</dd>
          </div>
          <div>
            <dt>Text encoder</dt>
            <dd>{config.profile.text_encoder}</dd>
          </div>
          <div>
            <dt>VAE</dt>
            <dd>{config.profile.vae}</dd>
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
          {status.version && <span>ComfyUI {status.version}</span>}
          {status.device && <span>{status.device}</span>}
        </div>
      )}
    </section>
  );
}
