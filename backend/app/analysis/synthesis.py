"""One Gemini call rewrites interpretation/suggested_investigation for existing findings (spec §16).

It may NOT add findings, change evidence, or change observed facts. Falls back to the templates on any failure.
"""

import json
import logging

from app.config import get_settings
from app.llm.gemini_pool import gemini_pool
from app.models.schemas import Finding, PersonaState

log = logging.getLogger(__name__)

MAX_FINDINGS = 12

SYSTEM = (
    "You are a senior UX researcher reviewing evidence from SYNTHETIC users (AI agents with behavioural profiles) "
    "who tried a task on a website. You never claim confirmed bugs or real-user behaviour. Use hedged language "
    "('may', 'could', 'suggests'). Be concrete and specific to the page and evidence. No marketing tone."
)

PROMPT = """Task the synthetic users attempted: {goal}

Persona outcomes:
{outcomes}

Findings (observed facts are fixed; do not change them):
{findings}

For EACH finding index, write:
- "interpretation": 1-2 sentences on what the evidence may indicate about the design.
- "suggested_investigation": 1 sentence naming what a team should review or test with real users.
Return JSON: {{"findings": [{{"index": 0, "interpretation": "...", "suggested_investigation": "..."}}, ...]}}"""


def _outcomes(personas: list[PersonaState]) -> str:
    return "\n".join(f"- {p.label}: {p.task_status} after {p.action_count} actions ({p.termination_reason or ''})"
                     for p in personas)


def _findings(findings: list[Finding]) -> str:
    return "\n".join(f"[{i}] {f.category} on {f.page or 'whole journey'} ({f.severity}; personas: {', '.join(f.personas)}): "
                     f"{f.observed}" for i, f in enumerate(findings))


async def synthesize(goal: str, personas: list[PersonaState], findings: list[Finding]) -> list[Finding]:
    if not findings or get_settings().gemini_mode == "fake":
        return findings
    head, tail = findings[:MAX_FINDINGS], findings[MAX_FINDINGS:]
    res = await gemini_pool().generate(
        "synthesis", PROMPT.format(goal=goal, outcomes=_outcomes(personas), findings=_findings(head)),
        system=SYSTEM, json_output=True, max_output_tokens=4096, max_wait_s=40)
    data = json.loads(res.text)
    items = data.get("findings", data) if isinstance(data, dict) else data
    out = [f.model_copy(deep=True) for f in head]
    rewritten = 0
    for item in items if isinstance(items, list) else []:
        i = item.get("index")
        interp, invest = item.get("interpretation"), item.get("suggested_investigation")
        if not isinstance(i, int) or not (0 <= i < len(out)) or not isinstance(interp, str) or not isinstance(invest, str):
            continue  # unknown index or malformed -> keep the template
        out[i].interpretation = interp.strip()[:600]
        out[i].suggested_investigation = invest.strip()[:400]
        out[i].source = "llm_synthesized"
        rewritten += 1
    log.info("synthesis (%s) rewrote %d/%d findings", res.model, rewritten, len(head))
    return out + tail
