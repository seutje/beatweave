import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";

interface ServiceState {
  name: string;
  purpose: string;
  state: "checking" | "ready" | "offline";
  message: string;
}

const initial: ServiceState[] = [
  {
    name: "Local LLM",
    purpose: "Plans prompts",
    state: "checking",
    message: "Checking…",
  },
  {
    name: "ComfyUI",
    purpose: "Renders keyframes",
    state: "checking",
    message: "Checking…",
  },
  {
    name: "Wan2GP",
    purpose: "Renders video",
    state: "checking",
    message: "Checking…",
  },
];

export function BackendConnectivity() {
  const [services, setServices] = useState(initial);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    setServices(initial);
    const results = await Promise.allSettled([
      api.llm.test(),
      api.comfyui.test(),
      api.wan2gp.test(),
    ]);
    setServices(
      initial.map((service, index) => {
        const result = results[index];
        if (result.status === "rejected") {
          return {
            ...service,
            state: "offline",
            message:
              result.reason instanceof Error
                ? result.reason.message
                : "Connection failed",
          };
        }
        const value = result.value;
        const ready =
          "profile_ready" in value
            ? value.available && value.profile_ready
            : value.available;
        return {
          ...service,
          state: ready ? "ready" : "offline",
          message: value.message,
        };
      }),
    );
    setChecking(false);
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => void check(), 0);
    return () => window.clearTimeout(id);
  }, [check]);

  return (
    <section className="connectivity-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Backend setup</span>
          <h1>Local service connections</h1>
          <p>
            Start each service separately, then configure its local URL below.
          </p>
        </div>
        <button onClick={() => void check()} disabled={checking}>
          {checking ? "Checking…" : "Check all"}
        </button>
      </div>
      <div className="connectivity-grid">
        {services.map((service) => (
          <article
            key={service.name}
            className={`is-${service.state}`}
            title={service.message}
          >
            <span
              className={`status__dot status__dot--${service.state === "ready" ? "connected" : service.state === "offline" ? "offline" : "checking"}`}
            />
            <div>
              <strong>{service.name}</strong>
              <small>{service.purpose}</small>
            </div>
            <span>{service.state}</span>
            <p>{service.message}</p>
          </article>
        ))}
      </div>
      <p className="setup-note">
        Offline services never prevent opening or editing a project. Connect
        them only when their workflow step is needed.
      </p>
    </section>
  );
}
