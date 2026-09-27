import { useProjectStore } from "../stores/projectStore";

export function AnalysisPanel() {
  const { analysis, analysisJob, loading, analyze } = useProjectStore();
  const active =
    analysisJob?.state === "queued" || analysisJob?.state === "running";
  const failed =
    analysisJob?.state === "failed" ? analysisJob.error : undefined;

  return (
    <section className="analysis-panel">
      <div className="analysis-panel__heading">
        <div>
          <span className="eyebrow">Music analysis</span>
          <h2>{analysis ? "Timing map ready" : "Find the musical pulse"}</h2>
          <p>
            Beat This detects timestamped beats and downbeats; a local feature
            pass measures track energy.
          </p>
        </div>
        <button
          className="primary"
          onClick={() => void analyze(Boolean(analysis))}
          disabled={loading || active}
        >
          {active
            ? "Analyzing…"
            : analysis
              ? "Re-run Analysis"
              : "Analyze Track"}
        </button>
      </div>

      {active && (
        <div
          className="analysis-progress"
          role="progressbar"
          aria-valuenow={analysisJob.progress * 100}
        >
          <span style={{ width: `${analysisJob.progress * 100}%` }} />
          <small>{Math.round(analysisJob.progress * 100)}%</small>
        </div>
      )}

      {failed && (
        <div className="analysis-failure" role="alert">
          <strong>Analysis failed</strong>
          <span>{failed.message}</span>
        </div>
      )}

      {analysis && (
        <dl className="analysis-stats">
          <div>
            <dt>BPM estimate</dt>
            <dd>{analysis.bpm_estimate?.toFixed(1) ?? "—"}</dd>
          </div>
          <div>
            <dt>Detected beats</dt>
            <dd>{analysis.beats.length}</dd>
          </div>
          <div>
            <dt>Downbeats</dt>
            <dd>{analysis.downbeats.length}</dd>
          </div>
          <div>
            <dt>Analyzer</dt>
            <dd>{analysis.parameters.beat_model}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
