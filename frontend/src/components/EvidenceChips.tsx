const policyLabels: Record<string, string> = {
  edge_case_input: "odd input",
  double_click: "double-click",
  forced_back: "went back mid-flow",
  deterministic: "rule-based (no LLM)",
  fallback_model: "fallback model",
};

const signalTones: Record<string, string> = {
  stuck: "warn",
  backtrack: "neutral",
  no_page_change: "neutral",
  error_message: "bad",
  risk_page: "violet",
  progress: "good",
  delayed_change: "neutral",
  action_failed: "bad",
};

export function shortModel(model: string) {
  return model.includes("flash-lite") ? "flash-lite" : model === "mock-scripted" ? "fake" : model.split("/").at(-1) || model;
}

export function ModelBadge({ model }: { model: string | null }) {
  if (!model) return <span className="model-badge muted">Model pending</span>;
  const shortName = shortModel(model);
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
        <span className="evidence-chip tone-neutral" key={tag} title={tag}>
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
        <span className={`evidence-chip tone-${signalTones[signal] || "neutral"}`} key={signal} title={signal}>
          {signal.replaceAll("_", " ")}
        </span>
      ))}
    </div>
  );
}
