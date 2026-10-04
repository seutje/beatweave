import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { connectToEvents } from "../api/events";
import type { BackendEvent, HealthResponse } from "../api/types";
import { useProjectStore } from "../stores/projectStore";
import { useTimelineStore } from "../stores/timelineStore";
import { waitForBackend } from "./backendConnection";

type ConnectionState = "connecting" | "connected" | "offline";

export interface AgentActivity {
  label: string;
  path: string;
}

export function agentActivityFromEvent(
  event: BackendEvent,
): AgentActivity | undefined {
  if (event.type !== "project-changed" || event.payload.source !== "mcp")
    return undefined;
  const path = event.payload.path;
  if (typeof path !== "string") return undefined;
  const label = path.startsWith("/timeline")
    ? "timeline"
    : path.startsWith("/planning")
      ? "visual plan"
      : path.startsWith("/keyframes")
        ? "keyframes"
        : path.startsWith("/scenes")
          ? "video takes"
          : path.startsWith("/media/audio")
            ? "audio"
            : path.startsWith("/analysis")
              ? "analysis"
              : path.startsWith("/exports")
                ? "export queue"
                : "project";
  return { label, path };
}

export async function synchronizeBackendChange(
  event: BackendEvent,
): Promise<void> {
  if (!agentActivityFromEvent(event) && event.type !== "job-complete") return;
  await useProjectStore.getState().load();
  const project = useProjectStore.getState();
  if (project.current && project.audio) {
    await useTimelineStore.getState().load();
  } else {
    useTimelineStore.getState().clear();
  }
  window.dispatchEvent(
    new CustomEvent("beatweave:project-changed", { detail: event.payload }),
  );
  window.dispatchEvent(new Event("beatweave:video-takes-changed"));
}

export function useBackend() {
  const [state, setState] = useState<ConnectionState>("connecting");
  const [health, setHealth] = useState<HealthResponse>();
  const [error, setError] = useState<string>();
  const [agentActivity, setAgentActivity] = useState<AgentActivity>();

  const retry = useCallback(async () => {
    setState("connecting");
    try {
      const result = await waitForBackend(api.health);
      setHealth(result);
      setError(undefined);
      setState("connected");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Backend is unavailable",
      );
      setState("offline");
    }
  }, []);

  useEffect(() => {
    let active = true;
    void waitForBackend(api.health, { shouldContinue: () => active })
      .then((result) => {
        if (!active) return;
        setHealth(result);
        setError(undefined);
        setState("connected");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof Error ? reason.message : "Backend is unavailable",
        );
        setState("offline");
      });
    let activityTimer: number | undefined;
    let synchronization = Promise.resolve();
    const disconnectEvents = connectToEvents(
      (event) => {
        console.debug("Backend event", event);
        const activity = agentActivityFromEvent(event);
        if (activity) {
          setAgentActivity(activity);
          if (activityTimer !== undefined) window.clearTimeout(activityTimer);
          activityTimer = window.setTimeout(
            () => setAgentActivity(undefined),
            4000,
          );
        }
        if (activity || event.type === "job-complete") {
          synchronization = synchronization
            .then(() => synchronizeBackendChange(event))
            .catch((reason: unknown) =>
              console.warn("Could not synchronize a backend change", reason),
            );
        }
      },
      (connected) => {
        if (active && connected) setState("connected");
      },
    );
    return () => {
      active = false;
      if (activityTimer !== undefined) window.clearTimeout(activityTimer);
      disconnectEvents();
    };
  }, []);

  return { state, health, error, retry, agentActivity };
}
