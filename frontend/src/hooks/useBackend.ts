import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { connectToEvents } from "../api/events";
import type { HealthResponse } from "../api/types";

type ConnectionState = "connecting" | "connected" | "offline";

export function useBackend() {
  const [state, setState] = useState<ConnectionState>("connecting");
  const [health, setHealth] = useState<HealthResponse>();
  const [error, setError] = useState<string>();

  const retry = useCallback(async () => {
    setState("connecting");
    try {
      const result = await api.health();
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
    void api
      .health()
      .then((result) => {
        setHealth(result);
        setError(undefined);
        setState("connected");
      })
      .catch((reason: unknown) => {
        setError(
          reason instanceof Error ? reason.message : "Backend is unavailable",
        );
        setState("offline");
      });
    return connectToEvents(
      (event) => console.debug("Backend event", event),
      (connected) => {
        if (connected) setState("connected");
      },
    );
  }, []);

  return { state, health, error, retry };
}
