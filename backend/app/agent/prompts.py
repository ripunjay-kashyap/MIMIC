"""Persona prompts. Target ~800 tokens per decision call (Groq TPM is the binding constraint)."""

from app.llm.base import ChatMessage
from app.models.schemas import PersonaState
from app.personas.policies import allowed_actions
from app.personas.templates import TEMPLATES_BY_TYPE

HISTORY_STEPS = 2


def _feeling(f: float, threshold: float) -> str:
    ratio = f / threshold if threshold else 0
    if ratio < 0.25:
        return "You feel calm."
    if ratio < 0.55:
        return "You are a bit annoyed."
    if ratio < 0.8:
        return "You are frustrated and close to giving up."
    return "You are very frustrated and about to give up."


def system_prompt(persona: PersonaState) -> str:
    t = TEMPLATES_BY_TYPE[persona.persona_type]
    ident = t.test_identity
    acts = ", ".join(allowed_actions(persona))
    return (
        f"You are simulating a real website user for usability testing. Persona: {persona.label}.\n"
        f"{t.behavior}\n"
        f"GOAL: {persona.goal}\n"
        f"If a form asks for your details use ONLY this test identity: name {ident['name']}, mobile {ident['mobile']}, "
        f"PIN code {ident['pin']}, date of birth {ident['dob']}.\n"
        "RULES: Choose exactly ONE next action. Use only element ids from the ELEMENTS list; never invent ids. "
        "Elements marked [RISKY: blocked] cannot be used. Stay in character. "
        "Use 'done' only when the goal is visibly complete. Use 'give_up' only if you would really leave.\n"
        f"Allowed actions: {acts}. 'type' fills one input with 'text'; 'select' picks an option by its text. "
        "'back' is the browser Back button and is ALWAYS available (no element_id). "
        "click/type/select need an element_id; scroll/back/wait/done/give_up don't.\n"
        'Reply with JSON only: {"action": "...", "element_id": int|null, "text": str|null, '
        '"thought": "<=25 words, first person, in character", "confidence": 0..1, "expects": "<=12 words"}'
    )


def _unchanged_steps(persona: PersonaState) -> int:
    h = persona.recent_hashes
    n = 0
    for x in reversed(h):
        if x != h[-1]:
            break
        n += 1
    return n


class JourneyMemory:
    """What a person would remember: the pages they've been through and which links led nowhere."""

    TRAIL = 8

    def __init__(self, start_path: str | None = None) -> None:
        self.trail: list[str] = [start_path] if start_path else []
        self.tried: dict[str, dict[str, dict]] = {}  # page -> label -> {to, count, returned}

    def record(self, path_before: str, action: str, label: str | None, navigated_to: str | None) -> None:
        if navigated_to and (not self.trail or self.trail[-1] != navigated_to):
            if not self.trail:
                self.trail.append(path_before)
            self.trail.append(navigated_to)
        if action == "click" and label and navigated_to:
            t = self.tried.setdefault(path_before, {}).setdefault(label, {"to": navigated_to, "count": 0, "returned": False})
            t["count"] += 1
            t["to"] = navigated_to
        if action == "back" and navigated_to:
            for t in self.tried.get(navigated_to, {}).values():
                if t["to"] == path_before:
                    t["returned"] = True

    def lines(self, path: str) -> list[str]:
        out = []
        if len(self.trail) > 1:
            out.append("JOURNEY SO FAR: " + " → ".join(self.trail[-self.TRAIL:]))
        tried = self.tried.get(path, {})
        if tried:
            parts = []
            for label, t in tried.items():
                note = " (you came back from there)" if t["returned"] else ""
                times = f", {t['count']}×" if t["count"] > 1 else ""
                parts.append(f"'{label}' → {t['to']}{note}{times}")
            out.append("ALREADY TRIED ON THIS PAGE: " + "; ".join(parts))
        return out


def user_prompt(persona: PersonaState, observation_text: str, history: list[str], *, escalation: str | None = None,
                memory_lines: list[str] | None = None) -> str:
    lines = [observation_text]
    lines.extend(memory_lines or [])
    if len(persona.recent_hashes) >= 2 and _unchanged_steps(persona) >= 2:
        lines.append(f"NOTE: this page has not changed during your last {_unchanged_steps(persona)} actions.")
    if escalation:
        lines.append(f"VISUAL NOTE (from a screenshot): {escalation}")
    lines.append("RECENT STEPS: " + (" | ".join(history[-HISTORY_STEPS:]) if history else "(none, first step)"))
    lines.append(
        f"STATUS: step {persona.action_count + 1} of at most {persona.max_actions}. "
        f"{_feeling(persona.current_frustration, persona.abandon_frustration)}"
    )
    return "\n".join(lines)


def build_messages(persona: PersonaState, observation_text: str, history: list[str], *,
                   escalation: str | None = None, memory_lines: list[str] | None = None) -> list[ChatMessage]:
    return [
        ChatMessage("system", system_prompt(persona)),
        ChatMessage("user", user_prompt(persona, observation_text, history, escalation=escalation,
                                        memory_lines=memory_lines)),
    ]


def history_line(action: str, label: str | None, text: str | None, ok: bool, error: str | None, navigated_to: str | None,
                 changed: bool = True) -> str:
    target = f" '{label}'" if label else ""
    typed = f" = '{text[:30]}'" if text is not None and action == "type" else ""
    if navigated_to:
        outcome = f"-> now on {navigated_to}"
    elif not ok:
        outcome = f"-> failed ({error})"
    elif action == "scroll" and not changed:
        outcome = "-> nothing new, already at the bottom"
    else:
        outcome = "-> ok, same page" if changed else "-> nothing visibly changed"
    return f"{action}{target}{typed} {outcome}"
