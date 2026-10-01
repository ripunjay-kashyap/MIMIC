"""Gate 5: single-persona loop with fake/scripted LLMs. Zero quota."""

import pytest

from app.agent import graph as graph_mod
from app.agent.graph import PersonaRunContext, run_persona
from app.agent.sinks import MemorySink
from app.config import get_settings
from app.llm.base import Decision
from app.models.schemas import TERMINAL_STATUSES, AgentAction, SuccessCriteria
from app.personas.cohort import DEMO_MILESTONES, generate_cohort

CRIT = SuccessCriteria(url_contains="confirmed")


@pytest.fixture
def fake_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_mode", "fake")
    monkeypatch.setattr(get_settings(), "screenshot_mode", "key")


@pytest.fixture
def demo_root(demo_site_url):
    # conftest serves demo_site at "/", milestones expect "/demo/..." -> use milestones=None-equivalent mapping
    return demo_site_url


def persona(ptype):
    return next(p for p in generate_cohort("Buy a health policy") if p.persona_type == ptype)


async def run(pool, url, ptype, *, milestones=None):
    sink = MemorySink("test-run")
    p = persona(ptype)
    async with pool.session(p.persona_id, url, device=p.device) as s:
        final = await run_persona(PersonaRunContext(run_id="test-run", persona=p, session=s, sink=sink,
                                                    success_criteria=CRIT, milestones=milestones))
    return final, sink


def scripted(actions):
    """Replace the router with a fixed sequence of AgentActions (last one repeats)."""
    calls = {"n": 0}

    async def decide(persona, messages, *, identity=None, step=1):
        a = actions[min(calls["n"], len(actions) - 1)]
        calls["n"] += 1
        return Decision(action=a, model="scripted")

    return decide, calls


async def test_power_persona_succeeds_with_fake_llm(pool, demo_root, fake_mode):
    final, sink = await run(pool, demo_root, "power")
    assert final.task_status == "success", final.termination_reason
    assert final.action_count <= final.max_actions
    types = [e.type for e in sink.events]
    assert types[0] == "persona_started" and types[-1] == "persona_finished"
    # Contract ordering per step: observation -> decision -> action_result -> state_update
    step2 = [e.type for e in sink.events if e.step == 2 and e.type != "screenshot"]
    assert step2 == ["observation", "decision", "action_result", "state_update"]
    obs = next(e for e in sink.events if e.type == "observation")
    assert {"path", "page_hash", "alerts", "prompt", "element_count"} <= set(obs.payload)
    dec = next(e for e in sink.events if e.type == "decision")
    assert {"action", "model", "element_label", "policy_tags"} <= set(dec.payload)
    assert any(e.type == "screenshot" and e.payload["reason"] == "start" for e in sink.events)
    assert any(e.type == "screenshot" and e.payload["reason"] == "final" for e in sink.events)
    seqs = [e.seq for e in sink.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


async def test_low_literacy_detours_then_backtracks(pool, demo_root, fake_mode):
    final, sink = await run(pool, demo_root, "low_literacy")
    paths = [e.payload["path"] for e in sink.events if e.type == "observation"]
    assert "/learn.html" in paths
    assert final.backtracks >= 1


async def test_loop_is_bounded_when_llm_only_waits(pool, demo_root, monkeypatch):
    decide, calls = scripted([AgentAction(action="wait", thought="hmm")])
    monkeypatch.setattr(graph_mod.router, "decide", decide)
    final, _ = await run(pool, demo_root, "explorer")
    assert final.task_status in ("abandoned", "budget_exhausted")
    assert calls["n"] <= final.max_actions


async def test_hallucinated_element_is_a_failed_attempt(pool, demo_root, monkeypatch):
    decide, _ = scripted([AgentAction(action="click", element_id=999, thought="made up")])
    monkeypatch.setattr(graph_mod.router, "decide", decide)
    final, sink = await run(pool, demo_root, "power")
    results = [e.payload["result"] for e in sink.events if e.type == "action_result"]
    assert results and all(r["error"] == "element_not_found" for r in results)
    assert final.task_status in ("failed", "abandoned")


async def test_early_done_is_not_success(pool, demo_root, monkeypatch):
    decide, _ = scripted([AgentAction(action="done", thought="I'm done!")])
    monkeypatch.setattr(graph_mod.router, "decide", decide)
    final, _ = await run(pool, demo_root, "power")
    assert final.task_status != "success"
    assert final.task_status in TERMINAL_STATUSES


async def test_crash_becomes_error_status_not_exception(pool, demo_root, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(graph_mod.router, "decide", boom)
    final, sink = await run(pool, demo_root, "power")
    assert final.task_status == "error" and "model exploded" in final.termination_reason
    assert sink.events[-1].type == "persona_finished" and sink.events[-1].payload["status"] == "error"


async def test_progress_uses_demo_milestones(pool, demo_site_url, fake_mode):
    # Serve paths as /demo/... by pointing the milestone list at the test server's root paths.
    milestones = [m.replace("/demo/", "/") for m in DEMO_MILESTONES]
    final, _ = await run(pool, demo_site_url, "power", milestones=milestones)
    assert final.progress == 1.0 and not final.progress_estimated
