"use client";

import { useEffect, useState } from "react";
import { getRun } from "./api";
import { API_URL, MOCK } from "./config";
import { errorMessage } from "./errors";
import { subscribeMock } from "./mock";
import type { PersonaState, RunEvent, RunStatus, RunSummary } from "./types";

export const finished = (persona: PersonaState) =>
  !["pending", "active"].includes(persona.task_status);

const terminal = (status: RunStatus) => status === "completed" || status === "failed";
const rank: Record<RunStatus, number> = {
  created: 0, cohort_ready: 1, running: 2, aggregating: 3, completed: 4, failed: 4,
};

function newerPersona(prior: PersonaState, incoming: PersonaState) {
  if (incoming.action_count < prior.action_count) return prior;
  if (finished(prior) && !finished(incoming)) return prior;
  return incoming;
}

function mergeSnapshot(current: RunSummary, incoming: RunSummary): RunSummary {
  return {
    ...incoming,
    status: rank[incoming.status] >= rank[current.status] ? incoming.status : current.status,
    personas: current.personas.map(prior => {
      const next = incoming.personas.find(p => p.persona_id === prior.persona_id);
      return next ? newerPersona(prior, next) : prior;
    }),
  };
}

export function useRunEvents(runId: string, initial: RunSummary) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [snapshot, setSnapshot] = useState(initial);
  const [connected, setConnected] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let ended = false;
    let source: EventSource | undefined;
    let closeMock: (() => void) | undefined;
    let disconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let pollInFlight = false;
    let connectionVersion = 0;
    let highestSeq = 0;
    const seen = new Set<number>();
    const stateSeq = new Map<string, number>();

    function stopPolling() {
      connectionVersion++;
      clearTimeout(disconnectTimer);
      clearInterval(pollTimer);
      disconnectTimer = undefined;
      pollTimer = undefined;
      if (active) setPolling(false);
    }

    function finishStream() {
      ended = true;
      stopPolling();
      source?.close();
      closeMock?.();
      setConnected(false);
      setError(null);
      setPollError(null);
    }

    async function pollRun() {
      if (!active || ended || pollInFlight) return;
      pollInFlight = true;
      const version = connectionVersion;
      const watermark = highestSeq;
      try {
        const latest = await getRun(runId);
        // A response from before reconnect/unmount must not overwrite fresh SSE data.
        if (!active || ended || version !== connectionVersion) return;
        for (const persona of latest.personas) {
          stateSeq.set(persona.persona_id, Math.max(stateSeq.get(persona.persona_id) ?? 0, watermark));
        }
        setSnapshot(current => mergeSnapshot(current, latest));
        setPollError(null);
        if (terminal(latest.status)) finishStream();
      } catch (reason) {
        if (active && !ended && version === connectionVersion) {
          setPollError(`Run refresh failed: ${errorMessage(reason)}`);
        }
      } finally {
        pollInFlight = false;
      }
    }

    function schedulePolling() {
      if (MOCK || ended || terminal(initial.status) || disconnectTimer || pollTimer) return;
      disconnectTimer = setTimeout(() => {
        disconnectTimer = undefined;
        if (!active || ended) return;
        setPolling(true);
        void pollRun();
        pollTimer = setInterval(() => void pollRun(), 5000);
      }, 10000);
    }

    function onEvent(event: RunEvent) {
      if (!active || ended || event.run_id !== runId || !Number.isFinite(event.seq) || seen.has(event.seq)) return;
      seen.add(event.seq);
      highestSeq = Math.max(highestSeq, event.seq);
      setEvents(previous => {
        if (previous.some(e => e.seq === event.seq)) return previous;
        return [...previous, event].sort((a, b) => a.seq - b.seq);
      });
      if (event.type === "run_status") {
        setSnapshot(current => ({
          ...current,
          status: rank[event.payload.status] >= rank[current.status] ? event.payload.status : current.status,
        }));
        if (terminal(event.payload.status)) finishStream();
      }
      const state = event.type === "persona_started"
        ? event.payload.persona
        : event.type === "state_update" || event.type === "persona_finished"
          ? event.payload.state
          : null;
      if (state && event.seq > (stateSeq.get(state.persona_id) ?? 0)) {
        stateSeq.set(state.persona_id, event.seq);
        setSnapshot(current => ({
          ...current,
          personas: current.personas.map(prior =>
            prior.persona_id === state.persona_id ? newerPersona(prior, state) : prior),
        }));
      }
    }

    function onOpen() {
      if (!active || ended) return;
      stopPolling();
      setConnected(true);
      setError(null);
      setPollError(null);
    }

    function onError(reason: unknown) {
      if (!active || ended) return;
      setConnected(false);
      setError(errorMessage(reason));
      schedulePolling();
    }

    if (MOCK) {
      closeMock = subscribeMock(runId, onEvent, onOpen, onError);
    } else {
      source = new EventSource(`${API_URL}/runs/${encodeURIComponent(runId)}/events`);
      source.onopen = onOpen;
      source.onmessage = message => {
        try {
          onEvent(JSON.parse(message.data) as RunEvent);
        } catch {
          onError(new Error("An event could not be read. Reconnect to retry the stream."));
        }
      };
      source.onerror = () => onError(new Error("Event stream interrupted. Reconnecting automatically…"));
      schedulePolling();
    }

    return () => {
      active = false;
      stopPolling();
      source?.close();
      closeMock?.();
    };
  }, [runId, initial, attempt]);

  return {
    events,
    personas: Object.fromEntries(snapshot.personas.map(p => [p.persona_id, p])),
    status: snapshot.status,
    runError: snapshot.error,
    connected,
    polling,
    error,
    pollError,
    reconnect: () => setAttempt(n => n + 1),
  };
}
