import type { AnalysisJob, BackendEvent } from "../api/types";

export function trackedJobFromEvent(
  event: BackendEvent,
  jobId: string,
): AnalysisJob | undefined {
  if (!event.type.startsWith("job-") || event.payload.id !== jobId) {
    return undefined;
  }
  return event.payload as unknown as AnalysisJob;
}
