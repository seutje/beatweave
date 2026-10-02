import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    vi.restoreAllMocks();
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

  it("samples the audio master clock on animation frames while playing", () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    let frame: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frame = callback;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(
      () => undefined,
    );

    act(() => root.render(<AudioTransport audio={audio} active />));
    const element = container.querySelector("audio")!;
    Object.defineProperty(element, "paused", {
      configurable: true,
      value: false,
    });
    Object.defineProperty(element, "currentTime", {
      configurable: true,
      value: 12.5,
      writable: true,
    });
    act(() => usePlaybackStore.getState().setPlaying(true));
    act(() => frame?.(0));

    expect(usePlaybackStore.getState().currentTime).toBe(12.5);
    expect(window.requestAnimationFrame).toHaveBeenCalledTimes(2);
  });
});
