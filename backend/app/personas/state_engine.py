"""The ONLY code that mutates a persona's dynamic state. Pure: no browser, LLM or DB imports.

Signals emitted match `state_update.signals` in docs/API_CONTRACT.md.
"""

import re
from dataclasses import dataclass, field

from app.models.schemas import TERMINAL_STATUSES, ActionResult, AgentAction, PersonaState, SuccessCriteria
from app.personas.templates import HARD_MAX_ACTIONS

STUCK_WINDOW = 3
SLOW_ACTION_MS = 2500

RISK_WORDS = re.compile(
    r"(?<!co-)\b(pay|payment|payable|otp|kyc|aadhaar|pan card|card number|upi|charges|share my data|auto-renew|consent)\b",
    re.IGNORECASE,
)
TRUST_WORDS = re.compile(r"\b(secure|refund|privacy policy|no hidden|cancel anytime|money-back)\b", re.IGNORECASE)


@dataclass
class StepInput:
    action: AgentAction
    result: ActionResult
    path_before: str
    path_after: str
    page_hash_after: str
    alerts_before: list[str] = field(default_factory=list)
    alerts_after: list[str] = field(default_factory=list)
    text_after: str = ""
    delayed_change: bool = False  # page changed between steps without an action causing it
    verification_blocked: str | None = None
    llm_progress_estimate: float | None = None


@dataclass
class StepOutcome:
    state: PersonaState
    deltas: dict[str, float]
    signals: list[str]


def _bump(f: float, delta: float) -> float:
    return round(min(1.0, max(0.0, f + delta)), 3)


def success_met(criteria: SuccessCriteria | None, url: str, text: str) -> bool:
    if criteria is None or not (criteria.url_contains or criteria.text_visible):
        return False
    if criteria.url_contains and criteria.url_contains not in url:
        return False
    if criteria.text_visible and criteria.text_visible.lower() not in text.lower():
        return False
    return True


def _progress(state: PersonaState, path: str, milestones: list[str] | None, estimate: float | None) -> tuple[float, bool]:
    if milestones:
        if path in milestones:
            return max(state.progress, round(milestones.index(path) / (len(milestones) - 1), 3)), False
        return state.progress, False
    if estimate is not None:
        return max(state.progress, round(min(1.0, max(0.0, estimate)), 3)), True
    return state.progress, state.progress_estimated


def apply(
    state: PersonaState,
    step: StepInput,
    *,
    success_criteria: SuccessCriteria | None,
    milestones: list[str] | None = None,
) -> StepOutcome:
    if state.task_status in TERMINAL_STATUSES:
        return StepOutcome(state, {}, [])

    s = state.model_copy(deep=True)
    s.task_status = "active"
    before = state.model_dump(include={"current_frustration", "progress", "failed_attempts", "action_count", "backtracks"})
    signals: list[str] = []
    patience_k = 1.2 - s.patience
    f = s.current_frustration
    a, r = step.action, step.result

    if a.action not in ("done", "give_up"):
        s.action_count += 1

    if not s.visited_paths or s.visited_paths[-1] != step.path_after:
        s.visited_paths.append(step.path_after)
    s.recent_hashes = (s.recent_hashes + [step.page_hash_after])[-STUCK_WINDOW:]

    # ---- frustration rules
    if not r.ok:
        s.failed_attempts += 1
        f = _bump(f, 0.20 * patience_k)
        signals.append("action_failed")
    elif a.action == "click" and not r.page_changed and not r.navigated:
        f = _bump(f, 0.10 * patience_k)
        signals.append("no_page_change")

    if len(s.recent_hashes) == STUCK_WINDOW and len(set(s.recent_hashes)) == 1 and a.action != "done":
        f = _bump(f, 0.15)
        signals.append("stuck")

    if a.action == "back" and r.ok:
        s.backtracks += 1
        if s.exploration < 0.8:  # exploring is expected behaviour for the explorer
            f = _bump(f, 0.05)
        signals.append("backtrack")

    if a.action == "wait" and not r.page_changed:
        f = _bump(f, 0.10 * (1 - s.patience))

    if r.ok and r.duration_ms > SLOW_ACTION_MS and a.action != "wait":
        f = _bump(f, 0.05 * patience_k)

    new_alerts = [x for x in step.alerts_after if x not in step.alerts_before]
    if new_alerts:
        f = _bump(f, 0.10 * (1.2 - s.digital_literacy))
        signals.append("error_message")

    arrived = step.path_after != step.path_before or s.action_count == 1
    succeeded = success_met(success_criteria, step.result.url_after, step.text_after)
    if arrived and not succeeded and RISK_WORDS.search(step.text_after) and not TRUST_WORDS.search(step.text_after):
        f = _bump(f, 0.15 * (1 - s.risk_tolerance))
        signals.append("risk_page")

    if step.delayed_change:
        signals.append("delayed_change")

    progress, estimated = _progress(s, step.path_after, milestones, step.llm_progress_estimate)
    if progress > s.progress:
        if "risk_page" not in signals:  # arriving somewhere risky isn't a relief
            f = _bump(f, -0.10)
        signals.append("progress")
    s.progress, s.progress_estimated = progress, estimated

    if a.action == "done" and not success_met(success_criteria, r.url_after, step.text_after) and success_criteria:
        s.failed_attempts += 1  # claimed success that isn't real
        f = _bump(f, 0.10)
        signals.append("action_failed")

    if a.action == "give_up" and f < 0.5 * s.abandon_frustration:
        f = _bump(f, 0.15)  # not allowed to quit while calm; it still counts as unease

    s.current_frustration = f

    # ---- termination (order matters)
    if success_met(success_criteria, r.url_after, step.text_after):
        s.task_status, s.termination_reason = "success", "success criteria met"
        s.progress = 1.0
    elif step.verification_blocked:
        s.task_status, s.termination_reason = "blocked_by_verification", step.verification_blocked
    elif a.action == "done" and not success_criteria:
        s.task_status, s.termination_reason = "success", "agent_claimed_success"
    elif a.action == "give_up" and f >= 0.5 * s.abandon_frustration:
        s.task_status, s.termination_reason = "abandoned", f"chose to give up at frustration {f:.2f}"
    elif f >= s.abandon_frustration:
        s.task_status, s.termination_reason = "abandoned", f"frustration {f:.2f} ≥ threshold {s.abandon_frustration}"
    elif s.failed_attempts >= s.max_failed_attempts:
        s.task_status, s.termination_reason = "failed", f"{s.failed_attempts} failed attempts"
    elif s.action_count >= min(s.max_actions, HARD_MAX_ACTIONS):
        s.task_status, s.termination_reason = "budget_exhausted", f"used all {s.action_count} actions"

    after = s.model_dump(include=set(before))
    deltas = {k: round(after[k] - before[k], 3) for k in before if after[k] != before[k]}
    return StepOutcome(s, deltas, signals)


def mark_error(state: PersonaState, reason: str) -> PersonaState:
    s = state.model_copy(deep=True)
    s.task_status, s.termination_reason = "error", reason[:300]
    return s


def mark_blocked(state: PersonaState, reason: str) -> PersonaState:
    s = state.model_copy(deep=True)
    s.task_status, s.termination_reason = "blocked_by_verification", reason[:300]
    return s
