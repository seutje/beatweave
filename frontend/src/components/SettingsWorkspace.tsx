import { useState } from "react";

import { BackendConnectivity } from "./BackendConnectivity";
import { ComfyUISettingsPanel } from "./ComfyUISettingsPanel";
import { LLMSettingsPanel } from "./LLMSettingsPanel";
import { MCPSettingsPanel } from "./MCPSettingsPanel";
import { ReliabilityPanel } from "./ReliabilityPanel";
import { Wan2GPSettingsPanel } from "./Wan2GPSettingsPanel";

type Section =
  "connections" | "planning" | "images" | "video" | "mcp" | "recovery";

export function SettingsWorkspace() {
  const [section, setSection] = useState<Section>("connections");
  const tabs: { id: Section; label: string }[] = [
    { id: "connections", label: "Connections" },
    { id: "planning", label: "Planning" },
    { id: "images", label: "Images" },
    { id: "video", label: "Video" },
    { id: "mcp", label: "MCP" },
    { id: "recovery", label: "Recovery" },
  ];
  return (
    <div className="settings-workspace">
      <header>
        <span className="eyebrow">Application settings</span>
        <h1>Services &amp; recovery</h1>
        <p>
          Configure local tools without mixing technical setup into your
          creative workspace.
        </p>
      </header>
      <nav className="settings-tabs" aria-label="Settings sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={section === tab.id ? "active" : ""}
            onClick={() => setSection(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      {section === "connections" && <BackendConnectivity />}
      {section === "planning" && <LLMSettingsPanel />}
      {section === "images" && <ComfyUISettingsPanel />}
      {section === "video" && <Wan2GPSettingsPanel />}
      {section === "mcp" && <MCPSettingsPanel />}
      {section === "recovery" && <ReliabilityPanel />}
    </div>
  );
}
