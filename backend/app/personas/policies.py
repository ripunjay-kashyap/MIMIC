"""Code-enforced behaviour differences between personas, applied around the LLM's decision.

Tags returned match `decision.policy_tags` in docs/API_CONTRACT.md.
"""

import hashlib
import random
import re
from dataclasses import dataclass, field

from app.models.schemas import AgentAction, PersonaState

EDGE_CASE_INPUTS = ["12345", "", "😀😀😀", "९८७६५४३२१०", "  9876543210  ", "0000000000", "x" * 120, "-1"]
SUBMIT_WORDS = re.compile(r"\b(proceed|pay|submit|confirm|continue|verify|buy|place order)\b", re.IGNORECASE)
RISK_PAGE = re.compile(r"\b(pay|payment|payable|charges|consent|share my data|auto-renew)\b", re.IGNORECASE)

ALL_ACTIONS = ["click", "type", "select", "scroll", "back", "wait", "done", "give_up"]


def rng_for(run_id: str, persona_id: str) -> random.Random:
    seed = int(hashlib.sha256(f"{run_id}:{persona_id}".encode()).hexdigest()[:16], 16)
    return random.Random(seed)


@dataclass
class PolicyMemory:
    """Per-persona, per-run policy scratch state (not part of PersonaState)."""
    rng: random.Random
    scrolled_paths: set[str] = field(default_factory=set)
    steps_since_forced_back: int = 0


def allowed_actions(state: PersonaState) -> list[str]:
    acts = list(ALL_ACTIONS)
    if state.persona_type == "impatient":
        acts.remove("wait")  # never waits voluntarily
    if state.persona_type == "power":
        acts.remove("scroll")  # doesn't browse; goes straight for controls
    return acts


def labels_only(state: PersonaState) -> bool:
    """Low-literacy users don't see controls that lack a visible text label."""
    return state.persona_type == "low_literacy"


@dataclass
class PolicyDecision:
    action: AgentAction
    double_click: bool = False
    tags: list[str] = field(default_factory=list)


def apply_policy(
    state: PersonaState,
    action: AgentAction,
    *,
    path: str,
    page_text: str,
    element_label: str | None,
    element_kind: str | None,
    mem: PolicyMemory,
) -> PolicyDecision:
    t = state.persona_type
    mem.steps_since_forced_back += 1

    # Disallowed action slipped through the prompt -> nearest allowed equivalent.
    if action.action not in allowed_actions(state):
        action = action.model_copy(update={"action": "scroll" if action.action == "wait" else "click"})
        if action.action == "click" and action.element_id is None:
            action = action.model_copy(update={"action": "back"})

    if action.action == "scroll":
        mem.scrolled_paths.add(path)

    if t == "chaos":
        r = mem.rng.random()
        if action.action == "type" and element_kind and element_kind.startswith("input") and r < 0.45:
            value = mem.rng.choice(EDGE_CASE_INPUTS)
            return PolicyDecision(action.model_copy(update={"text": value}), tags=["edge_case_input"])
        if action.action == "click" and r < 0.30:
            return PolicyDecision(action, double_click=True, tags=["double_click"])
        if action.action in ("click", "type") and state.action_count >= 2 and mem.steps_since_forced_back > 4 and r > 0.88:
            mem.steps_since_forced_back = 0
            return PolicyDecision(AgentAction(action="back", thought="(chaos) going back mid-flow", confidence=0.5),
                                  tags=["forced_back", "deterministic"])

    if t == "cautious" and action.action == "click" and element_label and SUBMIT_WORDS.search(element_label):
        if RISK_PAGE.search(page_text) and path not in mem.scrolled_paths:
            mem.scrolled_paths.add(path)
            return PolicyDecision(
                AgentAction(action="scroll", thought="Before I commit, let me look for fee and privacy details.",
                            confidence=0.6, expects="fee or terms explanation"),
                tags=["deterministic"],
            )

    return PolicyDecision(action)
