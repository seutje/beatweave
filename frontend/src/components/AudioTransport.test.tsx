import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import type { AudioState } from "../api/types";
import { usePlaybackStore } from "../stores/playbackStore";
import { AudioTransport } from "./AudioTransport";

const audio = {
  asset: { id: "audio-1", sha256: "track-hash" },
  waveform: { duration_seconds: 60 },
} as AudioState;

describe("AudioTransport", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    usePlaybackStore.setState({
      element: undefined,
      currentTime: 0,
      duration: 0,
      playing: false,
    });
  });

  it("reattaches its audio element when its workspace becomes active again", () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);

    act(() => root.render(<AudioTransport audio={audio} active />));
    const timelineElement = container.querySelector("audio");
    expect(usePlaybackStore.getState().element).toBe(timelineElement);

    act(() => root.render(<AudioTransport audio={audio} active={false} />));
    expect(usePlaybackStore.getState().element).toBeUndefined();

    act(() => root.render(<AudioTransport audio={audio} active />));
    expect(usePlaybackStore.getState().element).toBe(timelineElement);
  });
});
