import Link from "next/link";
import type { PersonaState, RunEvent } from "@/lib/types";
import { PersonaSprite, personaNames } from "./PersonaSprite";

export function MissionCounters({ personas, events }: { personas: PersonaState[]; events: RunEvent[] }) {
  const values = [
    [personas.filter(p => p.task_status === "active").length, "Active agents"],
    [personas.reduce((total, p) => total + p.action_count, 0), "Actions taken"],
    [events.filter(e => e.type === "finding").length, "Findings recorded"],
    [events.length, "Events received"],
  ] as const;
  return <div className="mission-stats" aria-label="Run counters">
    {values.map(([value, label]) => <div className="mission-stat" key={label}><strong>{value}</strong><span>{label}</span></div>)}
  </div>;
}

export function MissionRail({ personas, runId }: { personas: PersonaState[]; runId: string }) {
  return <div className="mission-rail" aria-label="Persona status rail">
    {personas.map(persona => (
      <Link className="mission-agent" key={persona.persona_id} data-status={persona.task_status}
        href={`/runs/${runId}/personas/${persona.persona_id}`}
        aria-label={`${persona.label}, ${persona.task_status.replaceAll("_", " ")}, open replay`}>
        <PersonaSprite type={persona.persona_type} size={28} />
        <div><strong>{personaNames[persona.persona_type]}</strong><small>{persona.task_status.replaceAll("_", " ")}</small></div>
      </Link>
    ))}
  </div>;
}

export function LiveTicker({ events, personas }: { events: RunEvent[]; personas: PersonaState[] }) {
  const event = events.findLast(e => ["decision", "persona_finished", "finding", "run_status"].includes(e.type));
  const persona = personas.find(p => p.persona_id === event?.persona_id);
  let text = "Waiting for the first recorded event.";
  if (event?.type === "decision") text = `${persona?.label || event.persona_id} → ${event.payload.action.action}${event.payload.element_label ? ` · ${event.payload.element_label}` : ""}`;
  if (event?.type === "persona_finished") text = `${persona?.label || event.persona_id} → ${event.payload.status.replaceAll("_", " ")} · ${event.payload.reason}`;
  if (event?.type === "finding") text = `${event.payload.finding.severity} severity → ${event.payload.finding.observed}`;
  if (event?.type === "run_status") text = `Run ${event.payload.status.replaceAll("_", " ")}`;
  return <div className="live-ticker" aria-label="Latest recorded activity"><span className="ticker-label">{event ? `#${event.seq}` : "AWAITING"}</span><p>{text}</p></div>;
}
