"""Per-persona agent loop as a LangGraph graph: observe -> decide -> act -> update -> (loop | finalize).

Bounded three ways: state engine budgets, an iteration cap, and LangGraph's recursion_limit.
Events follow docs/API_CONTRACT.md ordering: observation, decision, action_result, state_update, [screenshot].
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.prompts import build_messages, history_line
from app.browser.actions import execute
from app.browser.guards import detect_verification
from app.browser.observe import Observation, normalize_path
from app.browser.session import PersonaSession
from app.config import get_settings
from app.llm import router
from app.models.schemas import TERMINAL_STATUSES, ActionResult, PersonaState, SuccessCriteria
from app.personas.policies import PolicyDecision, PolicyMemory, apply_policy, labels_only, rng_for
from app.personas.state_engine import StepInput, apply, mark_blocked, mark_error
from app.personas.templates import HARD_MAX_ACTIONS, TEMPLATES_BY_TYPE

log = logging.getLogger(__name__)


class EventSink(Protocol):
    async def emit(self, type: str, persona_id: str | None, step: int | None, url: str | None,
                   payload: dict[str, Any]) -> int: ...

    async def screenshot(self, persona_id: str, step: int, reason: str, data: bytes) -> str | None: ...


Escalator = Callable[[PersonaSession, Observation, PersonaState, list[str]], Awaitable[str | None]]


@dataclass
class PersonaRunContext:
    run_id: str
    persona: PersonaState
    session: PersonaSession
    sink: EventSink
    success_criteria: SuccessCriteria | None
    milestones: list[str] | None = None
    escalate: Escalator | None = None
    mem: PolicyMemory = field(init=False)

    def __post_init__(self) -> None:
        self.mem = PolicyMemory(rng=rng_for(self.run_id, self.persona.persona_id))


class LoopState(TypedDict, total=False):
    persona: PersonaState
    step: int
    obs: Observation
    prev_hash: str | None
    prev_result: ActionResult | None
    delayed: bool
    blocked: str | None
    history: list[str]
    decision: PolicyDecision
    element_label: str | None
    result: ActionResult


def _screenshot_reasons(step: int, result: ActionResult | None, action: str | None, terminal: bool) -> list[str]:
    mode = get_settings().screenshot_mode
    if mode == "none":
        return []
    if mode == "all":
        return ["step"]
    reasons = []
    if step == 1:
        reasons.append("start")
    if result is not None:
        if result.navigated:
            reasons.append("navigation")
        if not result.ok:
            reasons.append("failed_action")
    if action == "back":
        reasons.append("backtrack")
    if terminal:
        reasons.append("final")
    return reasons[:1] if not terminal else (["final"])


def build_graph(ctx: PersonaRunContext):
    sink, session = ctx.sink, ctx.session
    pid = ctx.persona.persona_id
    identity = TEMPLATES_BY_TYPE[ctx.persona.persona_type].test_identity

    async def shoot(step: int, reason: str) -> None:
        try:
            path = await sink.screenshot(pid, step, reason, await session.screenshot())
            if path:
                await sink.emit("screenshot", pid, step, session.page.url, {"reason": reason, "path": path, "url": None})
        except Exception as e:  # noqa: BLE001 - evidence capture must never kill a persona
            log.warning("screenshot failed for %s: %s", pid, e)

    async def observe_node(st: LoopState) -> LoopState:
        step = st.get("step", 0) + 1
        obs = await session.observe()
        prev_hash, prev_result = st.get("prev_hash"), st.get("prev_result")
        delayed = bool(prev_result is not None and prev_hash and obs.page_hash != prev_hash)
        blocked = await detect_verification(session.page)
        await sink.emit("observation", pid, step, obs.url, {
            "title": obs.title, "element_count": len(obs.elements), "summary": obs.summary(), "path": obs.path,
            "page_hash": obs.page_hash, "alerts": obs.alerts,
            "prompt": obs.to_prompt(labels_only=labels_only(st["persona"])),
        })
        if step == 1:
            await shoot(step, "start")
        return {"step": step, "obs": obs, "delayed": delayed, "blocked": blocked}

    async def blocked_node(st: LoopState) -> LoopState:
        persona = mark_blocked(st["persona"], st["blocked"] or "verification")
        await sink.emit("state_update", pid, st["step"], st["obs"].url,
                        {"state": persona.model_dump(), "deltas": {}, "signals": []})
        return {"persona": persona}

    async def decide_node(st: LoopState) -> LoopState:
        persona, obs = st["persona"], st["obs"]
        history = st.get("history", [])
        escalation = await ctx.escalate(session, obs, persona, history) if ctx.escalate else None
        messages = build_messages(persona, obs.to_prompt(labels_only=labels_only(persona)), history, escalation=escalation)
        d = await router.decide(persona, messages, identity=identity, step=st["step"])
        el = obs.element(d.action.element_id)
        pol = apply_policy(persona, d.action, path=obs.path, page_text=obs.text, element_label=el.label if el else None,
                           element_kind=el.kind if el else None, mem=ctx.mem)
        final_el = obs.element(pol.action.element_id)
        tags = list(pol.tags)
        if d.fallback and "fallback_model" not in tags:
            tags.append("fallback_model")
        await sink.emit("decision", pid, st["step"], obs.url, {
            "action": pol.action.model_dump(), "model": d.model, "element_label": final_el.label if final_el else None,
            "policy_tags": tags, "llm_action": d.action.model_dump() if pol.action != d.action else None,
            "tokens": {"prompt": d.prompt_tokens, "completion": d.completion_tokens},
        })
        return {"decision": pol, "element_label": final_el.label if final_el else None}

    async def act_node(st: LoopState) -> LoopState:
        pol = st["decision"]
        result = await execute(session, pol.action, double_click=pol.double_click)
        await sink.emit("action_result", pid, st["step"], result.url_after, {"result": result.model_dump()})
        return {"result": result}

    async def update_node(st: LoopState) -> LoopState:
        persona, obs_before, result, pol = st["persona"], st["obs"], st["result"], st["decision"]
        obs_after = await session.observe()
        out = apply(persona, StepInput(
            action=pol.action, result=result, path_before=obs_before.path, path_after=normalize_path(result.url_after),
            page_hash_after=obs_after.page_hash, alerts_before=obs_before.alerts, alerts_after=obs_after.alerts,
            text_after=obs_after.text, delayed_change=st.get("delayed", False),
        ), success_criteria=ctx.success_criteria, milestones=ctx.milestones)
        await sink.emit("state_update", pid, st["step"], result.url_after,
                        {"state": out.state.model_dump(), "deltas": out.deltas, "signals": out.signals})
        terminal = out.state.task_status in TERMINAL_STATUSES
        for reason in _screenshot_reasons(st["step"], result, pol.action.action, terminal=False):
            if reason != "start":
                await shoot(st["step"], reason)
        history = st.get("history", []) + [history_line(
            pol.action.action, st.get("element_label"), pol.action.text, result.ok, result.error,
            normalize_path(result.url_after) if result.navigated else None, changed=result.page_changed)]
        return {"persona": out.state, "history": history, "prev_hash": obs_after.page_hash, "prev_result": result}

    async def finalize_node(st: LoopState) -> LoopState:
        persona = st["persona"]
        if persona.task_status not in TERMINAL_STATUSES:  # iteration cap hit
            persona = persona.model_copy(update={"task_status": "budget_exhausted",
                                                 "termination_reason": "iteration cap reached"})
        await shoot(st.get("step", 0), "final")
        await sink.emit("persona_finished", pid, st.get("step"), session.page.url, {
            "status": persona.task_status, "reason": persona.termination_reason or "", "state": persona.model_dump()})
        return {"persona": persona}

    max_iterations = HARD_MAX_ACTIONS * 2 + 5

    def after_observe(st: LoopState) -> str:
        return "blocked" if st.get("blocked") else "decide"

    def after_update(st: LoopState) -> str:
        if st["persona"].task_status in TERMINAL_STATUSES or st["step"] >= max_iterations:
            return "finalize"
        return "observe"

    g = StateGraph(LoopState)
    g.add_node("observe", observe_node)
    g.add_node("blocked", blocked_node)
    g.add_node("decide", decide_node)
    g.add_node("act", act_node)
    g.add_node("update", update_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "observe")
    g.add_conditional_edges("observe", after_observe, {"blocked": "blocked", "decide": "decide"})
    g.add_edge("blocked", "finalize")
    g.add_edge("decide", "act")
    g.add_edge("act", "update")
    g.add_conditional_edges("update", after_update, {"finalize": "finalize", "observe": "observe"})
    g.add_edge("finalize", END)
    return g.compile(), max_iterations


async def run_persona(ctx: PersonaRunContext) -> PersonaState:
    """Run one persona to a terminal state. Never raises: infra errors become task_status='error'."""
    pid = ctx.persona.persona_id
    persona = ctx.persona.model_copy(update={"task_status": "active"})
    await ctx.sink.emit("persona_started", pid, None, ctx.session.target_url, {"persona": persona.model_dump()})
    try:
        await ctx.session.goto_start()
        graph, max_iterations = build_graph(ctx)
        final = await graph.ainvoke({"persona": persona, "step": 0, "history": []},
                                    config={"recursion_limit": max_iterations * 6 + 10,
                                            "run_name": f"persona:{pid}", "tags": [ctx.run_id, pid]})
        return final["persona"]
    except Exception as e:  # noqa: BLE001
        log.exception("persona %s crashed", pid)
        errored = mark_error(persona, f"{type(e).__name__}: {e}")
        try:
            await ctx.sink.emit("error", pid, None, None, {"message": f"{type(e).__name__}: {str(e)[:300]}"})
            await ctx.sink.emit("persona_finished", pid, None, None,
                                {"status": "error", "reason": errored.termination_reason, "state": errored.model_dump()})
        except Exception:  # noqa: BLE001
            pass
        return errored
