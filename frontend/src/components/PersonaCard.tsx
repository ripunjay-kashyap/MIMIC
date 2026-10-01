import Link from "next/link";
import { finished } from "@/lib/events";
import type { PersonaState, RunEvent } from "@/lib/types";
import { Bar } from "./Bar";
import { StatusChip } from "./StatusChip";
export function pathOnly(url: string | null | undefined) {
  if (!url) return "Waiting for first action";
  try { return new URL(url, "http://local").pathname; } catch { return url; }
}
export function PersonaCard({ persona, runId, live = false, events = [] }: { persona: PersonaState; runId: string; live?: boolean; events?: RunEvent[] }) {
  const latest = events.findLast(event => Boolean(event.url));
  const decision = events.findLast(event => event.type === "decision");
  const traits = [["Digital literacy", persona.digital_literacy], ["Patience", persona.patience], ["Risk tolerance", persona.risk_tolerance], ["Reading tolerance", persona.reading_tolerance], ["Exploration", persona.exploration]] as const;
  return <article className="panel persona-card" data-testid={`persona-${persona.persona_id}`}>
    <div className="card-top"><span className="eyebrow">{persona.device} · {persona.language}</span><StatusChip status={persona.task_status} /></div>
    <h2>{persona.label}</h2><p className="muted blurb">{persona.blurb}</p>
    {live ? <>
      <p className="url-path" title={latest?.url || persona.visited_paths.at(-1)}>{pathOnly(latest?.url || persona.visited_paths.at(-1))}</p>
      <div className="decision"><strong>{decision?.type === "decision" ? `${decision.payload.action.action} · ${decision.payload.element_label || "Page"}` : "Waiting for a decision"}</strong>
        <p className="thought" title={decision?.type === "decision" ? decision.payload.action.thought : undefined}>{decision?.type === "decision" ? decision.payload.action.thought : "Decisions will appear as this persona explores."}</p></div>
      <p className="action-count"><strong>{persona.action_count} / {persona.max_actions}</strong> actions</p>
      <Bar label="Frustration" value={persona.current_frustration} threshold={persona.abandon_frustration} risk />
      <Bar label={persona.progress_estimated ? "Progress (estimated)" : "Progress"} value={persona.progress} />
      <div className="card-bottom"><span className="muted">Abandons at ≥ {persona.abandon_frustration}</span>{finished(persona) ? <Link href={`/runs/${runId}/personas/${persona.persona_id}`}>Replay →</Link> : <span className="muted" aria-disabled="true">Replay pending</span>}</div>
    </> : <>
      <div className="traits">{traits.map(([label, value]) => <Bar key={label} label={label} value={value} />)}</div>
      <dl className="limits"><div><dt>Max actions</dt><dd>{persona.max_actions}</dd></div><div><dt>Abandons at frustration</dt><dd>≥ {persona.abandon_frustration}</dd></div><div><dt>Max failed attempts</dt><dd>{persona.max_failed_attempts}</dd></div></dl>
    </>}
    <p className="model">Model: {persona.llm_model || "Assigned at deployment"}</p>
  </article>;
}
