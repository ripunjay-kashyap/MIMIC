import Link from "next/link";
import { finished } from "@/lib/events";
import type { PersonaState, RunEvent } from "@/lib/types";
import { Bar } from "./Bar";
import { ModelBadge, SignalChips } from "./EvidenceChips";
import { PersonaSprite, personaStyle } from "./PersonaSprite";
import { StatusChip } from "./StatusChip";

export function pathOnly(url: string | null | undefined) {
  if (!url) return "Waiting for first action";
  try {
    return new URL(url, "https://relative.invalid").pathname;
  } catch {
    return url;
  }
}

interface Props {
  persona: PersonaState;
  runId: string;
  live?: boolean;
  events?: RunEvent[];
}

export function PersonaCard({ persona, runId, live = false, events = [] }: Props) {
  const decision = events.findLast(event => event.type === "decision");
  const update = events.findLast(event => event.type === "state_update");
  const latestStep = events.findLast(event => event.step !== null)?.step;
  // A new observation/decision starts a fresh step; don't retain older signals.
  // A polled state can be ahead of the last received event too.
  const signals = update && update.step === latestStep
    && update.payload.state.action_count >= persona.action_count
    ? update.payload.signals
    : [];
  const path = persona.visited_paths.at(-1) || events.findLast(event => event.url)?.url;
  const traits = [
    ["Digital literacy", persona.digital_literacy],
    ["Patience", persona.patience],
    ["Risk tolerance", persona.risk_tolerance],
    ["Reading tolerance", persona.reading_tolerance],
    ["Exploration", persona.exploration],
  ] as const;

  return (
    <article className="persona-card" data-testid={`persona-${persona.persona_id}`} style={personaStyle(persona.persona_type)}>
      <div className="persona-identity">
        <PersonaSprite type={persona.persona_type} size={56} />
        <div>
          <h2>{persona.label}</h2>
          <p className="persona-meta">{persona.device} · {persona.language}</p>
        </div>
        <StatusChip status={persona.task_status} />
      </div>
      <p className="blurb">{persona.blurb}</p>
      {live ? (
        <>
          <p className="url-path" title={path || undefined}>{pathOnly(path)}</p>
          <div className="decision">
            <strong>
              {decision ? `${decision.payload.action.action} · ${decision.payload.element_label || "Page"}` : "Waiting for a decision"}
            </strong>
            <p className="thought" title={decision?.payload.action.thought}>
              {decision?.payload.action.thought ? `“${decision.payload.action.thought}”` : "Decisions will appear as this persona explores."}
            </p>
          </div>
          <SignalChips signals={signals} />
          <p className="action-count"><strong>{persona.action_count} / {persona.max_actions}</strong> actions</p>
          <Bar label="Frustration" value={persona.current_frustration} threshold={persona.abandon_frustration} risk />
          <Bar label={persona.progress_estimated ? "Progress (estimated)" : "Progress"} value={persona.progress} />
          <div className="card-bottom">
            <span className="muted">Gives up at {Math.round(persona.abandon_frustration * 100)}% frustration</span>
            {finished(persona) ? (
              <Link href={`/runs/${runId}/personas/${persona.persona_id}`}>Replay →</Link>
            ) : (
              <span className="muted" aria-disabled="true">Replay pending</span>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="traits">
            {traits.map(([label, value]) => <Bar key={label} label={label} value={value} />)}
          </div>
          <p className="limits">
            Gives up after <strong>{persona.max_actions} actions</strong>, <strong>{persona.max_failed_attempts} failed attempts</strong>, or at <strong>{Math.round(persona.abandon_frustration * 100)}% frustration</strong>.
          </p>
        </>
      )}
      <p className="model">Decides with <ModelBadge model={persona.llm_model} /></p>
    </article>
  );
}
