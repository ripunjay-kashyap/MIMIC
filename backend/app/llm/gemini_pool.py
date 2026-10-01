"""Gemini (key, model) pool: per-task model preference, RPM/RPD budgeting, 503/429 rotation.

Every request SENT counts against RPD (AI Studio counts 503s too). Daily counts persist in Supabase.
"""

import asyncio
import base64
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import httpx
from langsmith import traceable

from app.config import get_settings
from app.db.client import get_db
from app.llm.base import LLMError

log = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
Task = Literal["decision", "visual", "synthesis", "cohort"]

# Per-model free-tier limits (per project), verified in AI Studio. Keyed by substring match.
MODEL_LIMITS = {"flash-lite": (15, 500), "flash": (5, 20)}
SAFETY_MARGIN_RPD = 1  # never use the very last request of the day

TASK_PREFERENCE: dict[Task, list[str]] = {
    "decision": ["flash-lite"],
    "cohort": ["flash-lite"],
    "visual": ["3.8-flash", "3.7-flash", "flash-lite"],
    "synthesis": ["3.8-flash", "3.7-flash", "flash-lite"],
}


def _limits(model: str) -> tuple[int, int]:
    for key, lim in MODEL_LIMITS.items():
        if key in model:
            return lim
    return (5, 20)


def _today() -> str:
    # Gemini daily quotas reset at midnight Pacific; UTC date is close enough with the safety margin.
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class Pair:
    key: str
    model: str
    key_hash: str
    rpm: int
    rpd: int
    sent_times: list[float] = field(default_factory=list)
    day: str = ""
    day_count: int = 0
    cooldown_until: float = 0.0

    def rpm_wait(self) -> float:
        now = time.monotonic()
        self.sent_times = [t for t in self.sent_times if now - t < 60]
        return 0.0 if len(self.sent_times) < self.rpm else 60 - (now - self.sent_times[0]) + 0.05

    def has_daily_budget(self) -> bool:
        return self.day_count < self.rpd - SAFETY_MARGIN_RPD


@dataclass
class GeminiResult:
    text: str
    model: str
    key_hash: str
    prompt_tokens: int = 0
    output_tokens: int = 0


class GeminiPool:
    def __init__(self) -> None:
        s = get_settings()
        self.pairs = [
            Pair(key=k, model=m, key_hash=hashlib.sha256(k.encode()).hexdigest()[:12], rpm=_limits(m)[0], rpd=_limits(m)[1])
            for k in s.gemini_api_keys for m in s.gemini_models
        ]
        self._loaded_day = ""
        self._lock = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def _load_counts(self) -> None:
        today = _today()
        if self._loaded_day == today:
            return
        for p in self.pairs:
            p.day, p.day_count = today, 0
        db = await get_db()
        if db is not None:
            try:
                res = await db.table("gemini_usage").select("key_hash,model,count").eq("day", today).execute()
                counts = {(r["key_hash"], r["model"]): r["count"] for r in res.data}
                for p in self.pairs:
                    p.day_count = counts.get((p.key_hash, p.model), 0)
            except Exception as e:  # noqa: BLE001
                log.warning("could not load gemini usage: %s", e)
        self._loaded_day = today

    async def _record(self, p: Pair) -> None:
        p.sent_times.append(time.monotonic())
        p.day_count += 1
        db = await get_db()
        if db is not None:
            try:
                await db.rpc("increment_gemini_usage",
                             {"p_key_hash": p.key_hash, "p_model": p.model, "p_day": p.day}).execute()
            except Exception as e:  # noqa: BLE001
                log.warning("could not persist gemini usage: %s", e)

    def _candidates(self, task: Task) -> list[Pair]:
        out = []
        for pref in TASK_PREFERENCE[task]:
            group = [p for p in self.pairs if pref in p.model and p not in out]
            group.sort(key=lambda p: p.day_count)  # spread load across keys
            out.extend(group)
        return out

    def remaining(self) -> dict[str, int]:
        rem: dict[str, int] = {}
        for p in self.pairs:
            rem[p.model] = rem.get(p.model, 0) + max(0, p.rpd - SAFETY_MARGIN_RPD - p.day_count)
        return rem

    @traceable(run_type="llm", name="gemini.generate")
    async def generate(
        self, task: Task, prompt: str, *, system: str | None = None, image_jpeg: bytes | None = None,
        json_output: bool = False, max_output_tokens: int = 1024, max_wait_s: float = 20.0,
    ) -> GeminiResult:
        if not self.pairs:
            raise LLMError("no GEMINI_API_KEYS configured", retryable=False)
        await self._load_counts()
        parts: list[dict] = [{"text": prompt}]
        if image_jpeg:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_jpeg).decode()}})
        body: dict = {"contents": [{"role": "user", "parts": parts}],
                      "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.3}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_output:
            body["generationConfig"]["responseMimeType"] = "application/json"

        deadline = time.monotonic() + max_wait_s
        last_error = "no candidate with budget"
        for p in self._candidates(task):
            if not p.has_daily_budget() or time.monotonic() < p.cooldown_until:
                continue
            for attempt in range(2):  # one retry on 503
                async with self._lock:
                    wait = p.rpm_wait()
                    if time.monotonic() + wait > deadline:
                        break
                    if wait:
                        await asyncio.sleep(wait)
                    if not p.has_daily_budget():
                        break
                    await self._record(p)  # counted BEFORE sending: failures count too
                try:
                    resp = await self._http.post(f"{GEMINI_BASE}/models/{p.model}:generateContent",
                                                 headers={"x-goog-api-key": p.key}, json=body)
                except httpx.HTTPError as e:
                    last_error = f"{p.model}: transport {type(e).__name__}"
                    break
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates") or []
                    text = "".join(pt.get("text", "") for pt in (cands[0].get("content", {}).get("parts", []) if cands else []))
                    if not text:
                        last_error = f"{p.model}: empty response ({(cands[0].get('finishReason') if cands else 'no candidates')})"
                        break
                    u = data.get("usageMetadata", {})
                    return GeminiResult(text=text, model=p.model, key_hash=p.key_hash,
                                        prompt_tokens=u.get("promptTokenCount", 0), output_tokens=u.get("candidatesTokenCount", 0))
                last_error = f"{p.model}: HTTP {resp.status_code}"
                if resp.status_code == 503 and attempt == 0:
                    await asyncio.sleep(2)
                    continue
                if resp.status_code == 429:
                    p.cooldown_until = time.monotonic() + 60
                break
        raise LLMError(f"gemini unavailable for {task}: {last_error}")


_pool: GeminiPool | None = None


def gemini_pool() -> GeminiPool:
    global _pool
    if _pool is None:
        _pool = GeminiPool()
    return _pool
