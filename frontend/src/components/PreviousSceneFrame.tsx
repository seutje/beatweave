import { useEffect, useState } from "react";

import { api } from "../api/client";

export function PreviousSceneFrame({ sceneId }: { sceneId: string }) {
  const [assetId, setAssetId] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    let pending = false;
    const load = async () => {
      if (pending) return;
      pending = true;
      try {
        const asset = await api.videoTakes.previousFrame(sceneId);
        if (active) {
          setAssetId(asset.id);
          setError(undefined);
        }
      } catch (reason) {
        if (active) {
          setAssetId(undefined);
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load previous scene frame.",
          );
        }
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [sceneId]);

  return (
    <section
      className="scene-inspector__section"
      aria-label="Selected start frame"
    >
      <strong>✓ Selected · Previous scene frame</strong>
      <p>
        First invisible frame after the previous scene’s timeline cut. Resolved
        when this render starts.
      </p>
      {assetId && (
        <img
          style={{ width: "100%" }}
          src={api.media.assetContentUrl(assetId)}
          alt="Selected first invisible frame of previous scene"
        />
      )}
      {error && <p role="status">{error}</p>}
      {!assetId && !error && <p>Loading start frame…</p>}
    </section>
  );
}
