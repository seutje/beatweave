import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { connectToEvents } from "../api/events";
import type { HealthResponse } from "../api/types";
import { waitForBackend } from "./backendConnection";

type ConnectionState = "connecting" | "connected" | "offline";

export function useBackend() {
  const [state, setState] = useState<ConnectionState>("connecting");
  const [health, setHealth] = useState<HealthResponse>();
  const [error, setError] = useState<string>();

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
    const disconnectEvents = connectToEvents(
      (event) => console.debug("Backend event", event),
      (connected) => {
        if (active && connected) setState("connected");
      },
    );
    return () => {
      active = false;
      disconnectEvents();
    };
  }, []);

  return { state, health, error, retry };
}
