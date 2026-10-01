import type { AudioAnalysis, AudioState, Timeline } from "../api/types";

interface Props {
  audio?: AudioState;
  analysis?: AudioAnalysis;
  timeline?: Timeline;
  onNavigate: (view: "Overview" | "Timeline" | "Settings") => void;
}

interface GuideStep {
  label: string;
  done: boolean;
  view: "Overview" | "Timeline" | "Settings";
  optional?: boolean;
}

export function WorkflowGuide({
  audio,
  analysis,
  timeline,
  onNavigate,
}: Props) {
  const steps: GuideStep[] = [
    { label: "Import a source track", done: Boolean(audio), view: "Overview" },
    {
      label: "Analyze beats and energy",
      done: Boolean(analysis),
      view: "Overview",
    },
    {
      label: "Build the scene timeline",
      done: Boolean(timeline?.scenes.length),
      view: "Timeline",
    },
    {
      label: "Connect creative backends",
      done: false,
      view: "Settings",
      optional: true,
    },
  ];
  const next = steps.find((step) => !step.done && !step.optional) ?? steps[3];

  return (
    <section className="workflow-guide" aria-label="Project setup guide">
      <div>
        <span className="eyebrow">Getting started</span>
        <h2>Your path from track to video</h2>
        <p>Work left to right. Backends can stay offline until you render.</p>
      </div>
      <ol>
        {steps.map((step, index) => (
          <li className={step.done ? "is-complete" : ""} key={step.label}>
            <span>{step.done ? "✓" : index + 1}</span>
            <button onClick={() => onNavigate(step.view)}>{step.label}</button>
            {step.optional && <small>optional now</small>}
          </li>
        ))}
      </ol>
      <button className="primary" onClick={() => onNavigate(next.view)}>
        Continue: {next.label}
      </button>
    </section>
  );
}
