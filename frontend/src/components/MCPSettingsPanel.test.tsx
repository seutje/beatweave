import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import { MCPSettingsPanel } from "./MCPSettingsPanel";

async function settle() {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

describe("MCP settings", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    invoke.mockReset();
  });

  it("starts the desktop-managed MCP server and shows its endpoint", async () => {
    invoke.mockImplementation((command: string) => {
      if (command === "mcp_status") {
        return Promise.resolve({
          running: false,
          url: "http://127.0.0.1:8421/mcp",
          message: "The MCP server is stopped.",
        });
      }
      return Promise.resolve({
        running: true,
        url: "http://127.0.0.1:8421/mcp",
        message: "The MCP server is accepting local client connections.",
      });
    });
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);

    act(() => root.render(<MCPSettingsPanel />));
    await settle();
    expect(container.textContent).toContain("Stopped");
    expect(container.textContent).toContain("http://127.0.0.1:8421/mcp");

    const start = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "Start MCP server",
    );
    await act(async () => start?.click());

    expect(invoke).toHaveBeenCalledWith("start_mcp_server");
    expect(container.textContent).toContain("Running");
    expect(container.textContent).toContain(
      "accepting local client connections",
    );
  });
});
