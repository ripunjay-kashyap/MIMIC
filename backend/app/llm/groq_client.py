"""Groq chat completions (OpenAI-compatible) for routine next-action decisions."""

import httpx
from langsmith import traceable

from app.config import get_settings
from app.llm.base import ChatMessage, Decision, LLMError, estimate_tokens, parse_action
from app.llm.ratelimit import limiter

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_COMPLETION_TOKENS = 300

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    return _client


def reasoning_params(model: str) -> dict:
    if "gpt-oss" in model:
        return {"reasoning_effort": "low"}
    if "qwen" in model:
        return {"reasoning_effort": "none"}
    return {}


def groq_limiter(model: str):
    s = get_settings()
    return limiter(f"groq:{model}", s.groq_rpm, s.groq_tpm)


def reserve_tokens(messages: list[ChatMessage]) -> int:
    return estimate_tokens(messages) + MAX_COMPLETION_TOKENS


@traceable(run_type="llm", name="groq.decide")
async def decide(model: str, messages: list[ChatMessage]) -> Decision:
    key = get_settings().groq_api_key
    if not key:
        raise LLMError("GROQ_API_KEY not set", retryable=False)
    lim = groq_limiter(model)
    reserved = reserve_tokens(messages)
    await lim.acquire(reserved)
    body = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": 0.2,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"},
        **reasoning_params(model),
    }
    try:
        resp = await _http().post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
    except httpx.HTTPError as e:
        raise LLMError(f"groq transport error: {type(e).__name__}") from e
    if resp.status_code != 200:
        raise LLMError(f"groq HTTP {resp.status_code}: {resp.text[:160]}", status=resp.status_code,
                       retryable=resp.status_code in (408, 429, 498, 500, 502, 503, 504) or resp.status_code == 400)
    data = resp.json()
    usage = data.get("usage") or {}
    lim.settle(reserved, int(usage.get("total_tokens") or reserved))
    content = data["choices"][0]["message"].get("content") or ""
    return Decision(
        action=parse_action(content),
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        raw=content[:600],
    )
