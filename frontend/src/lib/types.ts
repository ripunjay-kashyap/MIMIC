// Wire shapes from docs/API_CONTRACT.md; payloads are narrowed by event type.
export type RunStatus = "created" | "cohort_ready" | "running" | "aggregating" | "completed" | "failed";
export type TaskStatus = "pending" | "active" | "success" | "failed" | "abandoned" | "budget_exhausted" | "blocked_by_verification" | "error";
export interface PersonaState {
  persona_id: string;
  persona_type: "impatient" | "low_literacy" | "power" | "cautious" | "explorer" | "chaos";
  label: string; blurb: string; goal: string;
  digital_literacy: number; patience: number; risk_tolerance: number;
  reading_tolerance: number; exploration: number;
  language: string; device: "desktop" | "mobile"; llm_model: string | null;
  max_actions: number; max_failed_attempts: number; abandon_frustration: number;
  action_count: number; failed_attempts: number; backtracks: number;
  current_frustration: number; progress: number; progress_estimated: boolean;
  visited_paths: string[]; task_status: TaskStatus; termination_reason: string | null;
}
export interface RunSummary {
  run_id: string; target_url: string; goal: string; status: RunStatus;
  created_at: string; personas: PersonaState[]; metrics: Metrics | null; error: string | null;
}
export interface AgentAction {
  action: "click" | "type" | "select" | "scroll" | "back" | "wait" | "done" | "give_up";
  element_id: number | null; text: string | null; thought: string; confidence: number; expects: string;
}
export interface ActionResult {
  ok: boolean; error: string | null; url_before: string; url_after: string;
  navigated: boolean; page_changed: boolean; dialogs: string[]; duration_ms: number;
}
export interface Metrics {
  completion_rate: number; abandonment_rate: number; success_count: number; failure_count: number;
  abandoned_count: number; budget_exhausted_count: number; blocked_count: number; error_count: number;
  average_actions: number; median_actions: number; unique_paths: number; repeated_friction_points: number;
  backtracks_total: number; frustration_at_termination: Record<string, number>;
}
export interface EvidenceRef { persona_id: string; seq: number; screenshot_path: string | null; screenshot_url?: string | null; }
export interface Finding {
  id: string; run_id: string; category: string; severity: "low" | "medium" | "high";
  page: string | null; personas: string[]; evidence: EvidenceRef[];
  observed: string; interpretation: string | null; suggested_investigation: string | null;
  source: "deterministic" | "llm_synthesized" | "template";
}
export interface Report { run_id: string; status: RunStatus; metrics: Metrics; findings: Finding[]; }
export interface Journey { persona: PersonaState; events: RunEvent[]; }
export interface EventPayloads {
  run_status: { status: RunStatus };
  persona_started: { persona: PersonaState };
  observation: { title: string; element_count: number; summary: string };
  decision: { action: AgentAction; model: string; element_label: string | null };
  action_result: { result: ActionResult };
  state_update: { state: PersonaState; deltas: Record<string, number>; signals: string[] };
  escalation: { model: string; observation: string; screenshot_url: string | null };
  screenshot: { reason: string; path: string; url: string | null };
  persona_finished: { status: TaskStatus; reason: string; state: PersonaState };
  finding: { finding: Finding };
  error: { message: string };
  heartbeat: Record<string, never>;
}
export type EventType = keyof EventPayloads;
export type RunEvent = { [K in EventType]: {
  run_id: string; seq: number; persona_id: string | null; ts: string;
  type: K; step: number | null; url: string | null; payload: EventPayloads[K];
}}[EventType];
export interface Health { status: "ok"; version: string; browser_ready: boolean; db_ready: boolean; llm_mode: string; }
export interface CreateRun { target_url: string; goal: string; success_criteria?: { url_contains?: string; text_visible?: string }; authorized: true; }
