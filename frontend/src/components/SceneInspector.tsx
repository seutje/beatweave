import { type FormEvent, useState } from "react";

import type { Scene } from "../api/types";
import { formatTime } from "../lib/audioPlayback";

interface Props {
  scene: Scene;
  loading: boolean;
  onSave: (update: {
    concept: string;
    image_prompt: string;
    video_prompt: string;
  }) => Promise<void>;
  onRegenerate: (confirmOverwrite: boolean) => Promise<void>;
}

export function SceneInspector({
  scene,
  loading,
  onSave,
  onRegenerate,
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

  return (
    <>
      <h2>Scene {scene.position + 1}</h2>
      <dl>
        <dt>Start</dt>
        <dd>{formatTime(scene.start_time)}</dd>
        <dt>End</dt>
        <dd>{formatTime(scene.end_time)}</dd>
        <dt>Visual / motion</dt>
        <dd>
          {Math.round(scene.visual_energy * 100)}% /{" "}
          {Math.round(scene.motion_energy * 100)}%
        </dd>
      </dl>
      <form
        className="scene-prompt-form"
        onSubmit={(event) => void save(event)}
      >
        <label>
          Concept
          <textarea
            value={concept}
            onChange={(event) => setConcept(event.target.value)}
          />
        </label>
        <label>
          Image prompt
          <textarea
            value={imagePrompt}
            onChange={(event) => setImagePrompt(event.target.value)}
          />
        </label>
        <label>
          Video prompt
          <textarea
            value={videoPrompt}
            onChange={(event) => setVideoPrompt(event.target.value)}
          />
        </label>
        <button className="primary" disabled={!dirty || loading}>
          Save prompts
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => void regenerate()}
        >
          Regenerate scene
        </button>
      </form>
    </>
  );
}
