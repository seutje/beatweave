import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { AssetMetadata, Scene } from "../api/types";
import { SceneInspector } from "./SceneInspector";

vi.mock("./VideoTakesPanel", () => ({ VideoTakesPanel: () => null }));
vi.mock("../api/client", () => ({
  api: {
    videoTakes: { previousFrame: vi.fn() },
    media: { assetContentUrl: (id: string) => `/assets/${id}` },
  },
}));

const scene: Scene = {
  id: "second",
  position: 1,
  start_time: 1,
  end_time: 2,
  start_keyframe_id: "shared",
  end_keyframe_id: "end",
  concept: "",
  image_prompt: "",
  video_prompt: "Move",
  visual_energy: 0,
  motion_energy: 0,
  selected_video_take_id: null,
  selected_video_take_stale: false,
  approved: false,
  use_last_frame_conditioning: true,
  use_previous_scene_frame: false,
  created_at: "",
  updated_at: "",
};

describe("previous scene start frame", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;
  const onSave = vi.fn(async () => {});
  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    vi.mocked(api.videoTakes.previousFrame).mockResolvedValue({
      id: "invisible",
    } as AssetMetadata);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.clearAllMocks();
  });
  const mount = async (value: Scene, activeTab: "video" | "start-frame") => {
    await act(async () =>
      root.render(
        <SceneInspector
          scene={value}
          scenes={[value]}
          loading={false}
          activeTab={activeTab}
          frameContent={<div>Planned keyframe</div>}
          onSave={onSave}
          onRegenerate={async () => {}}
          onTimelineRefresh={async () => {}}
          onTabChange={() => {}}
        />,
      ),
    );
  };

  it("shows the checkbox after the first scene and persists toggles", async () => {
    await mount(scene, "video");
    const checkbox = container.querySelector<HTMLInputElement>(
      '[aria-label="use last frame of prev scene"]',
    )!;
    expect(checkbox.checked).toBe(false);
    await act(async () => checkbox.click());
    expect(onSave).toHaveBeenCalledWith({ use_previous_scene_frame: true });
    await mount({ ...scene, position: 0 }, "video");
    expect(
      container.querySelector('[aria-label="use last frame of prev scene"]'),
    ).toBeNull();
  });

  it("shows the extracted frame as selected only when enabled", async () => {
    await mount({ ...scene, use_previous_scene_frame: true }, "start-frame");
    expect(api.videoTakes.previousFrame).toHaveBeenCalledWith("second");
    expect(container.textContent).toContain("✓ Selected");
    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "/assets/invisible",
    );
    expect(container.textContent).not.toContain("Planned keyframe");
    await mount(scene, "start-frame");
    expect(container.textContent).toContain("Planned keyframe");
  });

  it("explains when the previous scene has no continuation frame", async () => {
    vi.mocked(api.videoTakes.previousFrame).mockRejectedValue(
      new Error("No frame after the cut"),
    );
    await mount({ ...scene, use_previous_scene_frame: true }, "start-frame");
    expect(container.querySelector('[role="status"]')?.textContent).toContain(
      "No frame after the cut",
    );
    expect(container.querySelector("img")).toBeNull();
  });
});
