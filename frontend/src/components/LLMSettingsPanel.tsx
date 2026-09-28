import { type FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { LLMProviderConfig, ProviderAvailability } from "../api/types";

export function LLMSettingsPanel() {
  const [config, setConfig] = useState<LLMProviderConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434/v1");
  const [model, setModel] = useState("qwen3:8b");
  const [timeout, setTimeoutValue] = useState(30);
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState<ProviderAvailability | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.llm
      .config()
      .then((value) => {
        setConfig(value);
        setBaseUrl(value.base_url);
        setModel(value.model);
        setTimeoutValue(value.timeout_seconds);
      })
      .catch((error: unknown) =>
        setMessage(
          error instanceof Error
            ? error.message
            : "Could not load LLM settings.",
        ),
      );
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setStatus(null);
    try {
      const saved = await api.llm.updateConfig({
        provider: "openai_compatible",
        base_url: baseUrl,
        model,
        timeout_seconds: timeout,
        ...(apiKey ? { api_key: apiKey } : {}),
      });
      setConfig(saved);
      setApiKey("");
      setMessage("Provider settings saved.");
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not save LLM settings.",
      );
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setMessage("");
    try {
      setStatus(await api.llm.test());
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not test the provider.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="details-panel llm-settings">
      <div className="llm-settings__heading">
        <div>
          <span className="eyebrow">Creative planning</span>
          <h2>Local LLM provider</h2>
        </div>
        <span className="provider-kind">OpenAI-compatible</span>
      </div>
      <p className="panel-description">
        Configure a local endpoint for future visual and scene planning.
        Projects remain usable while it is offline.
      </p>
      <form onSubmit={(event) => void save(event)}>
        <label>
          Base URL
          <input
            type="url"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="http://localhost:11434/v1"
            required
          />
        </label>
        <label>
          Model name
          <input
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="qwen3:8b"
            required
          />
        </label>
        <label>
          Timeout (seconds)
          <input
            type="number"
            min="1"
            max="600"
            value={timeout}
            onChange={(event) => setTimeoutValue(Number(event.target.value))}
            required
          />
        </label>
        <label>
          API key {config?.api_key_configured && <small>(configured)</small>}
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={
              config?.api_key_configured
                ? "Leave blank to keep current key"
                : "Optional"
            }
          />
        </label>
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
      {message && <p className="settings-message">{message}</p>}
      {status && (
        <p
          className={
            status.available
              ? "provider-status is-online"
              : "provider-status is-offline"
          }
        >
          {status.message}
        </p>
      )}
    </section>
  );
}
