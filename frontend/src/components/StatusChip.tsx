import type { RunStatus, TaskStatus } from "@/lib/types";
const labels: Partial<Record<TaskStatus | RunStatus, string>> = { cohort_ready: "Cohort ready", budget_exhausted: "Budget exhausted", blocked_by_verification: "Blocked" };
export function StatusChip({ status }: { status: TaskStatus | RunStatus }) {
  return <span className={`status status-${status}`}>{labels[status] || status.replaceAll("_", " ")}</span>;
}
