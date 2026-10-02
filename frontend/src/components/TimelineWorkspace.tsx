import { memo, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { Keyframe, Scene, SceneVideoTakes, VideoTake } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import { exceededDragThreshold, isEditableTarget } from "../lib/interactions";
import { usePlaybackStore } from "../stores/playbackStore";
import { useProjectStore } from "../stores/projectStore";
import { useTimelineStore } from "../stores/timelineStore";
import { snapTime, type SnapMode, type SnapTarget } from "../timeline/snapping";
import { createTimelineTransform } from "../timeline/transform";
import { AudioTransport } from "./AudioTransport";
import { KeyframeInspector } from "./KeyframeInspector";
import { SceneInspector } from "./SceneInspector";

const HEIGHT = 258;
const SCENE_TOP = 188;
const SCENE_BOTTOM = 258;

interface DragState {
  keyframeId: string;
  time: number;
  target?: SnapTarget;
}

interface PendingDrag {
  pointerId: number;
  keyframeId: string;
  time: number;
  x: number;
  y: number;
}

interface ContextMenuState {
  x: number;
  y: number;
  time: number;
  sceneId?: string;
  keyframeId?: string;
}

interface OverlayState {
  waveform: boolean;
  beats: boolean;
  downbeats: boolean;
  energy: boolean;
}

type SceneRenderStatus =
  | "unrendered"
  | "rendering"
  | "complete"
  | "failed"
  | "stale"
  | "missing"
  | "approved";

interface SceneVideoState {
  detail: SceneVideoTakes;
  selected?: VideoTake;
  status: SceneRenderStatus;
}

const ACTIVE_JOB_STATES = new Set(["queued", "preparing", "running"]);

function sceneVideoState(detail: SceneVideoTakes): SceneVideoState {
  const selected = detail.takes.find((take) => take.selected);
  const latestJob = detail.render_jobs[0];
  let status: SceneRenderStatus = "unrendered";
  if (latestJob && ACTIVE_JOB_STATES.has(latestJob.state)) status = "rendering";
  else if (selected?.stale || detail.selected_take_stale) status = "stale";
  else if (selected) status = "complete";
  else if (detail.selected_take_id) status = "missing";
  else if (latestJob?.state === "failed") status = "failed";
  return { detail, selected, status };
}

function drawTimeline(
  canvas: HTMLCanvasElement,
  viewportWidth: number,
  pixelsPerSecond: number,
  scrollX: number,
  duration: number,
  waveform: number[],
  beats: number[],
  downbeats: number[],
  energy: { time: number; value: number }[],
  scenes: Scene[],
  keyframes: Keyframe[],
  keyframeImages: Map<string, HTMLImageElement>,
  sceneVideos: Map<string, HTMLVideoElement>,
  videoStates: Map<string, SceneVideoState>,
  currentTime: number,
  selectedSceneId: string | undefined,
  selectedKeyframeId: string | undefined,
  overlays: OverlayState,
  drag: DragState | undefined,
  proposedBoundaries: number[],
) {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = viewportWidth * ratio;
  canvas.height = HEIGHT * ratio;
  canvas.style.width = `${viewportWidth}px`;
  canvas.style.height = `${HEIGHT}px`;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, viewportWidth, HEIGHT);
  const transform = createTimelineTransform(pixelsPerSecond, scrollX);
  const x = (time: number) => transform.timeToX(time);

  context.fillStyle = "#080e17";
  context.fillRect(0, 0, viewportWidth, HEIGHT);
  context.strokeStyle = "#1d293a";
  context.beginPath();
  context.moveTo(0, 150.5);
  context.lineTo(viewportWidth, 150.5);
  context.stroke();

  if (overlays.beats) {
    context.strokeStyle = "rgba(112, 137, 194, .25)";
    context.lineWidth = 1;
    beats.forEach((time) => {
      const position = x(time);
      if (position < 0 || position > viewportWidth) return;
      context.beginPath();
      context.moveTo(position, 24);
      context.lineTo(position, SCENE_BOTTOM);
      context.stroke();
    });
  }
  if (overlays.downbeats) {
    context.strokeStyle = "rgba(103, 213, 239, .65)";
    context.lineWidth = 1.5;
    downbeats.forEach((time) => {
      const position = x(time);
      if (position < 0 || position > viewportWidth) return;
      context.beginPath();
      context.moveTo(position, 20);
      context.lineTo(position, SCENE_BOTTOM);
      context.stroke();
    });
  }
  if (overlays.waveform && waveform.length > 0 && duration > 0) {
    context.fillStyle = "rgba(105, 145, 255, .6)";
    const center = 91;
    const startTime = Math.max(0, transform.xToTime(0));
    const endTime = Math.min(duration, transform.xToTime(viewportWidth));
    const start = Math.floor((startTime / duration) * waveform.length);
    const end = Math.ceil((endTime / duration) * waveform.length);
    for (let index = start; index < end; index += 1) {
      const position = x((index / waveform.length) * duration);
      const height = waveform[index] * 72;
      context.fillRect(
        position,
        center - height / 2,
        Math.max(1, (pixelsPerSecond * duration) / waveform.length),
        height,
      );
    }
  }
  if (overlays.energy && energy.length > 1) {
    context.strokeStyle = "#c36cf3";
    context.lineWidth = 2;
    context.beginPath();
    energy.forEach((sample, index) => {
      const positionX = x(sample.time);
      const positionY = 140 - sample.value * 68;
      if (index === 0) context.moveTo(positionX, positionY);
      else context.lineTo(positionX, positionY);
    });
    context.stroke();
  }

  scenes.forEach((scene) => {
    const previewStart =
      drag?.keyframeId === scene.start_keyframe_id
        ? drag.time
        : scene.start_time;
    const previewEnd =
      drag?.keyframeId === scene.end_keyframe_id ? drag.time : scene.end_time;
    const left = x(previewStart);
    const right = x(previewEnd);
    const videoState = videoStates.get(scene.id);
    const sceneVideo = sceneVideos.get(scene.id);
    const statusColors: Record<SceneRenderStatus, string> = {
      unrendered: "#1b2a46",
      rendering: "#463c1b",
      complete: "#183d38",
      failed: "#4a2029",
      stale: "#493b1d",
      missing: "#3f263d",
      approved: "#45345f",
    };
    const displayedStatus: SceneRenderStatus = scene.approved
      ? "approved"
      : (videoState?.status ?? "unrendered");
    context.fillStyle = statusColors[displayedStatus];
    context.strokeStyle =
      scene.id === selectedSceneId
        ? scene.approved
          ? "#b59ae7"
          : "#8292ff"
        : "#3a4c69";
    context.fillRect(
      left + 1,
      SCENE_TOP,
      right - left - 2,
      SCENE_BOTTOM - SCENE_TOP,
    );
    context.strokeRect(
      left + 1.5,
      SCENE_TOP + 0.5,
      right - left - 3,
      SCENE_BOTTOM - SCENE_TOP - 1,
    );
    if (sceneVideo?.readyState && right - left > 42) {
      context.save();
      context.globalAlpha = 0.42;
      context.beginPath();
      context.rect(left + 2, SCENE_TOP + 2, right - left - 4, 34);
      context.clip();
      context.drawImage(
        sceneVideo,
        left + 2,
        SCENE_TOP + 2,
        right - left - 4,
        34,
      );
      context.restore();
    }
    if (right > 0 && left < viewportWidth) {
      context.fillStyle = "#dce5f4";
      context.font = "12px system-ui";
      context.fillText(
        `Scene ${scene.position + 1}`,
        Math.max(8, left + 10),
        SCENE_TOP + 25,
      );
      context.fillStyle = "#95a5bd";
      context.font = "10px system-ui";
      context.fillText(
        `${(previewEnd - previewStart).toFixed(2)}s`,
        Math.max(8, left + 10),
        SCENE_TOP + 44,
      );
      const label = displayedStatus;
      context.fillStyle = label === "failed" ? "#ff91a4" : "#d6c989";
      context.font = "9px system-ui";
      context.fillText(
        `${scene.approved || videoState?.selected ? "✓ " : ""}${label}`,
        Math.max(8, left + 10),
        SCENE_TOP + 60,
      );
    }
  });

  if (proposedBoundaries.length > 0) {
    context.save();
    context.setLineDash([5, 4]);
    context.strokeStyle = "#ffd36e";
    context.lineWidth = 2;
    proposedBoundaries.forEach((time) => {
      const position = x(time);
      if (position < 0 || position > viewportWidth) return;
      context.beginPath();
      context.moveTo(position, 12);
      context.lineTo(position, SCENE_BOTTOM + 10);
      context.stroke();
    });
    context.restore();
  }

  keyframes.forEach((keyframe) => {
    const time = drag?.keyframeId === keyframe.id ? drag.time : keyframe.time;
    const position = x(time);
    if (position < -10 || position > viewportWidth + 10) return;
    const image = keyframeImages.get(keyframe.id);
    if (image) {
      context.save();
      context.beginPath();
      context.roundRect(position - 20, SCENE_TOP - 51, 40, 40, 4);
      context.clip();
      context.drawImage(image, position - 20, SCENE_TOP - 51, 40, 40);
      context.restore();
      context.strokeStyle = "#70d7ef";
      context.strokeRect(position - 20, SCENE_TOP - 51, 40, 40);
    }
    context.fillStyle = keyframe.id === selectedKeyframeId ? "#fff" : "#70d7ef";
    context.beginPath();
    context.moveTo(position, SCENE_TOP - 8);
    context.lineTo(position + 7, SCENE_TOP - 1);
    context.lineTo(position, SCENE_TOP + 6);
    context.lineTo(position - 7, SCENE_TOP - 1);
    context.closePath();
    context.fill();
  });

  if (drag?.target) {
    const position = x(drag.target.time);
    context.strokeStyle = "#ffd36e";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(position, 12);
    context.lineTo(position, SCENE_BOTTOM + 10);
    context.stroke();
    context.fillStyle = "#ffd36e";
    context.font = "10px system-ui";
    context.fillText(
      `${drag.target.kind} ${formatTime(drag.target.time)}`,
      position + 5,
      18,
    );
  }

  const playhead = x(currentTime);
  context.strokeStyle = "#ff607e";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(playhead, 0);
  context.lineTo(playhead, HEIGHT);
  context.stroke();
  context.fillStyle = "#ff607e";
  context.beginPath();
  context.moveTo(playhead - 6, 0);
  context.lineTo(playhead + 6, 0);
  context.lineTo(playhead, 8);
  context.closePath();
  context.fill();
}

const TimelineClipPreview = memo(function TimelineClipPreview({
  scene,
  state,
  nextAssetId,
  currentTime,
  playing,
  onSelect,
}: {
  scene?: Scene;
  state?: SceneVideoState;
  nextAssetId?: string;
  currentTime: number;
  playing: boolean;
  onSelect: (id: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const activeVideo = useRef<HTMLVideoElement | undefined>(undefined);
  const assetId = state?.selected?.asset_id;

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
    const element = assetId ? videos.current.get(assetId) : undefined;
    const previous = activeVideo.current;
    if (previous && previous !== element) previous.pause();
    activeVideo.current = element;
    if (!element || !scene) return;
    const localTime = Math.max(
      0,
      Math.min(currentTime - scene.start_time, element.duration || Infinity),
    );
    if (Math.abs(element.currentTime - localTime) > 0.12) {
      element.currentTime = localTime;
    }
  }, [assetId, currentTime, scene]);

  useEffect(() => {
    const element = assetId ? videos.current.get(assetId) : undefined;
    if (!element) return;
    const start = () => void element.play().catch(() => undefined);
    if (playing) {
      start();
      element.addEventListener("canplay", start);
    } else {
      element.pause();
    }
    return () => element.removeEventListener("canplay", start);
  }, [assetId, playing]);

  useEffect(() => {
    const surface = canvas.current;
    if (!surface || !assetId) return;
    const context = surface.getContext("2d");
    const element = videos.current.get(assetId);
    if (!context || !element) return;
    let animationFrame = 0;

    const draw = () => {
      const bounds = surface.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(bounds.width * scale));
      const height = Math.max(1, Math.round(bounds.height * scale));
      if (surface.width !== width || surface.height !== height) {
        surface.width = width;
        surface.height = height;
      }
      if (element.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        const videoRatio = element.videoWidth / element.videoHeight || 16 / 9;
        const canvasRatio = width / height;
        const drawWidth =
          canvasRatio > videoRatio ? height * videoRatio : width;
        const drawHeight =
          canvasRatio > videoRatio ? height : width / videoRatio;
        context.fillStyle = "#050912";
        context.fillRect(0, 0, width, height);
        context.drawImage(
          element,
          (width - drawWidth) / 2,
          (height - drawHeight) / 2,
          drawWidth,
          drawHeight,
        );
      }
      if (playing) animationFrame = window.requestAnimationFrame(draw);
    };

    const drawLoadedFrame = () => draw();
    element.addEventListener("loadeddata", drawLoadedFrame);
    element.addEventListener("seeked", drawLoadedFrame);
    draw();
    return () => {
      window.cancelAnimationFrame(animationFrame);
      element.removeEventListener("loadeddata", drawLoadedFrame);
      element.removeEventListener("seeked", drawLoadedFrame);
    };
  }, [assetId, playing]);

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
          className={`render-state is-${
            scene?.approved ? "approved" : (state?.status ?? "unrendered")
          }`}
        >
          {scene?.approved ? "approved" : (state?.status ?? "unrendered")}
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
          {state?.status === "rendering"
            ? "Rendering this scene…"
            : state?.status === "failed"
              ? "The latest scene render failed."
              : state?.status === "missing"
                ? "The selected video file is missing."
                : "No selected video take for this scene."}
        </div>
      )}
    </section>
  );
});

export function TimelineWorkspace({ active = true }: { active?: boolean }) {
  const { current, audio, analysis } = useProjectStore();
  const {
    timeline,
    proposal,
    loading,
    error,
    selectedSceneId,
    selectedKeyframeId,
    load,
    createScene,
    deleteScene,
    moveBoundary,
    suggestLayout,
    applyLayout,
    cancelProposal,
    undo,
    redo,
    updateScene,
    generateVisualPlan,
    regenerateScene,
    selectScene,
    selectKeyframe,
    clearError,
  } = useTimelineStore();
  const { currentTime, playing, seek, toggle } = usePlaybackStore();
  const canvas = useRef<HTMLCanvasElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const keyframeImages = useRef(new Map<string, HTMLImageElement>());
  const sceneVideos = useRef(new Map<string, HTMLVideoElement>());
  const [imageRevision, setImageRevision] = useState(0);
  const [videoRevision, setVideoRevision] = useState(0);
  const [videoStates, setVideoStates] = useState(
    new Map<string, SceneVideoState>(),
  );
  const [viewportWidth, setViewportWidth] = useState(800);
  const [scrollX, setScrollX] = useState(0);
  const [pixelsPerSecond, setPixelsPerSecond] = useState(70);
  const [snapMode, setSnapMode] = useState<SnapMode>("beat");
  const [preferredLength, setPreferredLength] = useState(
    Math.min(6, current?.settings.max_clip_length_seconds ?? 10),
  );
  const [drag, setDrag] = useState<DragState>();
  const activeDrag = useRef<DragState | undefined>(undefined);
  const pendingDrag = useRef<PendingDrag | undefined>(undefined);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>();
  const [overlays, setOverlays] = useState<OverlayState>({
    waveform: true,
    beats: true,
    downbeats: true,
    energy: true,
  });

  useEffect(() => {
    if (audio) void load();
  }, [audio, load]);

  useEffect(() => {
    if (!timeline || !active) return;
    let subscriptionActive = true;
    const refresh = async () => {
      try {
        const result = await api.videoTakes.timeline();
        if (subscriptionActive) {
          setVideoStates(
            new Map(
              result.scenes.map((detail) => [
                detail.scene_id,
                sceneVideoState(detail),
              ]),
            ),
          );
        }
      } catch {
        if (subscriptionActive) setVideoStates(new Map());
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 1500);
    window.addEventListener("beatweave:video-takes-changed", refresh);
    return () => {
      subscriptionActive = false;
      window.clearInterval(interval);
      window.removeEventListener("beatweave:video-takes-changed", refresh);
    };
  }, [active, timeline]);

  useEffect(() => {
    if (active) return;
    usePlaybackStore.getState().element?.pause();
  }, [active]);

  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const observer = new ResizeObserver(() =>
      setViewportWidth(element.clientWidth),
    );
    observer.observe(element);
    setViewportWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!active) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      const command = event.ctrlKey || event.metaKey;
      if (
        command &&
        event.key.toLowerCase() === "z" &&
        event.shiftKey &&
        timeline?.can_redo
      ) {
        event.preventDefault();
        void redo();
      } else if (
        command &&
        event.key.toLowerCase() === "z" &&
        timeline?.can_undo
      ) {
        event.preventDefault();
        void undo();
      } else if (
        command &&
        event.key.toLowerCase() === "y" &&
        timeline?.can_redo
      ) {
        event.preventDefault();
        void redo();
      } else if (!command && event.code === "Space") {
        event.preventDefault();
        void toggle();
      } else if (
        !command &&
        (event.key === "ArrowLeft" || event.key === "ArrowRight")
      ) {
        event.preventDefault();
        seek(
          currentTime +
            (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 5 : 0.25),
        );
      } else if (!command && event.key.toLowerCase() === "s") {
        const scene = timeline?.scenes.find(
          (item) => item.id === selectedSceneId,
        );
        if (!scene) return;
        event.preventDefault();
        const candidate =
          currentTime > scene.start_time && currentTime < scene.end_time
            ? currentTime
            : (scene.start_time + scene.end_time) / 2;
        const target = snapTime(
          candidate,
          snapMode,
          analysis?.beats ?? [],
          analysis?.downbeats ?? [],
          12 / pixelsPerSecond,
        );
        void createScene(target?.time ?? candidate, target?.index);
      } else if (
        !command &&
        (event.key === "Delete" || event.key === "Backspace") &&
        selectedSceneId
      ) {
        event.preventDefault();
        if (
          window.confirm(
            "Delete the selected scene and join its neighboring timing?",
          )
        )
          void deleteScene(selectedSceneId);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    analysis,
    active,
    createScene,
    currentTime,
    deleteScene,
    pixelsPerSecond,
    redo,
    seek,
    selectedSceneId,
    snapMode,
    timeline,
    toggle,
    undo,
  ]);

  useEffect(() => {
    const close = () => setContextMenu(undefined);
    window.addEventListener("pointerdown", close);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("blur", close);
    };
  }, []);

  const beats = useMemo(() => analysis?.beats ?? [], [analysis]);
  const downbeats = useMemo(() => analysis?.downbeats ?? [], [analysis]);
  const internalKeyframes = useMemo(
    () =>
      new Set(
        timeline?.scenes.slice(0, -1).map((scene) => scene.end_keyframe_id) ??
          [],
      ),
    [timeline],
  );

  useEffect(() => {
    const wanted = new Map(
      (timeline?.keyframes ?? [])
        .filter((keyframe) => keyframe.selected_variant_asset_id)
        .map((keyframe) => [keyframe.id, keyframe.selected_variant_asset_id!]),
    );
    for (const id of keyframeImages.current.keys()) {
      if (!wanted.has(id)) keyframeImages.current.delete(id);
    }
    wanted.forEach((assetId, keyframeId) => {
      const currentImage = keyframeImages.current.get(keyframeId);
      if (currentImage?.dataset.assetId === assetId) return;
      const image = new Image();
      image.dataset.assetId = assetId;
      image.onload = () => {
        keyframeImages.current.set(keyframeId, image);
        setImageRevision((value) => value + 1);
      };
      image.src = api.media.assetContentUrl(assetId);
    });
  }, [timeline]);

  useEffect(() => {
    const wanted = new Map(
      [...videoStates.entries()]
        .filter((entry): entry is [string, SceneVideoState] =>
          Boolean(entry[1].selected),
        )
        .map(([sceneId, state]) => [sceneId, state.selected!.asset_id]),
    );
    for (const id of sceneVideos.current.keys()) {
      if (!wanted.has(id)) sceneVideos.current.delete(id);
    }
    wanted.forEach((assetId, sceneId) => {
      const currentVideo = sceneVideos.current.get(sceneId);
      if (currentVideo?.dataset.assetId === assetId) return;
      const video = document.createElement("video");
      video.dataset.assetId = assetId;
      video.crossOrigin = "anonymous";
      video.muted = true;
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        video.currentTime = Math.min(0.1, Math.max(0, video.duration / 2));
      };
      video.onseeked = () => {
        sceneVideos.current.set(sceneId, video);
        setVideoRevision((value) => value + 1);
      };
      video.src = api.media.assetContentUrl(assetId);
    });
  }, [videoStates]);

  useEffect(() => {
    if (!active || !canvas.current || !audio || !timeline) return;
    drawTimeline(
      canvas.current,
      viewportWidth,
      pixelsPerSecond,
      scrollX,
      timeline.duration_seconds,
      audio.waveform.peaks,
      beats,
      downbeats,
      analysis?.energy_curve ?? [],
      timeline.scenes,
      timeline.keyframes,
      keyframeImages.current,
      sceneVideos.current,
      videoStates,
      currentTime,
      selectedSceneId,
      selectedKeyframeId,
      overlays,
      drag,
      proposal?.boundaries.slice(1, -1).map((boundary) => boundary.time) ?? [],
    );
  }, [
    analysis,
    active,
    audio,
    beats,
    currentTime,
    downbeats,
    drag,
    overlays,
    imageRevision,
    videoRevision,
    videoStates,
    pixelsPerSecond,
    proposal,
    scrollX,
    selectedKeyframeId,
    selectedSceneId,
    timeline,
    viewportWidth,
  ]);

  if (!audio) {
    return (
      <section className="timeline-empty">
        Import audio before opening the timeline.
      </section>
    );
  }

  const transform = createTimelineTransform(pixelsPerSecond, scrollX);
  const selectedScene = timeline?.scenes.find(
    (scene) => scene.id === selectedSceneId,
  );
  const selectedKeyframe = timeline?.keyframes.find(
    (keyframe) => keyframe.id === selectedKeyframeId,
  );
  const previewScene = timeline?.scenes.find(
    (scene) => scene.start_time <= currentTime && currentTime < scene.end_time,
  );
  const previewState = previewScene
    ? videoStates.get(previewScene.id)
    : undefined;
  const previewSceneIndex = previewScene
    ? (timeline?.scenes.indexOf(previewScene) ?? -1)
    : -1;
  const nextPreviewScene =
    previewSceneIndex >= 0
      ? timeline?.scenes[previewSceneIndex + 1]
      : undefined;
  const nextPreviewAssetId = nextPreviewScene
    ? videoStates.get(nextPreviewScene.id)?.selected?.asset_id
    : undefined;
  const contentWidth = Math.max(
    viewportWidth,
    (timeline?.duration_seconds ?? audio.waveform.duration_seconds) *
      pixelsPerSecond,
  );

  const pointerTime = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return Math.max(
      0,
      Math.min(
        timeline?.duration_seconds ?? 0,
        transform.xToTime(event.clientX - rect.left),
      ),
    );
  };

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.button !== 0) return;
    setContextMenu(undefined);
    if (!timeline) return;
    const time = pointerTime(event);
    const nearest = timeline.keyframes.find(
      (keyframe) => Math.abs(keyframe.time - time) * pixelsPerSecond <= 9,
    );
    if (
      nearest &&
      event.clientY - event.currentTarget.getBoundingClientRect().top >=
        SCENE_TOP - 16
    ) {
      selectKeyframe(nearest.id);
      if (internalKeyframes.has(nearest.id)) {
        event.currentTarget.setPointerCapture(event.pointerId);
        pendingDrag.current = {
          pointerId: event.pointerId,
          keyframeId: nearest.id,
          time: nearest.time,
          x: event.clientX,
          y: event.clientY,
        };
      }
      return;
    }
    if (
      event.clientY - event.currentTarget.getBoundingClientRect().top >=
      SCENE_TOP
    ) {
      const scene = timeline.scenes.find(
        (item) => item.start_time <= time && item.end_time >= time,
      );
      selectScene(scene?.id);
    } else {
      seek(time);
    }
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    let currentDrag = activeDrag.current ?? drag;
    if (!currentDrag && pendingDrag.current) {
      const pending = pendingDrag.current;
      if (
        !exceededDragThreshold(
          pending.x,
          pending.y,
          event.clientX,
          event.clientY,
        )
      )
        return;
      currentDrag = { keyframeId: pending.keyframeId, time: pending.time };
    }
    if (!currentDrag) return;
    const rawTime = pointerTime(event);
    const target = snapTime(
      rawTime,
      snapMode,
      beats,
      downbeats,
      12 / pixelsPerSecond,
      event.altKey,
    );
    const next = { ...currentDrag, time: target?.time ?? rawTime, target };
    activeDrag.current = next;
    setDrag(next);
  };

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    pendingDrag.current = undefined;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    const completed = activeDrag.current ?? drag;
    if (!completed) return;
    activeDrag.current = undefined;
    setDrag(undefined);
    void moveBoundary(
      completed.keyframeId,
      completed.time,
      completed.target?.index,
    );
  };

  const onPointerCancel = (event: React.PointerEvent<HTMLCanvasElement>) => {
    pendingDrag.current = undefined;
    activeDrag.current = undefined;
    setDrag(undefined);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const onContextMenu = (event: React.MouseEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    if (!timeline) return;
    const time = pointerTime(
      event as unknown as React.PointerEvent<HTMLCanvasElement>,
    );
    const keyframe = timeline.keyframes.find(
      (item) => Math.abs(item.time - time) * pixelsPerSecond <= 9,
    );
    const scene = timeline.scenes.find(
      (item) => item.start_time <= time && item.end_time >= time,
    );
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      time,
      sceneId: scene?.id,
      keyframeId: keyframe?.id,
    });
  };

  const onWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      setPixelsPerSecond((value) =>
        Math.max(25, Math.min(180, value - event.deltaY * 0.15)),
      );
    } else if (event.shiftKey && scroll.current) {
      event.preventDefault();
      scroll.current.scrollLeft += event.deltaY;
    }
  };

  const splitSelected = () => {
    if (!selectedScene) return;
    const candidate =
      currentTime > selectedScene.start_time &&
      currentTime < selectedScene.end_time
        ? currentTime
        : (selectedScene.start_time + selectedScene.end_time) / 2;
    const target = snapTime(
      candidate,
      snapMode,
      beats,
      downbeats,
      12 / pixelsPerSecond,
    );
    void createScene(target?.time ?? candidate, target?.index);
  };

  const generatePlan = async () => {
    const hasExisting = Boolean(
      timeline?.scenes.some(
        (scene) => scene.concept || scene.image_prompt || scene.video_prompt,
      ) || timeline?.keyframes.some((keyframe) => keyframe.prompt),
    );
    if (
      hasExisting &&
      !window.confirm(
        "Generate a new visual plan and overwrite existing scene concepts, prompts, and starting-keyframe prompts?",
      )
    )
      return;
    await generateVisualPlan(hasExisting);
  };

  return (
    <div className="timeline-workspace">
      {error && (
        <div className="inline-error" role="alert">
          <span>{error}</span>
          <button onClick={clearError}>Dismiss</button>
        </div>
      )}
      <section className="timeline-toolbar">
        <div className="timeline-toolbar__transport">
          <AudioTransport audio={audio} active={active} />
        </div>
        <button
          className="primary"
          onClick={() =>
            void (timeline?.scenes.length ? splitSelected() : createScene())
          }
          disabled={
            loading || Boolean(timeline?.scenes.length && !selectedScene)
          }
          title="Split at the playhead (S)"
        >
          {timeline?.scenes.length
            ? "Split selected scene"
            : "Create first scene"}
        </button>
        <button
          onClick={() => selectedScene && void deleteScene(selectedScene.id)}
          disabled={loading || !selectedScene}
          title="Delete selected scene (Delete)"
        >
          Delete scene
        </button>
        <label>
          Preferred clip
          <input
            className="timeline-toolbar__number"
            type="number"
            min="1"
            max={current?.settings.max_clip_length_seconds ?? 10}
            step="0.5"
            value={preferredLength}
            onChange={(event) => setPreferredLength(Number(event.target.value))}
          />
        </label>
        <button
          onClick={() =>
            void suggestLayout(preferredLength, Math.min(2, preferredLength))
          }
          disabled={loading || !analysis || preferredLength <= 0}
          title="Preview a beat-aware layout without changing the timeline"
        >
          Suggest Layout
        </button>
        <button
          className="primary"
          onClick={() => void generatePlan()}
          disabled={loading || !analysis || !timeline?.scenes.length}
          title="Create editable concepts and prompts with the configured LLM"
        >
          Generate Visual Plan
        </button>
        <button
          onClick={() => void undo()}
          disabled={loading || !timeline?.can_undo}
          title="Undo (Ctrl+Z)"
        >
          Undo
        </button>
        <button
          onClick={() => void redo()}
          disabled={loading || !timeline?.can_redo}
          title="Redo (Ctrl+Y or Ctrl+Shift+Z)"
        >
          Redo
        </button>
        <label>
          Snap
          <select
            value={snapMode}
            onChange={(event) => setSnapMode(event.target.value as SnapMode)}
          >
            <option value="beat">Beat</option>
            <option value="downbeat">Downbeat</option>
            {downbeats.length > 0 && (
              <>
                <option value="bar-1">1 bar</option>
                <option value="bar-2">2 bars</option>
                <option value="bar-4">4 bars</option>
              </>
            )}
            <option value="free">Free</option>
          </select>
        </label>
      </section>
      {proposal && (
        <section
          className="layout-proposal"
          aria-label="Suggested layout preview"
        >
          <div>
            <span className="eyebrow">Preview only</span>
            <strong>{proposal.boundaries.length - 1} proposed scenes</strong>
            <small>
              {proposal.preferred_length_seconds}s preferred ·{" "}
              {proposal.maximum_length_seconds}s maximum
            </small>
          </div>
          <p>
            Dashed markers show the proposed boundaries. Your current layout is
            unchanged until you apply it.
          </p>
          <button onClick={cancelProposal} disabled={loading}>
            Cancel
          </button>
          <button
            className="primary"
            onClick={() => void applyLayout()}
            disabled={loading}
          >
            Apply layout
          </button>
        </section>
      )}
      <section className="timeline-overlays">
        {(Object.keys(overlays) as (keyof OverlayState)[]).map((name) => (
          <label key={name}>
            <input
              type="checkbox"
              checked={overlays[name]}
              onChange={() =>
                setOverlays((current) => ({
                  ...current,
                  [name]: !current[name],
                }))
              }
            />
            {name}
          </label>
        ))}
        <label className="timeline-overlays__zoom">
          Zoom
          <input
            type="range"
            min="25"
            max="180"
            value={pixelsPerSecond}
            onChange={(event) => setPixelsPerSecond(Number(event.target.value))}
          />
        </label>
        <span className="timeline-toolbar__hint">
          Alt-drag bypasses snapping
        </span>
      </section>
      {loading && (
        <div className="timeline-busy" role="status">
          <span className="spinner" /> Updating timeline…
        </div>
      )}
      <div className="timeline-layout">
        <div className="timeline-main">
          <div
            className="timeline-scroll"
            ref={scroll}
            onScroll={(event) => setScrollX(event.currentTarget.scrollLeft)}
            onWheel={onWheel}
            title="Ctrl+wheel to zoom · Shift+wheel to scroll"
          >
            <div
              className="timeline-scroll__content"
              style={{ width: contentWidth }}
            >
              <canvas
                ref={canvas}
                className="timeline-canvas"
                aria-label="Timeline editor"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerCancel}
                onContextMenu={onContextMenu}
              />
              {drag && (
                <div className="snap-feedback" role="status">
                  {drag.target
                    ? `Snapped to ${drag.target.kind} · ${formatTime(drag.time)}`
                    : `Free position · ${formatTime(drag.time)}`}
                </div>
              )}
            </div>
          </div>
          <TimelineClipPreview
            scene={previewScene}
            state={previewState}
            nextAssetId={nextPreviewAssetId}
            currentTime={currentTime}
            playing={active && playing}
            onSelect={selectScene}
          />
        </div>
        <aside className="timeline-inspector">
          <span className="eyebrow">Inspector</span>
          {selectedScene ? (
            <SceneInspector
              key={`${selectedScene.id}-${selectedScene.updated_at}`}
              scene={selectedScene}
              scenes={timeline?.scenes ?? []}
              loading={loading}
              onSave={(update) => updateScene(selectedScene.id, update)}
              onRegenerate={(confirm) =>
                regenerateScene(selectedScene.id, confirm)
              }
              onTimelineRefresh={load}
            />
          ) : selectedKeyframe ? (
            <KeyframeInspector
              key={selectedKeyframe.id}
              keyframe={selectedKeyframe}
              keyframes={timeline?.keyframes ?? []}
              shared={internalKeyframes.has(selectedKeyframe.id)}
              onTimeline={(updated) =>
                useTimelineStore.setState({ timeline: updated })
              }
            />
          ) : (
            <div className="inspector-empty">
              <span>◇</span>
              <strong>Nothing selected</strong>
              <p>
                Choose a scene to edit prompts and takes, or a diamond keyframe
                to compare image variants.
              </p>
              <small>
                Tip: right-click the timeline for contextual actions.
              </small>
            </div>
          )}
        </aside>
      </div>
      {contextMenu && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
          role="menu"
        >
          <small>{formatTime(contextMenu.time)}</small>
          {contextMenu.sceneId && (
            <button
              role="menuitem"
              onClick={() => {
                const scene = timeline?.scenes.find(
                  (item) => item.id === contextMenu.sceneId,
                );
                if (scene)
                  void updateScene(scene.id, { approved: !scene.approved });
                setContextMenu(undefined);
              }}
            >
              {timeline?.scenes.find((item) => item.id === contextMenu.sceneId)
                ?.approved
                ? "Unapprove scene"
                : "Approve scene"}
            </button>
          )}
          {contextMenu.sceneId && (
            <button
              role="menuitem"
              onClick={() => {
                selectScene(contextMenu.sceneId);
                setContextMenu(undefined);
              }}
            >
              Edit scene
            </button>
          )}
          {contextMenu.keyframeId && (
            <button
              role="menuitem"
              onClick={() => {
                selectKeyframe(contextMenu.keyframeId);
                setContextMenu(undefined);
              }}
            >
              Inspect keyframe
            </button>
          )}
          {contextMenu.sceneId && (
            <button
              role="menuitem"
              onClick={() => {
                selectScene(contextMenu.sceneId);
                seek(contextMenu.time);
                setContextMenu(undefined);
              }}
            >
              Move playhead here
            </button>
          )}
          {contextMenu.sceneId && (
            <button
              role="menuitem"
              onClick={() => {
                void createScene(contextMenu.time);
                setContextMenu(undefined);
              }}
            >
              Split here
            </button>
          )}
          {contextMenu.sceneId && (
            <button
              className="danger"
              role="menuitem"
              onClick={() => {
                if (window.confirm("Delete this scene?"))
                  void deleteScene(contextMenu.sceneId!);
                setContextMenu(undefined);
              }}
            >
              Delete scene
            </button>
          )}
        </div>
      )}
    </div>
  );
}
