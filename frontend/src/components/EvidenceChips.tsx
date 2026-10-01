const policyLabels: Record<string, string> = {
  edge_case_input: "odd input",
  double_click: "double-click",
  forced_back: "went back mid-flow",
  deterministic: "rule-based (no LLM)",
  fallback_model: "fallback model",
};

const signalColors: Record<string, string> = {
  stuck: "sand",
  backtrack: "slate",
  no_page_change: "stone",
  error_message: "rose",
  risk_page: "lavender",
  progress: "green",
  delayed_change: "teal",
  action_failed: "clay",
};

export function ModelBadge({ model }: { model: string | null }) {
  if (!model) return <span className="muted small">Model pending</span>;

  const shortName = model.includes("flash-lite")
    ? "flash-lite"
    : model === "mock-scripted"
      ? "fake"
      : model.split("/").at(-1);

  return (
    <span className="model-badge" title={model} aria-label={`Model: ${shortName}`}>
      {shortName}
    </span>
  );
}

export function PolicyChips({ tags }: { tags: string[] }) {
  if (!tags.length) return null;

  return (
    <div className="evidence-chips policy-chips" aria-label="Persona policies">
      {[...new Set(tags)].map(tag => (
        <span className="evidence-chip chip-slate" key={tag} title={tag}>
          {policyLabels[tag] || tag.replaceAll("_", " ")}
        </span>
      ))}
    </div>
  );
}

export function SignalChips({ signals }: { signals: string[] }) {
  if (!signals.length) return null;

  return (
    <div className="evidence-chips signal-chips" aria-label="Step signals">
      {[...new Set(signals)].map(signal => (
        <span
          className={`evidence-chip chip-${signalColors[signal] || "slate"}`}
          key={signal}
          title={signal}
        >
          {signal.replaceAll("_", " ")}
        </span>
      ))}
    </div>
  );
}
