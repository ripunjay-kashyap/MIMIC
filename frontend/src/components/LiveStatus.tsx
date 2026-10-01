import type { PersonaState, RunEvent } from "@/lib/types";
import { personaNames } from "./PersonaSprite";
import { statusLabel } from "./StatusChip";

export function RunCounters({ personas, events }: { personas: PersonaState[]; events: RunEvent[] }) {
  const values = [
    [personas.filter(p => p.task_status === "active").length, "browsing"],
    [personas.reduce((total, p) => total + p.action_count, 0), "actions"],
    [events.filter(e => e.type === "finding").length, "findings"],
    [events.length, "events"],
  ] as const;
  return <p className="run-counters" aria-label="Run counters">
    {values.map(([value, label]) => <span key={label}><strong>{value}</strong> {label}</span>)}
  </p>;
}

export function LiveTicker({ events, personas }: { events: RunEvent[]; personas: PersonaState[] }) {
  const event = events.findLast(e => ["decision", "persona_finished", "finding", "run_status"].includes(e.type));
  const persona = personas.find(p => p.persona_id === event?.persona_id);
  const name = persona ? personaNames[persona.persona_type] : event?.persona_id;
  let text = "Waiting for the first recorded event.";
  if (event?.type === "decision") text = `${name}: ${event.payload.action.action}${event.payload.element_label ? ` · ${event.payload.element_label}` : ""}`;
  if (event?.type === "persona_finished") text = `${name}: ${statusLabel(event.payload.status).toLowerCase()} · ${event.payload.reason}`;
  if (event?.type === "finding") text = `New ${event.payload.finding.severity} severity finding: ${event.payload.finding.observed}`;
  if (event?.type === "run_status") text = `Run ${statusLabel(event.payload.status).toLowerCase()}`;
  return <div className="live-ticker" aria-label="Latest recorded activity">
    <span className="ticker-label">{event ? `Event ${event.seq}` : "Waiting"}</span><p>{text}</p>
  </div>;
}
