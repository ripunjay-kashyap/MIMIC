"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getRun, startRun } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { finished, useRunEvents } from "@/lib/events";
import { useResource } from "@/lib/use-resource";
import type { RunSummary } from "@/lib/types";
import { PersonaCard } from "./PersonaCard";
import { StatusChip } from "./StatusChip";
import { ErrorState, Loading } from "./ResourceState";
import { JourneyMap } from "./JourneyMap";

function LoadedRun({ run }: { run: RunSummary }) {
  const stream = useRunEvents(run.run_id, run);
  const [starting, setStarting] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewChoice, setViewChoice] = useState<"cards" | "map" | null>(null);
  const status = started && ["created", "cohort_ready"].includes(stream.status) ? "running" : stream.status;
  const live = !["created", "cohort_ready"].includes(status);
  const personas = Object.values(stream.personas);
  const view = viewChoice ?? (live ? "map" : "cards");
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      try {
        const saved = localStorage.getItem("mimic_journey_view");
        if (saved === "cards" || saved === "map") setViewChoice(saved);
      } catch { /* Storage is optional, including in private browsing. */ }
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  function selectView(next: "cards" | "map") {
    setViewChoice(next);
    try { localStorage.setItem("mimic_journey_view", next); } catch { /* Keep the in-memory choice. */ }
  }
  const connection = ["completed", "failed"].includes(status)
    ? "Stream ended"
    : stream.connected
      ? "● Connected"
      : stream.polling ? "Refreshing every 5 seconds" : "○ Connecting";

  async function deploy() {
    if (starting) return;
    setStarting(true);
    setError(null);
    try {
      await startRun(run.run_id);
      setStarted(true);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setStarting(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">{live ? "03 / Observe the run" : "02 / Meet the synthetic users"}</p>
        <h1>{live ? "Live journeys" : "Review cohort"}</h1>
        <p className="lead">{run.goal}</p>
        <p className="target-line">Target: <span>{run.target_url}</span></p>
      </div>
      <div className="panel run-toolbar">
        <div className="toolbar-status">
          <StatusChip status={status} />
          <span>{personas.filter(finished).length} / {personas.length} personas finished</span>
          {live && <span className="connection">{connection}</span>}
          {status === "aggregating" && (
            <span className="analysis-status" role="status">
              <span className="spinner" aria-hidden="true" />
              Analyzing findings…
            </span>
          )}
        </div>
        {status === "completed" && (
          <Link className="button" href={`/runs/${run.run_id}/report`}>View report →</Link>
        )}
        {!live && (
          <button className="button" onClick={deploy} disabled={starting || status !== "cohort_ready"}>
            {starting ? "Deploying…" : "Deploy Swarm"}
          </button>
        )}
      </div>
      {error && <p className="error-panel" role="alert">{error}</p>}
      {stream.runError && <p className="error-panel" role="alert">{stream.runError}</p>}
      {status === "failed" && !stream.runError && (
        <p className="error-panel" role="alert">
          This run failed. Open the recorded persona replays to inspect what happened.
        </p>
      )}
      {stream.error && (
        <div className="error-panel" role="alert">
          <p>{stream.error}</p>
          <button className="button secondary" onClick={stream.reconnect}>Reconnect</button>
        </div>
      )}
      {stream.pollError && <p className="error-panel" role="alert">{stream.pollError}</p>}
      <div className="journey-tabs" role="tablist" aria-label="Run view">
        {(["cards", "map"] as const).map(tab => (
          <button key={tab} id={`tab-${tab}`} role="tab" aria-selected={view === tab}
            aria-controls="run-view-panel" tabIndex={view === tab ? 0 : -1}
            onClick={() => selectView(tab)} onKeyDown={event => {
              if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                const next = event.key === "Home" ? "cards" : event.key === "End" ? "map" : tab === "cards" ? "map" : "cards";
                selectView(next);
                document.getElementById(`tab-${next}`)?.focus();
              }
            }}>
            {tab === "cards" ? "Cards" : "Journey map"}
          </button>
        ))}
      </div>
      <div id="run-view-panel" role="tabpanel" aria-labelledby={`tab-${view}`}>
        {view === "map" ? (
          <JourneyMap
            events={stream.events}
            personas={personas}
            runId={run.run_id}
            status={status}
            findings={stream.events.flatMap(event => event.type === "finding" ? [event.payload.finding] : [])}
          />
        ) : (
          <div className="persona-grid">
            {personas.map(persona => (
              <PersonaCard
                key={persona.persona_id}
                persona={persona}
                runId={run.run_id}
                live={live}
                events={stream.events.filter(event => event.persona_id === persona.persona_id)}
              />
            ))}
          </div>
        )}
      </div>
      {live && (
        <details className="panel event-log">
          <summary>Raw event log · {stream.events.length} events received</summary>
          <p className="muted">Last 200 events, newest first</p>
          <ol>
            {stream.events.slice(-200).reverse().map(event => (
              <li key={event.seq}>
                <strong>#{event.seq} · {event.type} · {event.persona_id || "run"}</strong>
                <pre>{JSON.stringify(event, null, 2)}</pre>
              </li>
            ))}
          </ol>
        </details>
      )}
    </>
  );
}

export function RunView({ id }: { id: string }) {
  const load = useCallback(() => getRun(id), [id]);
  const resource = useResource(load);
  if (resource.loading) return <Loading label="Loading run and saved persona states…" />;
  if (resource.error || !resource.data) return <ErrorState error={resource.error} retry={resource.retry} />;
  return <LoadedRun key={id} run={resource.data} />;
}
