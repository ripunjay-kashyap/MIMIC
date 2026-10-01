"""Data contracts shared by every layer (plan §2). Change with care: DB, SSE and frontend depend on these."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["created", "cohort_ready", "running", "aggregating", "completed", "failed"]

PersonaType = Literal["impatient", "low_literacy", "power", "cautious", "explorer", "chaos"]

TaskStatus = Literal[
    "pending", "active", "success", "failed", "abandoned",
    "budget_exhausted", "blocked_by_verification", "error",
]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"success", "failed", "abandoned", "budget_exhausted", "blocked_by_verification", "error"}
)

ActionType = Literal["click", "type", "select", "scroll", "back", "wait", "done", "give_up"]

EventType = Literal[
    "run_status", "persona_started", "observation", "decision", "action_result",
    "state_update", "escalation", "screenshot", "persona_finished", "finding", "error", "heartbeat",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SuccessCriteria(BaseModel):
    url_contains: str | None = None
    text_visible: str | None = None


class PersonaState(BaseModel):
    persona_id: str
    persona_type: PersonaType
    label: str
    blurb: str
    goal: str
    # static traits (0..1)
    digital_literacy: float
    patience: float
    risk_tolerance: float
    reading_tolerance: float
    exploration: float
    language: str = "English"
    device: Literal["desktop", "mobile"] = "desktop"
    llm_model: str | None = None
    # budgets
    max_actions: int
    max_failed_attempts: int
    abandon_frustration: float
    # dynamic: mutated ONLY by personas/state_engine.py
    action_count: int = 0
    failed_attempts: int = 0
    backtracks: int = 0
    current_frustration: float = 0.0
    progress: float = 0.0
    progress_estimated: bool = False
    visited_paths: list[str] = Field(default_factory=list)
    recent_hashes: list[str] = Field(default_factory=list)  # last few page_hashes, for "stuck" detection
    task_status: TaskStatus = "pending"
    termination_reason: str | None = None


class AgentAction(BaseModel):
    """What the decision LLM is allowed to return."""

    action: ActionType
    element_id: int | None = None
    text: str | None = None
    thought: str = Field(default="", max_length=400)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    expects: str = Field(default="", max_length=200)


class ActionResult(BaseModel):
    ok: bool
    error: str | None = None
    url_before: str
    url_after: str
    navigated: bool = False
    page_changed: bool = False
    dialogs: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class RunEvent(BaseModel):
    run_id: str
    seq: int
    persona_id: str | None = None
    ts: datetime = Field(default_factory=utcnow)
    type: EventType
    step: int | None = None
    url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceRef(BaseModel):
    persona_id: str
    seq: int
    screenshot_path: str | None = None


class Finding(BaseModel):
    id: str | None = None
    run_id: str
    category: str
    severity: Literal["low", "medium", "high"]
    page: str | None = None
    personas: list[str]
    evidence: list[EvidenceRef]
    observed: str
    interpretation: str | None = None
    suggested_investigation: str | None = None
    source: Literal["deterministic", "llm_synthesized", "template"] = "deterministic"


# ---------------------------------------------------------------- API bodies

class CreateRunRequest(BaseModel):
    target_url: str
    goal: str = Field(min_length=3, max_length=500)
    success_criteria: SuccessCriteria | None = None
    authorized: bool


class RunSummary(BaseModel):
    run_id: str
    target_url: str
    goal: str
    status: RunStatus
    created_at: datetime
    personas: list[PersonaState]
    metrics: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    browser_ready: bool
    db_ready: bool
    llm_mode: str
