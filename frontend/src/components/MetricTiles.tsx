import type { Metrics } from "@/lib/types";

export function MetricTiles({ metrics: m }: { metrics: Metrics }) {
  const primary = [
    ["Completion rate", `${Math.round(m.completion_rate * 100)}%`],
    ["Abandonment rate", `${Math.round(m.abandonment_rate * 100)}%`],
    ["Average actions", m.average_actions.toFixed(1)],
    ["Unique paths", m.unique_paths],
    ["Repeated friction points", m.repeated_friction_points],
    ["Backtracks", m.backtracks_total],
  ] as const;
  const secondary = [
    ["Successful", m.success_count], ["Failed", m.failure_count], ["Abandoned", m.abandoned_count],
    ["Budget exhausted", m.budget_exhausted_count], ["Median actions", m.median_actions],
    ["Blocked", m.blocked_count], ["Errors", m.error_count],
  ] as const;
  return <div className="metrics-block">
    <dl className="metrics">
      {primary.map(([label, value]) => <div className="metric" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
    <dl className="metrics-secondary">
      {secondary.map(([label, value]) => <div className="metric" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  </div>;
}
