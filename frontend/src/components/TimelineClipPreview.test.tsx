import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Scene } from "../api/types";
import { usePlaybackStore } from "../stores/playbackStore";
import { TimelineClipPreview } from "./TimelineClipPreview";

const scene = {
  id: "scene-1",
  position: 0,
  start_time: 10,
  end_time: 20,
} as Scene;

describe("timeline video synchronization", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;
  let videos: HTMLVideoElement[];
  let frames: Map<number, FrameRequestCallback>;
  let nextFrame: number;
  let seeks: number[];
  let metadataReady: boolean;
  let drawImage: ReturnType<typeof vi.fn>;
  let audio: HTMLAudioElement;

  beforeEach(() => {
    videos = [];
    frames = new Map();
    nextFrame = 0;
    seeks = [];
    metadataReady = true;
    drawImage = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage,
      fillRect: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(id);
    });
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      if (!(this instanceof HTMLVideoElement) || videos.includes(this)) return;
      videos.push(this);
      let time = 0;
      Object.defineProperties(this, {
        currentTime: {
          configurable: true,
          get: () => time,
          set: (value: number) => {
            time = value;
            seeks.push(value);
            Object.defineProperty(this, "seeking", {
              configurable: true,
              writable: true,
              value: true,
            });
          },
        },
        readyState: {
          configurable: true,
          writable: true,
          value: metadataReady ? 4 : 0,
        },
        seeking: { configurable: true, writable: true, value: false },
        duration: { configurable: true, value: 10.25 },
        videoWidth: { configurable: true, value: 1920 },
        videoHeight: { configurable: true, value: 1088 },
        paused: { configurable: true, writable: true, value: true },
      });
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      Object.defineProperty(this, "paused", {
        configurable: true,
        writable: true,
        value: false,
      });
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      Object.defineProperty(this, "paused", {
        configurable: true,
        writable: true,
        value: true,
      });
    });
    audio = document.createElement("audio");
    audio.currentTime = 10;
    usePlaybackStore.setState({ element: audio, currentTime: 10 });
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    usePlaybackStore.setState({
      element: undefined,
      currentTime: 0,
      playing: false,
    });
    vi.restoreAllMocks();
  });

  const mount = async (
    playing = true,
    currentTime = 10,
    selectedScene = scene,
    assetId = "clip-1",
  ) => {
    await act(async () =>
      root.render(
        <TimelineClipPreview
          scene={selectedScene}
          assetId={assetId}
          nextAssetId="clip-2"
          currentTime={currentTime}
          playing={playing}
          onSelect={() => {}}
        />,
      ),
    );
  };
  const frame = () =>
    act(() => {
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach((callback) => callback(0));
    });
  const finishSeek = (video = videos[0]) =>
    act(() => {
      Object.defineProperty(video, "seeking", {
        configurable: true,
        writable: true,
        value: false,
      });
      video.dispatchEvent(new Event("seeked"));
    });

  it("uses the live audio clock and corrects small drift without seeking", async () => {
    await mount();
    // React's last rendered clock still says 10, but the audio has advanced.
    audio.currentTime = 10.1;
    frame();
    expect(videos[0].playbackRate).toBeCloseTo(1.05);
    expect(seeks).toEqual([]);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
    expect(videos[0].muted).toBe(true);
  });

  it("waits for an outstanding decoder seek before seeking again", async () => {
    await mount();
    audio.currentTime = 12;
    frame();
    expect(seeks).toEqual([2]);
    audio.currentTime = 12.5;
    frame();
    frame();
    expect(seeks).toEqual([2]);
    finishSeek();
    expect(seeks).toEqual([2, 2.5]);
  });

  it("keeps one drawing loop when loaded and seek events fire", async () => {
    await mount();
    act(() => {
      for (let i = 0; i < 5; i++) {
        videos[0].dispatchEvent(new Event("loadeddata"));
        videos[0].dispatchEvent(new Event("seeked"));
      }
    });
    expect(frames.size).toBe(1);
    frame();
    expect(frames.size).toBe(1);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  });

  it("positions late-loading video using the current audio time", async () => {
    metadataReady = false;
    audio.currentTime = 12;
    await mount();
    expect(seeks).toEqual([]);
    audio.currentTime = 13;
    act(() => {
      Object.defineProperty(videos[0], "readyState", {
        configurable: true,
        value: 4,
      });
      videos[0].dispatchEvent(new Event("loadedmetadata"));
    });
    expect(seeks).toEqual([3]);
  });

  it("scrubs precisely while paused, including changes below the old 120 ms threshold", async () => {
    await mount(false);
    audio.currentTime = 10.08;
    await mount(false, 10.08);
    expect(seeks[0]).toBeCloseTo(0.08);
    expect(frames.size).toBe(0);
    finishSeek();
    expect(drawImage).toHaveBeenCalled();
  });

  it("pauses the previous video and positions the preloaded next scene", async () => {
    await mount();
    const previous = videos[0];
    audio.currentTime = 20.4;
    await mount(
      true,
      20.4,
      { ...scene, id: "scene-2", start_time: 20, end_time: 30 },
      "clip-2",
    );
    expect(previous.paused).toBe(true);
    expect(videos[1].currentTime).toBeCloseTo(0.4);
    expect(videos[1].paused).toBe(false);
    expect(frames.size).toBe(1);
  });

  it("slows an ahead-of-audio video and restores normal speed after catching up", async () => {
    await mount();
    audio.currentTime = 10.2;
    videos[0].currentTime = 0.3;
    seeks.length = 0;
    finishSeek();
    expect(videos[0].playbackRate).toBeCloseTo(0.95);
    audio.currentTime = 10.3;
    frame();
    expect(videos[0].playbackRate).toBe(1);
    expect(seeks).toEqual([]);
  });

  it("stops drawing and pauses video when timeline playback is deactivated", async () => {
    await mount();
    expect(frames.size).toBe(1);
    await mount(false);
    expect(frames.size).toBe(0);
    expect(videos[0].paused).toBe(true);
    expect(videos[0].playbackRate).toBe(1);
  });
});
