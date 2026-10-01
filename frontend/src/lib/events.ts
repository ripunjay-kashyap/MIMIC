"use client";
import { useEffect, useMemo, useState } from "react";
import { API_URL, MOCK } from "./config";
import { errorMessage } from "./errors";
import { subscribeMock } from "./mock";
import type { PersonaState, RunEvent, RunStatus, RunSummary } from "./types";
export const finished = (persona: PersonaState) => !["pending", "active"].includes(persona.task_status);
const rank: Record<RunStatus, number> = { created: 0, cohort_ready: 1, running: 2, aggregating: 3, completed: 4, failed: 4 };

export function useRunEvents(runId: string, initial: RunSummary) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    let source: EventSource | undefined;
    const seen = new Set<number>();
    const onEvent = (event: RunEvent) => {
      if (!active || event.run_id !== runId || !Number.isFinite(event.seq) || seen.has(event.seq)) return;
      seen.add(event.seq);
      setEvents(previous => previous.some(e => e.seq === event.seq) ? previous : [...previous, event].sort((a,b) => a.seq-b.seq));
      if (event.type === "run_status" && ["completed", "failed"].includes(event.payload.status)) {
        source?.close(); setConnected(false);
      }
    };
    const onOpen = () => { if (active) { setConnected(true); setError(null); } };
    const onError = (reason: unknown) => { if (active) { setConnected(false); setError(errorMessage(reason)); } };
    let closeMock: (() => void) | undefined;
    if (MOCK) closeMock = subscribeMock(runId, onEvent, onOpen, onError);
    else {
      source = new EventSource(`${API_URL}/runs/${encodeURIComponent(runId)}/events`);
      source.onopen = onOpen;
      source.onmessage = message => {
        try { onEvent(JSON.parse(message.data) as RunEvent); }
        catch { onError(new Error("An event could not be read. Reconnect to retry the stream.")); }
      };
      source.onerror = () => onError(new Error("Event stream interrupted. Reconnecting automatically…"));
    }
    return () => { active = false; source?.close(); closeMock?.(); };
  }, [runId, attempt]);
  const { personas, status } = useMemo(() => {
    const personas: Record<string, PersonaState> = Object.fromEntries(initial.personas.map(p => [p.persona_id, p]));
    let status = initial.status;
    for (const event of events) {
      if (event.type === "run_status" && rank[event.payload.status] >= rank[status]) status = event.payload.status;
      const state = event.type === "persona_started" ? event.payload.persona : event.type === "state_update" || event.type === "persona_finished" ? event.payload.state : null;
      const prior = state ? personas[state.persona_id] : null;
      // Replayed history must not overwrite the newer GET /runs snapshot on reload.
      if (state && (!prior || (state.action_count >= prior.action_count && (!finished(prior) || finished(state))))) personas[state.persona_id] = state;
    }
    return { personas, status };
  }, [initial, events]);
  return { events, personas, status, connected, error, reconnect: () => setAttempt(n => n + 1) };
}
