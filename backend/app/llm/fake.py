"""Scripted decision-maker for LLM_MODE=fake: zero quota, deterministic, drives the demo site.

It reads the same observation prompt the real model gets, so the whole pipeline is exercised.
Persona-flavoured detours make fake cohorts diverge (useful for orchestration/UI tests).
"""

import re

from app.llm.base import Decision
from app.models.schemas import AgentAction

_EL = re.compile(r'^\[(\d+)\] (\S+) "([^"]*)"(.*)$')

HAPPY_PATH_CLICKS = ["Get a Quote", "Select", "Continue", "Send OTP", "Verify", "Confirm & Continue", "Proceed"]


def _elements(prompt: str) -> list[tuple[int, str, str, str]]:
    out = []
    for line in prompt.splitlines():
        m = _EL.match(line.strip())
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
    return out


def _path(prompt: str) -> str:
    m = re.search(r"^URL: (\S+)", prompt, re.MULTILINE)
    return m.group(1) if m else ""


def fake_decide(persona_type: str, prompt: str, identity: dict, step: int) -> Decision:
    els = _elements(prompt)
    path = _path(prompt)

    def act(action: str, el: tuple | None = None, text: str | None = None, thought: str = "") -> Decision:
        return Decision(AgentAction(action=action, element_id=el[0] if el else None, text=text,
                                    thought=thought or f"(fake) {action} {el[2] if el else ''}".strip(),
                                    confidence=0.8, expects="next step"), model="fake")

    by_label = {e[2]: e for e in els}
    is_home = path.endswith("/") or path.endswith("/index.html")

    # Persona detours (first visits only, keyed on step so they're deterministic).
    if persona_type == "low_literacy" and is_home and step == 1 and "Get Started" in by_label:
        return act("click", by_label["Get Started"], thought="'Get Started' sounds like where to begin.")
    if persona_type == "explorer" and is_home and step == 1 and "Explore Plans" in by_label:
        return act("click", by_label["Explore Plans"], thought="Let me compare the plans first.")
    if path.endswith("learn.html") or (path.endswith("explore.html") and "Get a Quote" not in by_label):
        return act("back", thought="This page doesn't help me buy anything.")

    # Fill empty text inputs from the persona's test identity.
    field_values = {"Full name": identity.get("name"), "Mobile number": identity.get("mobile"),
                    "PIN code": identity.get("pin"), "Date of birth": identity.get("dob"), "Enter OTP": "123456"}
    for el in els:
        if el[1].startswith("input[") and 'value=""' in el[3] and field_values.get(el[2]):
            return act("type", el, field_values[el[2]])

    if path.endswith("verify.html") and "Send OTP" in by_label and "Enter OTP" not in by_label:
        if "click 'Send OTP'" in prompt:
            return act("wait", thought="Waiting for the OTP to arrive.")
        return act("click", by_label["Send OTP"])

    for label in HAPPY_PATH_CLICKS:
        if label in by_label and not (label == "Send OTP" and "Enter OTP" in by_label):
            return act("click", by_label[label])

    if persona_type == "impatient":
        return act("give_up", thought="This is taking too long.")
    return act("back", thought="I'm not sure where to go from here.")
