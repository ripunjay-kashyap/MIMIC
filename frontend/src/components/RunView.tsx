"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import { getRun, startRun } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { finished, useRunEvents } from "@/lib/events";
import { useResource } from "@/lib/use-resource";
import type { RunSummary } from "@/lib/types";
import { PersonaCard } from "./PersonaCard";
import { StatusChip } from "./StatusChip";
import { ErrorState, Loading } from "./ResourceState";
function LoadedRun({ run }: { run: RunSummary }) {
  const stream = useRunEvents(run.run_id, run);
  const [starting, setStarting] = useState(false); const [started, setStarted] = useState(false); const [error, setError] = useState<string | null>(null);
  const status = started && ["created", "cohort_ready"].includes(stream.status) ? "running" : stream.status;
  const live = !["created", "cohort_ready"].includes(status);
  const personas = Object.values(stream.personas);
  async function deploy() {
    if (starting) return; setStarting(true); setError(null);
    try { await startRun(run.run_id); setStarted(true); }
    catch (error) { setError(errorMessage(error)); }
    finally { setStarting(false); }
  }
  return <><div className="page-heading"><p className="eyebrow">{live ? "03 / Observe the run" : "02 / Meet the synthetic users"}</p><h1>{live ? "Live journeys" : "Review cohort"}</h1><p className="lead">{run.goal}</p><p className="target-line">Target: <span>{run.target_url}</span></p></div>
    <div className="panel run-toolbar"><div className="toolbar-status"><StatusChip status={status} /><span>{personas.filter(finished).length} / {personas.length} personas finished</span>{live && <span className="connection">{["completed", "failed"].includes(status) ? "Stream ended" : stream.connected ? "● Connected" : "○ Connecting"}</span>}</div>
      {status === "completed" && <Link className="button" href={`/runs/${run.run_id}/report`}>View report →</Link>}
      {!live && <button className="button" onClick={deploy} disabled={starting || status !== "cohort_ready"}>{starting ? "Deploying…" : "Deploy Swarm"}</button>}
    </div>
    {error && <p className="error-panel" role="alert">{error}</p>}
    {run.error && <p className="error-panel" role="alert">{run.error}</p>}
    {status === "failed" && !run.error && <p className="error-panel" role="alert">This run failed. Open the recorded persona replays to inspect what happened.</p>}
    {stream.error && <div className="error-panel" role="alert"><p>{stream.error}</p><button className="button secondary" onClick={stream.reconnect}>Reconnect</button></div>}
    <div className="persona-grid">{personas.map(persona => <PersonaCard key={persona.persona_id} persona={persona} runId={run.run_id} live={live} events={stream.events.filter(e => e.persona_id === persona.persona_id)} />)}</div>
    {live && <details className="panel event-log"><summary>Raw event log · {stream.events.length} events received</summary><p className="muted">Last 200 events, newest first</p><ol>{stream.events.slice(-200).reverse().map(event => <li key={event.seq}><strong>#{event.seq} · {event.type} · {event.persona_id || "run"}</strong><pre>{JSON.stringify(event, null, 2)}</pre></li>)}</ol></details>}
  </>;
}
export function RunView({ id }: { id: string }) {
  const load = useCallback(() => getRun(id), [id]);
  const resource = useResource(load);
  if (resource.loading) return <Loading label="Loading run and saved persona states…" />;
  if (resource.error || !resource.data) return <ErrorState error={resource.error} retry={resource.retry} />;
  return <LoadedRun run={resource.data} />;
}
