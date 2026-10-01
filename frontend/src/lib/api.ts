import { API_URL, MOCK } from "./config";
import { ApiError } from "./errors";
import type { CreateRun, Health, Journey, Report, RunSummary } from "./types";
import * as mock from "./mock";
export { API_URL, MOCK } from "./config";
export { ApiError } from "./errors";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init, headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store", signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try { const body = await response.json(); if (typeof body.detail === "string") detail = body.detail; } catch { /* Keep HTTP fallback for non-JSON errors. */ }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}
const runPath = (id: string) => `/runs/${encodeURIComponent(id)}`;
export const getHealth = (): Promise<Health> => MOCK ? mock.mockHealth() : request("/health");
export const createRun = (input: CreateRun): Promise<RunSummary> => MOCK ? mock.mockCreateRun(input) : request("/runs", { method: "POST", body: JSON.stringify(input) });
export const getRun = (id: string): Promise<RunSummary> => MOCK ? mock.mockGetRun(id) : request(runPath(id));
export const startRun = (id: string): Promise<{ run_id: string; status: "running" }> => MOCK ? mock.mockStartRun(id) : request(`${runPath(id)}/start`, { method: "POST" });
export const getReport = (id: string): Promise<Report> => MOCK ? mock.mockGetReport(id) : request(`${runPath(id)}/report`);
export const getJourney = (id: string, personaId: string): Promise<Journey> => MOCK ? mock.mockGetJourney(id, personaId) : request(`${runPath(id)}/personas/${encodeURIComponent(personaId)}/journey`);
export const getGoldenRun = (): Promise<{ run_id: string }> => MOCK ? mock.mockGoldenRun() : request("/runs/golden");
