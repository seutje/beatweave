import { API_BASE_URL } from "./client";
import type { BackendEvent } from "./types";

const EVENT_URL = API_BASE_URL.replace(/^http/, "ws") + "/events";

export function connectToEvents(
  onEvent: (event: BackendEvent) => void,
  onConnectionChange: (connected: boolean) => void,
): () => void {
  let stopped = false;
  let socket: WebSocket | undefined;
  let retry: number | undefined;

  const connect = () => {
    if (stopped) return;
    socket = new WebSocket(EVENT_URL);
    socket.addEventListener("open", () => onConnectionChange(true));
    socket.addEventListener("message", (message) => {
      onEvent(JSON.parse(message.data as string) as BackendEvent);
    });
    socket.addEventListener("close", () => {
      onConnectionChange(false);
      if (!stopped) retry = window.setTimeout(connect, 1500);
    });
    socket.addEventListener("error", () => socket?.close());
  };

  connect();
  return () => {
    stopped = true;
    if (retry !== undefined) window.clearTimeout(retry);
    socket?.close();
  };
}
