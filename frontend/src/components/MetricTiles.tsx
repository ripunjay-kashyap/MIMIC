import type { Metrics } from "@/lib/types";
export function MetricTiles({ metrics: m }: { metrics: Metrics }) {
  const tiles = [["Completion rate", `${Math.round(m.completion_rate*100)}%`], ["Abandonment rate", `${Math.round(m.abandonment_rate*100)}%`], ["Successful", m.success_count], ["Failed", m.failure_count], ["Abandoned", m.abandoned_count], ["Budget exhausted", m.budget_exhausted_count], ["Average actions", m.average_actions.toFixed(1)], ["Median actions", m.median_actions], ["Unique paths", m.unique_paths], ["Repeated friction points", m.repeated_friction_points], ["Blocked", m.blocked_count], ["Errors", m.error_count]];
  return <div className="metrics">{tiles.map(([label, value]) => <div className="panel metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}
