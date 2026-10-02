import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  timelineMounts: 0,
  timelineUnmounts: 0,
}));

vi.mock("./hooks/useBackend", () => ({
  useBackend: () => ({ state: "connected", retry: vi.fn() }),
}));

vi.mock("./stores/projectStore", () => ({
  useProjectStore: () => ({
    current: { id: "project-1", name: "Test project" },
    load: vi.fn(),
  }),
}));

vi.mock("./components/ProjectLauncher", () => ({
  ProjectLauncher: () => <div>Launcher</div>,
}));
vi.mock("./components/ProjectOverview", () => ({
  ProjectOverview: () => <div>Project overview content</div>,
}));
vi.mock("./components/RenderQueue", () => ({
  RenderQueue: () => <div>Render queue</div>,
}));
vi.mock("./components/SettingsWorkspace", () => ({
  SettingsWorkspace: () => <div>Settings workspace</div>,
}));
vi.mock("./components/TimelineWorkspace", () => ({
  TimelineWorkspace: ({ active }: { active: boolean }) => {
    useEffect(() => {
      state.timelineMounts += 1;
      return () => {
        state.timelineUnmounts += 1;
      };
    }, []);
    return <div data-active={active}>Timeline content</div>;
  },
}));

import { App } from "./App";

function clickButton(container: HTMLElement, label: string) {
  const button = [...container.querySelectorAll("button")].find((candidate) =>
    candidate.textContent?.includes(label),
  );
  if (!button) throw new Error(`Could not find ${label} button`);
  button.click();
}

describe("workspace navigation", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    state.timelineMounts = 0;
    state.timelineUnmounts = 0;
  });

  it("keeps the timeline mounted while visiting the overview", () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);

    act(() => root.render(<App />));
    act(() => clickButton(container, "Timeline"));
    expect(state.timelineMounts).toBe(1);

    act(() => clickButton(container, "Overview"));
    expect(state.timelineUnmounts).toBe(0);
    expect(
      container
        .querySelector("main")
        ?.classList.contains("workspace--overview"),
    ).toBe(true);
    expect(
      container
        .querySelector("main")
        ?.classList.contains("workspace--timeline"),
    ).toBe(false);
    expect(
      container.querySelector("[data-active='false']")?.parentElement,
    ).toHaveProperty("hidden", true);

    act(() => clickButton(container, "Timeline"));
    expect(state.timelineMounts).toBe(1);
    expect(state.timelineUnmounts).toBe(0);
    expect(
      container.querySelector("[data-active='true']")?.parentElement,
    ).toHaveProperty("hidden", false);
    expect(
      container
        .querySelector("main")
        ?.classList.contains("workspace--timeline"),
    ).toBe(true);
  });
});
