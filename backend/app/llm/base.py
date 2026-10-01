"""Shared LLM types + JSON parsing for agent decisions."""

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.models.schemas import AgentAction


class LLMError(Exception):
    """Provider failed (HTTP error, timeout, quota). `retryable` = try another model."""

    def __init__(self, message: str, *, retryable: bool = True, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class InvalidOutput(LLMError):
    pass


@dataclass
class Decision:
    action: AgentAction
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fallback: bool = False
    raw: str = ""


@dataclass
class ChatMessage:
    role: str  # "system" | "user"
    content: str


def estimate_tokens(messages: list[ChatMessage]) -> int:
    return sum(len(m.content) for m in messages) // 4 + 8


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_action(text: str) -> AgentAction:
    cleaned = _FENCE.sub("", (text or "").strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise InvalidOutput(f"no JSON object in output: {cleaned[:120]!r}")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise InvalidOutput(f"invalid JSON: {e}") from e
    if isinstance(data.get("element_id"), str) and data["element_id"].strip().isdigit():
        data["element_id"] = int(data["element_id"])
    for k in ("thought", "expects"):
        if isinstance(data.get(k), str):
            data[k] = data[k][:200 if k == "expects" else 400]
    if isinstance(data.get("confidence"), (int, float)):
        data["confidence"] = min(1.0, max(0.0, float(data["confidence"])))
    try:
        return AgentAction.model_validate(data)
    except ValidationError as e:
        raise InvalidOutput(f"schema: {e.errors()[0]['msg']}") from e
