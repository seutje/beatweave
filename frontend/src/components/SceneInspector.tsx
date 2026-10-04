import { type FormEvent, type ReactNode, useState } from "react";

import type { Scene } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import type { TimelineInspectorTab } from "../stores/timelineStore";
import { VideoTakesPanel } from "./VideoTakesPanel";

interface Props {
  scene: Scene;
  scenes: Scene[];
  loading: boolean;
  activeTab: TimelineInspectorTab;
  frameContent?: ReactNode;
  onSave: (update: {
    concept?: string;
    image_prompt?: string;
    video_prompt?: string;
    approved?: boolean;
    use_last_frame_conditioning?: boolean;
  }) => Promise<void>;
  onRegenerate: (confirmOverwrite: boolean) => Promise<void>;
  onTimelineRefresh: () => Promise<void>;
  onTabChange: (tab: TimelineInspectorTab) => void;
}

export function SceneInspector({
  scene,
  scenes,
  loading,
  activeTab,
  frameContent,
  onSave,
  onRegenerate,
  onTimelineRefresh,
  onTabChange,
}: Props) {
  const [concept, setConcept] = useState(scene.concept);
  const [imagePrompt, setImagePrompt] = useState(scene.image_prompt);
  const [videoPrompt, setVideoPrompt] = useState(scene.video_prompt);

  const dirty =
    concept !== scene.concept ||
    imagePrompt !== scene.image_prompt ||
    videoPrompt !== scene.video_prompt;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    await onSave({
      concept,
      image_prompt: imagePrompt,
      video_prompt: videoPrompt,
    });
  };

  const regenerate = async () => {
    const hasExisting =
      dirty ||
      Boolean(scene.concept || scene.image_prompt || scene.video_prompt);
    if (
      hasExisting &&
      !window.confirm(
        "Regenerate this scene and overwrite its current concept and prompts?",
      )
    )
      return;
    await onRegenerate(hasExisting);
  };

  const duration = scene.end_time - scene.start_time;
  const beatCount =
    scene.start_beat_index !== undefined && scene.end_beat_index !== undefined
      ? scene.end_beat_index - scene.start_beat_index
      : undefined;

  return (
    <div className="scene-inspector">
      <header className="scene-inspector__header">
        <div className="scene-inspector__identity">
          <span className="scene-inspector__mark" aria-hidden="true">
            ◇
          </span>
          <div>
            <h2>Scene {scene.position + 1}</h2>
            <p>
              {beatCount !== undefined && <>{beatCount} beats · </>}
              {duration.toFixed(1)}s
            </p>
          </div>
        </div>
        <button
          type="button"
          className={
            scene.approved ? "scene-approval is-approved" : "scene-approval"
          }
          disabled={loading}
          aria-pressed={scene.approved}
          onClick={() => void onSave({ approved: !scene.approved })}
        >
          {scene.approved ? "✓ Approved" : "Approve"}
        </button>
      </header>

      <nav className="scene-inspector__tabs" aria-label="Scene inspector tabs">
        {(
          [
            ["prompts", "Prompts"],
            ["video", "Video"],
            ["start-frame", "Start frame"],
            ["end-frame", "End frame"],
          ] as const
        ).map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? "is-active" : ""}
            aria-pressed={activeTab === tab}
            onClick={() => onTabChange(tab)}
          >
            {label}
          </button>
        ))}
      </nav>

      {activeTab === "video" && (
        <section className="scene-inspector__section scene-inspector__timing">
          <div className="scene-inspector__section-heading">
            <span>Timing</span>
            <small>Timeline locked</small>
          </div>
          <dl>
            <div>
              <dt>Start</dt>
              <dd>{formatTime(scene.start_time)}</dd>
            </div>
            <div>
              <dt>End</dt>
              <dd>{formatTime(scene.end_time)}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{duration.toFixed(1)}s</dd>
            </div>
          </dl>
        </section>
      )}

      {activeTab === "prompts" && (
        <form
          className="scene-prompt-form"
          onSubmit={(event) => void save(event)}
        >
          <label className="scene-prompt-field">
            <span>Concept</span>
            <textarea
              value={concept}
              onChange={(event) => setConcept(event.target.value)}
              placeholder="Describe this scene's visual idea…"
            />
          </label>
          <label className="scene-prompt-field">
            <span>
              Image prompt <small>Keyframe appearance</small>
            </span>
            <textarea
              value={imagePrompt}
              onChange={(event) => setImagePrompt(event.target.value)}
              placeholder="Describe the scene's starting keyframe…"
            />
          </label>
          <label className="scene-prompt-field">
            <span>
              Video prompt <small>Motion and evolution</small>
            </span>
            <textarea
              value={videoPrompt}
              onChange={(event) => setVideoPrompt(event.target.value)}
              placeholder="Describe how motion develops through the scene…"
            />
          </label>
          <div className="scene-prompt-form__actions">
            <button className="primary" disabled={!dirty || loading}>
              Save changes
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => void regenerate()}
            >
              ✦ Regenerate
            </button>
          </div>
        </form>
      )}

      {activeTab === "prompts" && (
        <section className="scene-inspector__section scene-inspector__energy">
          <div className="scene-inspector__meter">
            <div>
              <span>Visual energy</span>
              <strong>{scene.visual_energy.toFixed(1)}</strong>
            </div>
            <progress value={scene.visual_energy} max={1} />
          </div>
          <div className="scene-inspector__meter is-motion">
            <div>
              <span>Motion energy</span>
              <strong>{scene.motion_energy.toFixed(1)}</strong>
            </div>
            <progress value={scene.motion_energy} max={1} />
          </div>
        </section>
      )}

      {activeTab === "video" && (
        <>
          <section className="scene-inspector__section">
            <label className="scene-inspector__toggle">
              <span>
                <strong>Last-frame conditioning</strong>
                <small>Guide the render toward the next keyframe</small>
              </span>
              <input
                type="checkbox"
                aria-label="Use last-frame conditioning"
                checked={scene.use_last_frame_conditioning}
                disabled={loading}
                onChange={(event) =>
                  void onSave({
                    use_last_frame_conditioning: event.target.checked,
                  })
                }
              />
            </label>
          </section>
          <VideoTakesPanel
            scene={scene}
            scenes={scenes}
            onTimelineRefresh={onTimelineRefresh}
          />
        </>
      )}

      {(activeTab === "start-frame" || activeTab === "end-frame") && (
        <div className="scene-inspector__frame">{frameContent}</div>
      )}
    </div>
  );
}
