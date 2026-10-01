"""Single entry point for agent decisions. Callers never import a provider directly.

Order: persona's pinned Groq model -> least-loaded other Groq model -> Gemini Flash-Lite -> safe default.
"""

import logging

from app.config import get_settings
from app.llm import groq_client
from app.llm.base import ChatMessage, Decision, InvalidOutput, LLMError, estimate_tokens, parse_action
from app.llm.fake import fake_decide
from app.llm.gemini_pool import gemini_pool
from app.models.schemas import AgentAction, PersonaState

log = logging.getLogger(__name__)

SPILLOVER_WAIT_S = 6.0  # if the pinned model would make us wait longer than this, try another


def _groq_order(pinned: str | None, messages: list[ChatMessage]) -> list[str]:
    models = list(get_settings().groq_models)
    if not models:
        return []
    pinned = pinned if pinned in models else models[0]
    tokens = groq_client.reserve_tokens(messages)
    others = sorted((m for m in models if m != pinned), key=lambda m: groq_client.groq_limiter(m).wait_time(tokens))
    if groq_client.groq_limiter(pinned).wait_time(tokens) > SPILLOVER_WAIT_S and others:
        best = others[0]
        if groq_client.groq_limiter(best).wait_time(tokens) < groq_client.groq_limiter(pinned).wait_time(tokens):
            return [best, pinned, *others[1:]]
    return [pinned, *others]


async def _gemini_decide(messages: list[ChatMessage]) -> Decision:
    system = "\n".join(m.content for m in messages if m.role == "system")
    user = "\n".join(m.content for m in messages if m.role == "user")
    res = await gemini_pool().generate("decision", user, system=system, json_output=True, max_output_tokens=400)
    return Decision(parse_action(res.text), model=res.model, prompt_tokens=res.prompt_tokens,
                    completion_tokens=res.output_tokens, raw=res.text[:600])


async def decide(persona: PersonaState, messages: list[ChatMessage], *, identity: dict | None = None,
                 step: int = 1) -> Decision:
    if get_settings().llm_mode == "fake":
        user = next(m.content for m in messages if m.role == "user")
        return fake_decide(persona.persona_type, user, identity or {}, step)

    errors: list[str] = []
    if persona.llm_model and persona.llm_model.startswith("gemini"):
        try:
            return await _gemini_decide(messages)
        except LLMError as e:
            errors.append(str(e))

    for model in _groq_order(persona.llm_model, messages):
        try:
            d = await groq_client.decide(model, messages)
            d.fallback = model != persona.llm_model
            return d
        except InvalidOutput as e:
            errors.append(f"{model}: {e}")
            # One repair attempt on the same model with the validation error appended.
            try:
                repair = messages + [ChatMessage("user", f"Your last reply was invalid ({e}). Reply with ONLY the JSON object.")]
                d = await groq_client.decide(model, repair)
                d.fallback = model != persona.llm_model
                return d
            except LLMError as e2:
                errors.append(f"{model} repair: {e2}")
        except LLMError as e:
            errors.append(f"{model}: {e}")
            if not e.retryable:
                break

    try:
        d = await _gemini_decide(messages)
        d.fallback = True
        return d
    except LLMError as e:
        errors.append(str(e))

    log.warning("all decision providers failed for %s: %s", persona.persona_id, errors)
    # Safe default; the state engine counts the scroll as a normal step (budget still advances).
    return Decision(AgentAction(action="scroll", thought="(no model available) looking around", confidence=0.0),
                    model="none", fallback=True, raw="; ".join(errors)[:600])


def decision_tokens(messages: list[ChatMessage]) -> int:
    return estimate_tokens(messages)
