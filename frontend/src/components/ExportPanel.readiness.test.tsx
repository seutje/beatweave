import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { ExportReadiness } from "../api/types";
import { ExportPanel } from "./ExportPanel";

vi.mock("../api/client", () => ({
  api: { exports: { readiness: vi.fn(), start: vi.fn() } },
}));
vi.mock("../api/events", () => ({ connectToEvents: vi.fn() }));

const readiness: ExportReadiness = {
  ready: true,
  scene_count: 2,
  duration_seconds: 2,
  issues: [],
  warnings: [
    {
      code: "selected_take_stale",
      scene_id: "scene-1",
      message:
        "Scene 1's selected take is stale. Export will use the selected take as-is.",
    },
  ],
};

describe("export readiness", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    vi.mocked(api.exports.readiness).mockResolvedValue(readiness);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.resetAllMocks();
  });

  it("shows stale warnings and allows exporting the selected sequence", async () => {
    await act(async () => root.render(<ExportPanel projectName="Test" />));

    expect(
      container.querySelector('[aria-label="Export warnings"]')?.textContent,
    ).toContain(readiness.warnings[0].message);
    const button = container.querySelector<HTMLButtonElement>("button.primary");
    expect(button?.disabled).toBe(false);
    vi.mocked(api.exports.start).mockReturnValue(new Promise(() => {}));
    await act(async () => button?.click());
    expect(api.exports.start).toHaveBeenCalledWith(
      expect.objectContaining({ filename: "Test-final.mp4" }),
    );
  });

  it("keeps export disabled when a stale take also has missing media", async () => {
    vi.mocked(api.exports.readiness).mockResolvedValue({
      ...readiness,
      ready: false,
      issues: [
        {
          code: "selected_take_file_missing",
          scene_id: "scene-1",
          message: "Scene 1's video file is missing.",
        },
      ],
    });
    await act(async () => root.render(<ExportPanel projectName="Test" />));

    expect(container.textContent).toContain("Scene 1's video file is missing.");
    expect(container.textContent).toContain(readiness.warnings[0].message);
    expect(
      container.querySelector<HTMLButtonElement>("button.primary")?.disabled,
    ).toBe(true);
    expect(api.exports.start).not.toHaveBeenCalled();
  });
});
