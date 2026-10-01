import type { RunStatus, TaskStatus } from "@/lib/types";
const labels: Record<TaskStatus | RunStatus, string> = {
  pending: "Waiting", active: "Browsing", success: "Reached goal", failed: "Failed", abandoned: "Gave up",
  budget_exhausted: "Out of steps", blocked_by_verification: "Blocked", error: "Error",
  created: "Created", cohort_ready: "Ready to deploy", running: "Running", aggregating: "Analyzing", completed: "Completed",
};
export const statusLabel = (status: TaskStatus | RunStatus) => labels[status] ?? String(status).replaceAll("_", " ");
export function StatusChip({ status }: { status: TaskStatus | RunStatus }) {
  return <span className={`status status-${status}`}>{statusLabel(status)}</span>;
}
