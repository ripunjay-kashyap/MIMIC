import { ApiError } from "../errors";
import type { CreateRun, Journey, Report, RunEvent } from "../types";
import { fixtureEvents, fixtureFindings, initialRun, snapshot } from "./fixtures";

interface StoredRun { id: string; input: CreateRun; createdAt: string; startedAt: number | null; }
const PREFIX = "mimic_mock_run_";
function read(id: string): StoredRun {
  const text = localStorage.getItem(PREFIX + id);
  if (!text) throw new ApiError("Run not found. Create a new mock run from Setup.", 404);
  return JSON.parse(text) as StoredRun;
}
function write(run: StoredRun) { localStorage.setItem(PREFIX + run.id, JSON.stringify(run)); }
function history(stored: StoredRun) {
  const run = initialRun(stored.id, stored.input, stored.createdAt);
  const all = fixtureEvents(run);
  const count = stored.startedAt === null ? 0 : Math.min(all.length, Math.max(1, Math.floor((Date.now() - stored.startedAt) / 300) + 1));
  return { run, all, available: all.slice(0, count) };
}
export async function mockHealth() { return { status: "ok" as const, version: "mock", browser_ready: true, db_ready: true, llm_mode: "mock" }; }
export async function mockCreateRun(input: CreateRun) {
  if (!input.authorized) throw new ApiError("Authorization is required.", 422);
  const stored: StoredRun = { id: `mock-${crypto.randomUUID()}`, input, createdAt: new Date().toISOString(), startedAt: null };
  write(stored);
  return initialRun(stored.id, input, stored.createdAt);
}
export async function mockGetRun(id: string) {
  const { run, available } = history(read(id));
  return snapshot(run, available);
}
export async function mockStartRun(id: string) {
  const stored = read(id);
  if (stored.startedAt !== null) throw new ApiError("This run has already started.", 409);
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(PREFIX) || key === PREFIX + id) continue;
    const other = JSON.parse(localStorage.getItem(key)!) as StoredRun;
    const { run, available } = history(other);
    const status = snapshot(run, available).status;
    if (status === "running" || status === "aggregating") throw new ApiError("Another run is active. Wait for it to finish before deploying this swarm.", 409);
  }
  stored.startedAt = Date.now();
  write(stored);
  return { run_id: id, status: "running" as const };
}
export async function mockGetReport(id: string): Promise<Report> {
  const { run, all, available } = history(read(id));
  const current = snapshot(run, available);
  if (current.status !== "completed") throw new ApiError("Run still in progress", 409);
  return { run_id: id, status: current.status, metrics: current.metrics!, findings: fixtureFindings(id, all) };
}
export async function mockGetJourney(id: string, personaId: string): Promise<Journey> {
  const { run, available } = history(read(id));
  const persona = snapshot(run, available).personas.find(p => p.persona_id === personaId);
  if (!persona) throw new ApiError("Persona not found.", 404);
  return { persona, events: available.filter(e => e.persona_id === personaId) };
}
export function subscribeMock(id: string, onEvent: (event: RunEvent) => void, onOpen: () => void, onError: (error: unknown) => void) {
  let cursor = 0;
  let closed = false;
  const close = () => { closed = true; clearInterval(timer); };
  const tick = () => {
    if (closed) return;
    try {
      const { available } = history(read(id));
      for (const event of available) if (event.seq > cursor) { cursor = event.seq; onEvent(event); }
      if (available.at(-1)?.type === "run_status" && (available.at(-1) as Extract<RunEvent, {type:"run_status"}>).payload.status === "completed") close();
    } catch (error) { onError(error); close(); }
  };
  const timer = setInterval(tick, 300);
  queueMicrotask(() => { if (!closed) { onOpen(); tick(); } });
  return close;
}
