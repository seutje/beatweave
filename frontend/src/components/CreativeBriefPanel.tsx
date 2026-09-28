import { open } from "@tauri-apps/plugin-dialog";
import { type FormEvent, useState } from "react";

import { api } from "../api/client";
import type { CreativeBrief } from "../api/types";
import { useProjectStore } from "../stores/projectStore";
import { joinList, splitList } from "./creativeBriefLists";

export function CreativeBriefPanel() {
  const {
    current,
    styleReferences,
    loading,
    updateProject,
    importStyleReference,
    removeStyleReference,
  } = useProjectStore();
  const [brief, setBrief] = useState<CreativeBrief>(
    current?.creative_brief ?? {
      concept: "",
      style: "",
      motifs: [],
      palette: [],
      narrative_arc: "",
      negative_guidance: "",
      visual_trajectory: [],
    },
  );
  const [motifsDraft, setMotifsDraft] = useState(() =>
    joinList(current?.creative_brief.motifs ?? []),
  );
  const [paletteDraft, setPaletteDraft] = useState(() =>
    joinList(current?.creative_brief.palette ?? []),
  );
  if (!current) return null;
  const editedBrief = {
    ...brief,
    motifs: splitList(motifsDraft),
    palette: splitList(paletteDraft),
  };
  const dirty =
    JSON.stringify(editedBrief) !== JSON.stringify(current.creative_brief);
  const update = <K extends keyof CreativeBrief>(
    key: K,
    value: CreativeBrief[K],
  ) => setBrief((existing) => ({ ...existing, [key]: value }));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBrief(editedBrief);
    await updateProject({ creative_brief: editedBrief });
  };

  const chooseReference = async () => {
    const path = await open({
      multiple: false,
      directory: false,
      title: "Import style reference",
      filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
    });
    if (path) await importStyleReference(path);
  };

  return (
    <section className="creative-brief">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Creative direction</span>
          <h2>Visual brief</h2>
        </div>
        <button onClick={() => void chooseReference()} disabled={loading}>
          Add reference
        </button>
      </div>
      <form onSubmit={(event) => void save(event)}>
        <label>
          Concept
          <textarea
            value={brief.concept}
            onChange={(event) => update("concept", event.target.value)}
          />
        </label>
        <label>
          Style
          <textarea
            value={brief.style}
            onChange={(event) => update("style", event.target.value)}
          />
        </label>
        <label className="creative-brief__wide">
          Narrative / visual arc
          <textarea
            value={brief.narrative_arc}
            onChange={(event) => update("narrative_arc", event.target.value)}
          />
        </label>
        <label>
          Motifs
          <input
            value={motifsDraft}
            onChange={(event) => setMotifsDraft(event.target.value)}
            placeholder="glass, roots, particles"
          />
        </label>
        <label>
          Palette
          <input
            value={paletteDraft}
            onChange={(event) => setPaletteDraft(event.target.value)}
            placeholder="cyan, amber, black"
          />
        </label>
        <label className="creative-brief__wide">
          Negative guidance
          <textarea
            value={brief.negative_guidance}
            onChange={(event) =>
              update("negative_guidance", event.target.value)
            }
          />
        </label>
        <div className="creative-brief__actions">
          <button className="primary" disabled={!dirty || loading}>
            Save brief
          </button>
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
        </div>
      </form>
      {brief.visual_trajectory.length > 0 && (
        <div className="visual-trajectory">
          <h3>Generated visual trajectory</h3>
          <ol>
            {brief.visual_trajectory.map((stage) => (
              <li key={`${stage.position}-${stage.description}`}>
                <span>{Math.round(stage.position * 100)}%</span>
                <p>{stage.description}</p>
                <small>Intensity {Math.round(stage.intensity * 100)}%</small>
              </li>
            ))}
          </ol>
        </div>
      )}
      <div className="reference-gallery">
        {styleReferences.length === 0 ? (
          <p>No style references imported.</p>
        ) : (
          styleReferences.map((asset) => (
            <figure key={asset.id}>
              <img
                src={api.media.referenceContentUrl(asset.id)}
                alt={asset.filename}
              />
              <figcaption>
                <span>{asset.filename}</span>
                <button
                  onClick={() => void removeStyleReference(asset.id)}
                  disabled={loading}
                >
                  Remove
                </button>
              </figcaption>
            </figure>
          ))
        )}
      </div>
    </section>
  );
}
