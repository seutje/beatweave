import { memo, useEffect, useRef } from "react";

import { api } from "../api/client";
import type { Scene } from "../api/types";
import { usePlaybackStore } from "../stores/playbackStore";

export const TimelineClipPreview = memo(function TimelineClipPreview({
  scene,
  assetId,
  status,
  nextAssetId,
  currentTime,
  playing,
  onSelect,
}: {
  scene?: Scene;
  assetId?: string;
  status?: string;
  nextAssetId?: string;
  currentTime: number;
  playing: boolean;
  onSelect: (id: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const refreshFrame = useRef<(() => void) | undefined>(undefined);
  const sceneStart = scene?.start_time;

  useEffect(() => {
    const wanted = new Set(
      [assetId, nextAssetId].filter((id): id is string => Boolean(id)),
    );
    for (const [id, element] of videos.current) {
      if (wanted.has(id)) continue;
      element.pause();
      element.removeAttribute("src");
      element.load();
      videos.current.delete(id);
    }
    wanted.forEach((id) => {
      if (videos.current.has(id)) return;
      const element = document.createElement("video");
      element.muted = true;
      element.playsInline = true;
      element.preload = "auto";
      element.src = api.media.assetContentUrl(id);
      element.load();
      videos.current.set(id, element);
    });
  }, [assetId, nextAssetId]);

  useEffect(
    () => () => {
      for (const element of videos.current.values()) {
        element.pause();
        element.removeAttribute("src");
        element.load();
      }
      videos.current.clear();
    },
    [],
  );

  useEffect(() => {
    const surface = canvas.current;
    const element = assetId ? videos.current.get(assetId) : undefined;
    if (!surface || !element || sceneStart === undefined) return;
    const context = surface.getContext("2d");
    if (!context) return;
    let animationFrame: number | undefined;
    let initialPosition = true;
    let disposed = false;
    let starting = false;

    const synchronize = () => {
      if (
        element.readyState < HTMLMediaElement.HAVE_METADATA ||
        element.seeking
      )
        return;
      const master = usePlaybackStore.getState();
      const time = master.element?.currentTime ?? master.currentTime;
      const duration = Number.isFinite(element.duration)
        ? Math.max(0, element.duration - 0.001)
        : Infinity;
      const target = Math.max(0, Math.min(time - sceneStart, duration));
      const drift = target - element.currentTime;
      // Scrubs and scene changes need an exact position. While playing, repeated
      // hard seeks can starve the decoder; correct small drift through speed instead.
      if (initialPosition || !playing || Math.abs(drift) > 0.25) {
        if (Math.abs(drift) > 0.015) element.currentTime = target;
        element.playbackRate = 1;
      } else {
        element.playbackRate =
          Math.abs(drift) < 0.025
            ? 1
            : Math.max(0.95, Math.min(1.05, 1 + drift * 0.5));
      }
      initialPosition = false;
    };

    const start = () => {
      if (!playing || disposed || starting || !element.paused || element.ended)
        return;
      starting = true;
      void element
        .play()
        .catch(() => undefined)
        .finally(() => {
          starting = false;
        });
    };

    const draw = () => {
      if (disposed) return;
      synchronize();
      if (
        element.seeking ||
        element.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
      )
        return;
      const bounds = surface.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(bounds.width * scale));
      const height = Math.max(1, Math.round(bounds.height * scale));
      if (surface.width !== width || surface.height !== height) {
        surface.width = width;
        surface.height = height;
      }
      const videoRatio = element.videoWidth / element.videoHeight || 16 / 9;
      const canvasRatio = width / height;
      const drawWidth = canvasRatio > videoRatio ? height * videoRatio : width;
      const drawHeight = canvasRatio > videoRatio ? height : width / videoRatio;
      context.fillStyle = "#050912";
      context.fillRect(0, 0, width, height);
      context.drawImage(
        element,
        (width - drawWidth) / 2,
        (height - drawHeight) / 2,
        drawWidth,
        drawHeight,
      );
    };

    const tick = () => {
      draw();
      if (!disposed) animationFrame = window.requestAnimationFrame(tick);
    };
    const ready = () => {
      draw();
      start();
    };
    refreshFrame.current = draw;
    element.addEventListener("loadedmetadata", ready);
    element.addEventListener("loadeddata", ready);
    element.addEventListener("canplay", ready);
    element.addEventListener("seeked", ready);
    draw();
    if (playing) {
      start();
      animationFrame = window.requestAnimationFrame(tick);
    } else element.pause();

    return () => {
      disposed = true;
      refreshFrame.current = undefined;
      if (animationFrame !== undefined)
        window.cancelAnimationFrame(animationFrame);
      element.removeEventListener("loadedmetadata", ready);
      element.removeEventListener("loadeddata", ready);
      element.removeEventListener("canplay", ready);
      element.removeEventListener("seeked", ready);
      element.pause();
      element.playbackRate = 1;
    };
  }, [assetId, playing, sceneStart]);

  useEffect(() => {
    if (!playing) refreshFrame.current?.();
  }, [currentTime, playing]);

  return (
    <section
      className="timeline-clip-preview"
      aria-label="Timeline clip preview"
    >
      <div className="timeline-clip-preview__heading">
        <strong>
          {scene ? `Scene ${scene.position + 1}` : "No scene at playhead"}
        </strong>
        <span
          className={`render-state is-${scene?.approved ? "approved" : (status ?? "unrendered")}`}
        >
          {scene?.approved ? "approved" : (status ?? "unrendered")}
        </span>
      </div>
      {scene && assetId ? (
        <canvas
          ref={canvas}
          aria-label={`Scene ${scene.position + 1} video preview`}
          onClick={() => onSelect(scene.id)}
        />
      ) : (
        <div className="timeline-clip-preview__empty">
          {status === "rendering"
            ? "Rendering this scene…"
            : status === "failed"
              ? "The latest scene render failed."
              : status === "missing"
                ? "The selected video file is missing."
                : "No selected video take for this scene."}
        </div>
      )}
    </section>
  );
});
