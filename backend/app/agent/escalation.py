"""Visual escalation (spec §10): when text isn't enough, a screenshot goes to Gemini once per page per run.

Trigger (deterministic): the page hasn't changed for >= 2 of the persona's actions, or the page offers < 2
interactive elements. Budget: MAX_PER_RUN calls; results cached by page_hash and shared across personas.
"""

import asyncio
import logging

from app.agent.graph import Escalator, EventSink
from app.browser.observe import Observation
from app.browser.session import PersonaSession
from app.config import get_settings
from app.llm.base import LLMError
from app.llm.gemini_pool import gemini_pool
from app.models.schemas import PersonaState

log = logging.getLogger(__name__)

MAX_PER_RUN = 4

PROMPT = (
    "A simulated website user ({label}) is trying to: {goal}\n"
    "They seem stuck on this page. Looking ONLY at the screenshot, describe in at most 70 words: what is visually "
    "most prominent, where the most likely next step is, and any messages, warnings or hidden-looking text. "
    "Never invent elements that are not visible. Plain text, no lists."
)

FAKE_NOTE = "(fake visual note) The main button is near the top; small grey footer text may contain instructions."


def _unchanged_steps(persona: PersonaState) -> int:
    h = persona.recent_hashes
    n = 0
    for x in reversed(h):
        if x != h[-1]:
            break
        n += 1
    return n


def should_escalate(persona: PersonaState, obs: Observation) -> str | None:
    if persona.action_count == 0:
        return None
    if len(persona.recent_hashes) >= 2 and _unchanged_steps(persona) >= 2:
        return "page unchanged"
    if len(obs.elements) < 2:
        return "few interactive elements"
    return None


def make_escalator(run_id: str, sink: EventSink) -> Escalator:
    cache: dict[str, str | None] = {}
    inflight: dict[str, asyncio.Future] = {}
    budget = {"used": 0}

    async def escalate(session: PersonaSession, obs: Observation, persona: PersonaState, history: list[str]) -> str | None:
        reason = should_escalate(persona, obs)
        if reason is None:
            return None
        key = obs.page_hash
        if key in cache:
            return cache[key]
        if key in inflight:  # another persona is already asking about this exact page
            return await inflight[key]
        if budget["used"] >= MAX_PER_RUN:
            return None

        budget["used"] += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        inflight[key] = fut
        step = persona.action_count + 1
        note, model, path = None, "none", None
        try:
            shot = await session.screenshot()
            path = await sink.screenshot(persona.persona_id, step, "escalation", shot)
            if get_settings().gemini_mode == "fake":
                note, model = FAKE_NOTE, "fake"
            else:
                res = await gemini_pool().generate(
                    "visual", PROMPT.format(label=persona.label, goal=persona.goal), image_jpeg=shot,
                    max_output_tokens=1500, max_wait_s=25)
                note, model = " ".join(res.text.split())[:600], res.model
        except LLMError as e:
            log.warning("visual escalation unavailable: %s", e)
        except Exception as e:  # noqa: BLE001 - escalation is best-effort
            log.warning("visual escalation failed: %s", e)
        finally:
            cache[key] = note
            inflight.pop(key, None)
            fut.set_result(note)

        await sink.emit("escalation", persona.persona_id, step, obs.url, {
            "model": model, "observation": note or "(visual escalation unavailable)", "reason": reason,
            "screenshot_path": path, "screenshot_url": None, "budget_used": budget["used"],
        })
        return note

    return escalate
