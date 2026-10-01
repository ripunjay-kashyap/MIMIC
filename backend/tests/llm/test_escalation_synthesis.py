"""Gate 8: visual escalation budget/dedupe and synthesis validation (no real quota)."""

import asyncio
import json

import pytest

from app.agent import escalation as esc
from app.agent.sinks import MemorySink
from app.analysis import synthesis
from app.browser.observe import Element, Observation
from app.config import get_settings
from app.llm.base import LLMError
from app.llm.gemini_pool import GeminiResult
from app.models.schemas import EvidenceRef, Finding
from app.personas.cohort import generate_cohort


def persona(ptype="power", **kw):
    p = next(p for p in generate_cohort("Buy a policy") if p.persona_type == ptype)
    return p.model_copy(update=kw)


def obs(page_hash="h1", n_elements=5):
    els = [Element(i, "button", "", "", f"B{i}", True, None, "", None, "", None, False) for i in range(n_elements)]
    return Observation(url="http://x/demo/verify.html", title="t", headings=[], alerts=[], text="", elements=els,
                       page_hash=page_hash)


class FakeSession:
    def __init__(self):
        self.shots = 0

    async def screenshot(self):
        self.shots += 1
        return b"\xff\xd8jpeg"


def test_trigger_rules():
    assert esc.should_escalate(persona(action_count=0), obs()) is None
    assert esc.should_escalate(persona(action_count=3, recent_hashes=["a", "b", "c"]), obs()) is None
    assert esc.should_escalate(persona(action_count=3, recent_hashes=["a", "b", "b"]), obs()) == "page unchanged"
    assert esc.should_escalate(persona(action_count=1, recent_hashes=["a"]), obs(n_elements=1)) == "few interactive elements"


async def test_budget_and_dedupe(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_mode", "fake")
    sink = MemorySink("r")
    escalate = esc.make_escalator("r", sink)
    stuck = persona(action_count=4, recent_hashes=["x", "x", "x"])
    session = FakeSession()

    # Three personas stuck on the same page at once -> one call, everyone gets the note.
    notes = await asyncio.gather(*(escalate(session, obs("same"), stuck, []) for _ in range(3)))
    assert notes == [esc.FAKE_NOTE] * 3 and session.shots == 1

    for i in range(10):  # distinct pages -> stops at the per-run budget
        await escalate(session, obs(f"page{i}"), stuck, [])
    events = [e for e in sink.events if e.type == "escalation"]
    assert len(events) == esc.MAX_PER_RUN
    assert all(e.payload["screenshot_path"] for e in events)


async def test_escalation_failure_is_soft(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_mode", "real")

    class DownPool:
        async def generate(self, *a, **k):
            raise LLMError("all keys exhausted")

    monkeypatch.setattr(esc, "gemini_pool", lambda: DownPool())
    sink = MemorySink("r")
    note = await esc.make_escalator("r", sink)(FakeSession(), obs(), persona(action_count=3, recent_hashes=["a", "a"]), [])
    assert note is None
    assert sink.events[-1].payload["observation"] == "(visual escalation unavailable)"


def finding(i):
    return Finding(run_id="r", category="stuck_on_page", severity="medium", page=f"/p{i}", personas=["power-01"],
                   evidence=[EvidenceRef(persona_id="power-01", seq=i + 1)], observed=f"fact {i}",
                   interpretation="template", suggested_investigation="template", source="template")


async def test_synthesis_rewrites_only_valid_indexes(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_mode", "real")
    reply = {"findings": [
        {"index": 0, "interpretation": "The OTP step may lack feedback.", "suggested_investigation": "Test a spinner."},
        {"index": 7, "interpretation": "hallucinated", "suggested_investigation": "x"},
        {"index": 1, "interpretation": 42},
    ]}

    class Pool:
        async def generate(self, *a, **k):
            return GeminiResult(text=json.dumps(reply), model="gemini-3.8-flash", key_hash="k")

    monkeypatch.setattr(synthesis, "gemini_pool", lambda: Pool())
    fs = [finding(0), finding(1)]
    out = await synthesis.synthesize("goal", [persona()], fs)
    assert len(out) == 2
    assert out[0].source == "llm_synthesized" and out[0].interpretation.startswith("The OTP step")
    assert out[1].source == "template" and out[1].interpretation == "template"
    assert [f.observed for f in out] == ["fact 0", "fact 1"] and out[0].evidence == fs[0].evidence
    assert fs[0].source == "template"  # input not mutated


async def test_synthesis_fake_mode_is_noop(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_mode", "fake")
    fs = [finding(0)]
    assert await synthesis.synthesize("goal", [persona()], fs) == fs


async def test_pool_skips_overloaded_model_and_counts_every_request(monkeypatch):
    import httpx

    from app.llm import gemini_pool as gp

    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_keys", ["k1", "k2", "k3"])
    monkeypatch.setattr(s, "gemini_models", ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"])

    async def no_db():
        return None

    monkeypatch.setattr(gp, "get_db", no_db)
    calls = []

    def handler(request: httpx.Request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        calls.append((model, request.headers["x-goog-api-key"]))
        if model == "gemini-3.8-flash":
            return httpx.Response(503, json={"error": {"code": 503}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                                         "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}})

    pool = gp.GeminiPool()
    pool._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    res = await pool.generate("visual", "describe")
    assert res.model == "gemini-3.7-flash"
    assert [m for m, _ in calls].count("gemini-3.8-flash") == 1  # not retried on the other two keys
    assert sum(p.day_count for p in pool.pairs) == 2  # the failed 503 still counted
