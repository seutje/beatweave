import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import type { VideoModelProfile, Wan2GPConfig } from "../api/types";
import { Wan2GPSettingsPanel } from "./Wan2GPSettingsPanel";

function initialConfig(): Wan2GPConfig {
  const ltx: VideoModelProfile = {
    name: "ltx-2.3-distilled-1.1",
    model_type: "ltx2_22B_distilled_1_1",
    settings_version: 2.73,
    preview: { resolution: "768x448", inference_steps: 6 },
    final: { resolution: "1920x1088", inference_steps: 8 },
    default_frame_rate: 24,
    minimum_frames: 17,
    frame_step: 8,
  };
  const h3: VideoModelProfile = {
    ...ltx,
    name: "minimax-h3-fl2va-33b",
    model_type: "minimax_h3_fl2va",
    preview: { resolution: "832x480", inference_steps: 20 },
    final: { resolution: "1920x1088", inference_steps: 20 },
    minimum_frames: 107,
    frame_step: 17,
    sample_solver: "euler",
    flow_shift: 12,
  };
  const pruned = {
    ...h3,
    name: "minimax-h3-fl2va-pruned-20b",
    model_type: "minimax_h3_fl2va_pruned",
  };
  return {
    base_url: "http://localhost:7860",
    request_timeout_seconds: 30,
    render_timeout_seconds: 7200,
    poll_interval_seconds: 0.5,
    profile: ltx,
    profiles: { [ltx.name]: ltx, [h3.name]: h3, [pruned.name]: pruned },
    audio_reactive_profile: {
      name: "ltx-2.3-audio-reactive-v2",
      filename: "ltx2.3_audio_reactive_lora_v2.safetensors",
      default_multiplier: 1,
      trigger_phrase: "",
    },
  };
}

describe("Wan2GP renderer settings", () => {
  let root: ReturnType<typeof createRoot> | undefined;
  let container: HTMLDivElement;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    vi.restoreAllMocks();
  });

  it("switches all three models, retains edits and saves the active profile", async () => {
    vi.spyOn(api.wan2gp, "config").mockResolvedValue(initialConfig());
    const save = vi
      .spyOn(api.wan2gp, "updateConfig")
      .mockImplementation(async (config) => config);
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<Wan2GPSettingsPanel />);
    });

    const select = container.querySelector("select")!;
    expect(select.options).toHaveLength(3);
    const switchTo = async (name: string) => {
      await act(async () => {
        select.value = name;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
    };
    expect(container.textContent).toContain("LoRA filename");
    await switchTo("minimax-h3-fl2va-33b");
    expect(container.textContent).toContain("H3 sampling");
    expect(container.textContent).not.toContain("LoRA filename");
    expect(container.textContent).toContain("4.46 seconds");
    const resolution = container.querySelector(
      "fieldset input",
    ) as HTMLInputElement;
    expect(resolution.value).toBe("832x480");
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )!.set!.call(resolution, "960x544");
      resolution.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await switchTo("minimax-h3-fl2va-pruned-20b");
    expect(
      (container.querySelector("fieldset input") as HTMLInputElement).value,
    ).toBe("832x480");
    await switchTo("ltx-2.3-distilled-1.1");
    expect(container.textContent).toContain("LoRA filename");
    expect(container.textContent).not.toContain("H3 sampling");
    expect(
      (container.querySelector("fieldset input") as HTMLInputElement).value,
    ).toBe("768x448");
    await switchTo("minimax-h3-fl2va-33b");
    expect(
      (container.querySelector("fieldset input") as HTMLInputElement).value,
    ).toBe("960x544");
    await act(async () => {
      container
        .querySelector("form")!
        .dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
    });
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        profile: expect.objectContaining({ name: "minimax-h3-fl2va-33b" }),
      }),
    );
  });
});
