"use client";
import { useCallback } from "react";
import Link from "next/link";
import { getJourney } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import { Bar } from "./Bar";
import { capitalize } from "./JourneyMap";
import { PersonaSprite, personaNames, personaStyle } from "./PersonaSprite";
import { StatusChip } from "./StatusChip";
import { ErrorState, Loading } from "./ResourceState";
import { Timeline } from "./Timeline";

export function ReplayView({ id, personaId, target }: { id: string; personaId: string; target?: string }) {
  const load = useCallback(() => getJourney(id, personaId), [id, personaId]);
  const { data, error, loading, retry } = useResource(load);
  if (loading) return <Loading label="Loading journey and evidence…" />;
  if (error || !data) return <ErrorState error={error} retry={retry} />;
  const persona = data.persona;
  return <div className="replay" style={personaStyle(persona.persona_type)}>
    <Link className="back-link" href={`/runs/${id}`}>← Back to run</Link>
    <header className="replay-header">
      <PersonaSprite type={persona.persona_type} size={104} />
      <div>
        <p className="kicker">Replay · {personaNames[persona.persona_type]}</p>
        <h1>{persona.label}</h1>
        <p className="lead">{persona.blurb}</p>
      </div>
    </header>
    <section className={`outcome outcome-${persona.task_status}`} aria-labelledby="outcome-title">
      <div className="outcome-head">
        <h2 id="outcome-title">Journey outcome</h2>
        <StatusChip status={persona.task_status} />
      </div>
      <p className="outcome-reason">{persona.termination_reason ? capitalize(persona.termination_reason) : "This persona has not finished yet. Reload to see the latest recorded steps."}</p>
      <div className="outcome-metrics">
        <p className="outcome-actions"><strong>{persona.action_count} / {persona.max_actions}</strong> actions used</p>
        <Bar label="Final frustration" value={persona.current_frustration} risk threshold={persona.abandon_frustration} />
        <Bar label={persona.progress_estimated ? "Final progress (estimated)" : "Final progress"} value={persona.progress} />
      </div>
    </section>
    <Timeline key={`${personaId}-${target || "start"}`} events={data.events} target={target} />
  </div>;
}
