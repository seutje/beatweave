import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { Keyframe, Scene } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import { usePlaybackStore } from "../stores/playbackStore";
import { useProjectStore } from "../stores/projectStore";
import { useTimelineStore } from "../stores/timelineStore";
import { snapTime, type SnapMode, type SnapTarget } from "../timeline/snapping";
import { createTimelineTransform } from "../timeline/transform";
import { AudioTransport } from "./AudioTransport";
import { KeyframeInspector } from "./KeyframeInspector";
import { SceneInspector } from "./SceneInspector";

const HEIGHT = 292;
const SCENE_TOP = 188;
const SCENE_BOTTOM = 258;

interface DragState {
  keyframeId: string;
  time: number;
  target?: SnapTarget;
}

interface OverlayState {
  waveform: boolean;
  beats: boolean;
  downbeats: boolean;
  energy: boolean;
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
    context.fillStyle = scene.id === selectedSceneId ? "#344d92" : "#1b2a46";
    context.strokeStyle = scene.id === selectedSceneId ? "#8292ff" : "#3a4c69";
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

export function TimelineWorkspace() {
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
  const { currentTime, seek } = usePlaybackStore();
  const canvas = useRef<HTMLCanvasElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const keyframeImages = useRef(new Map<string, HTMLImageElement>());
  const [imageRevision, setImageRevision] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(800);
  const [scrollX, setScrollX] = useState(0);
  const [pixelsPerSecond, setPixelsPerSecond] = useState(70);
  const [snapMode, setSnapMode] = useState<SnapMode>("beat");
  const [preferredLength, setPreferredLength] = useState(
    Math.min(6, current?.settings.max_clip_length_seconds ?? 10),
  );
  const [drag, setDrag] = useState<DragState>();
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
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
        return;
      }
      const command = event.ctrlKey || event.metaKey;
      if (!command) return;
      if (
        event.key.toLowerCase() === "z" &&
        event.shiftKey &&
        timeline?.can_redo
      ) {
        event.preventDefault();
        void redo();
      } else if (event.key.toLowerCase() === "z" && timeline?.can_undo) {
        event.preventDefault();
        void undo();
      } else if (event.key.toLowerCase() === "y" && timeline?.can_redo) {
        event.preventDefault();
        void redo();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [redo, timeline?.can_redo, timeline?.can_undo, undo]);

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
    if (!canvas.current || !audio || !timeline) return;
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
      currentTime,
      selectedSceneId,
      selectedKeyframeId,
      overlays,
      drag,
      proposal?.boundaries.slice(1, -1).map((boundary) => boundary.time) ?? [],
    );
  }, [
    analysis,
    audio,
    beats,
    currentTime,
    downbeats,
    drag,
    overlays,
    imageRevision,
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
        setDrag({ keyframeId: nearest.id, time: nearest.time });
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
    if (!drag) return;
    const rawTime = pointerTime(event);
    const target = snapTime(
      rawTime,
      snapMode,
      beats,
      downbeats,
      12 / pixelsPerSecond,
      event.altKey,
    );
    setDrag({ ...drag, time: target?.time ?? rawTime, target });
  };

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    const completed = drag;
    setDrag(undefined);
    void moveBoundary(
      completed.keyframeId,
      completed.time,
      completed.target?.index,
    );
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
      ),
    );
    if (
      hasExisting &&
      !window.confirm(
        "Generate a new visual plan and overwrite existing scene concepts and prompts?",
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
      <section className="timeline-header">
        <div>
          <span className="eyebrow">Timeline V1</span>
          <h1>Music-aware edit</h1>
        </div>
        <AudioTransport audio={audio} />
      </section>
      <section className="timeline-toolbar">
        <button
          className="primary"
          onClick={() =>
            void (timeline?.scenes.length ? splitSelected() : createScene())
          }
          disabled={
            loading || Boolean(timeline?.scenes.length && !selectedScene)
          }
        >
          {timeline?.scenes.length
            ? "Split selected scene"
            : "Create first scene"}
        </button>
        <button
          onClick={() => selectedScene && void deleteScene(selectedScene.id)}
          disabled={loading || !selectedScene}
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
        >
          Suggest Layout
        </button>
        <button
          className="primary"
          onClick={() => void generatePlan()}
          disabled={loading || !analysis || !timeline?.scenes.length}
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
        <label>
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
          Hold Alt while dragging to bypass snapping
        </span>
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
      </section>
      <div className="timeline-layout">
        <div
          className="timeline-scroll"
          ref={scroll}
          onScroll={(event) => setScrollX(event.currentTarget.scrollLeft)}
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
            />
          </div>
        </div>
        <aside className="timeline-inspector">
          <span className="eyebrow">Inspector</span>
          {selectedScene ? (
            <SceneInspector
              key={`${selectedScene.id}-${selectedScene.updated_at}`}
              scene={selectedScene}
              loading={loading}
              onSave={(update) => updateScene(selectedScene.id, update)}
              onRegenerate={(confirm) =>
                regenerateScene(selectedScene.id, confirm)
              }
            />
          ) : selectedKeyframe ? (
            <KeyframeInspector
              key={selectedKeyframe.id}
              keyframe={selectedKeyframe}
              shared={internalKeyframes.has(selectedKeyframe.id)}
              onTimeline={(updated) =>
                useTimelineStore.setState({ timeline: updated })
              }
            />
          ) : (
            <p>Select a scene or keyframe on the timeline.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
