import { invoke } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";

interface McpStatus {
  running: boolean;
  url: string;
  message: string;
}

export function MCPSettingsPanel() {
  const [status, setStatus] = useState<McpStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      setStatus(await invoke<McpStatus>("mcp_status"));
      setMessage("");
    } catch (error) {
      setMessage(
        typeof error === "string"
          ? error
          : "MCP lifecycle controls are available in the desktop app.",
      );
    }
  };

  useEffect(() => {
    const id = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(id);
  }, []);

  const setRunning = async (running: boolean) => {
    setBusy(true);
    setMessage("");
    try {
      setStatus(
        await invoke<McpStatus>(
          running ? "start_mcp_server" : "stop_mcp_server",
        ),
      );
    } catch (error) {
      setMessage(
        typeof error === "string"
          ? error
          : "Could not change MCP server state.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="details-panel llm-settings mcp-settings">
      <div className="llm-settings__heading">
        <div>
          <span className="eyebrow">Agent control</span>
          <h2>MCP server</h2>
        </div>
        <span
          className={`provider-status ${status?.running ? "is-online" : "is-offline"}`}
        >
          {status?.running ? "Running" : "Stopped"}
        </span>
      </div>
      <p className="panel-description">
        Start an optional local MCP endpoint for Codex or another trusted
        client. It controls the active project through the same API and durable
        job system as Beatweave.
      </p>
      <dl className="backend-profile">
        <div>
          <dt>Endpoint</dt>
          <dd>{status?.url ?? "http://127.0.0.1:8421/mcp"}</dd>
        </div>
        <div>
          <dt>Access</dt>
          <dd>Local machine only</dd>
        </div>
      </dl>
      <div className="llm-settings__actions">
        <button
          className="primary"
          type="button"
          disabled={busy || status?.running === true}
          onClick={() => void setRunning(true)}
        >
          {busy ? "Working…" : "Start MCP server"}
        </button>
        <button
          type="button"
          disabled={busy || status?.running !== true}
          onClick={() => void setRunning(false)}
        >
          Stop server
        </button>
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          Refresh status
        </button>
      </div>
      {status && <p className="settings-message">{status.message}</p>}
      {message && <p className="settings-message is-error">{message}</p>}
    </section>
  );
}
