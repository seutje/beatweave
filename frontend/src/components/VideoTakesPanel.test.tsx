import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { AnalysisJob, Scene, SceneVideoTakes } from "../api/types";
import { VideoTakesPanel } from "./VideoTakesPanel";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../api/client", () => ({
  api: {
    videoTakes: { detail: vi.fn(), render: vi.fn() },
    jobs: { list: vi.fn(), get: vi.fn() },
  },
}));

const scene: Scene = {
  id: "scene-1",
  position: 0,
  start_time: 0,
  end_time: 1,
  start_keyframe_id: "start",
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
const detail: SceneVideoTakes = {
  scene_id: scene.id,
  selected_take_id: null,
  selected_take_stale: false,
  takes: [],
  render_jobs: [],
};

describe("render monitoring recovery", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(api.videoTakes.detail).mockResolvedValue(detail);
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.resetAllMocks();
  });
  const mount = async () => {
    await act(async () =>
      root.render(
        <VideoTakesPanel
          scene={scene}
          scenes={[scene, { ...scene, id: "scene-2", position: 1 }]}
          onTimelineRefresh={async () => {}}
        />,
      ),
    );
  };

  it("retries an initially disconnected inspector and clears its connection error", async () => {
    vi.mocked(api.videoTakes.detail).mockRejectedValueOnce(
      new Error("Beatweave could not reach its local backend."),
    );
    await mount();
    expect(container.textContent).toContain("could not reach");
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(api.videoTakes.detail).toHaveBeenCalledTimes(2);
    expect(container.textContent).not.toContain("could not reach");
    expect(container.textContent).toContain("No video takes yet");
  });

  it("does not overlap requests while a previous poll is pending", async () => {
    vi.mocked(api.videoTakes.detail).mockReturnValue(new Promise(() => {}));
    await mount();
    await act(async () => vi.advanceTimersByTimeAsync(6000));
    expect(api.videoTakes.detail).toHaveBeenCalledTimes(1);
  });

  it("uses one job-list request for a batch and recovers after a failed poll", async () => {
    vi.mocked(api.videoTakes.render)
      .mockResolvedValueOnce({ job: { id: "job-1" } as AnalysisJob })
      .mockResolvedValueOnce({ job: { id: "job-2" } as AnalysisJob });
    vi.mocked(api.jobs.list)
      .mockRejectedValueOnce(
        new Error("Beatweave could not reach its local backend."),
      )
      .mockResolvedValue([
        { id: "job-1", state: "complete" } as AnalysisJob,
        { id: "job-2", state: "complete" } as AnalysisJob,
      ]);
    await mount();
    const button = [...container.querySelectorAll("button")].find(
      (item) => item.textContent === "Render all",
    );
    await act(async () => button?.click());
    expect(api.videoTakes.render).toHaveBeenNthCalledWith(
      1,
      "scene-1",
      "final",
      undefined,
      true,
      undefined,
    );
    expect(api.videoTakes.render).toHaveBeenNthCalledWith(
      2,
      "scene-2",
      "final",
      undefined,
      true,
      "job-1",
    );
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(api.jobs.list).toHaveBeenCalledTimes(2);
    expect(api.jobs.get).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain("Rendering ");
    expect(container.textContent).not.toContain("could not reach");
  });
});
