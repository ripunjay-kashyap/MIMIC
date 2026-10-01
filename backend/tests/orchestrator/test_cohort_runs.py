"""Gate 6/7: six personas in parallel through the HTTP API (fake LLM, in-memory repo, local demo site)."""

import asyncio
import json
import time

import httpx
import pytest

from app.api import runs as runs_api
from app.config import get_settings
from app.db.repo import MemoryRepo, set_repo
from app.main import app
from app.orchestrator import run_manager as rm
from app.orchestrator.run_manager import RunManager


@pytest.fixture
async def env(pool, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_mode", "fake")
    monkeypatch.setattr(s, "allow_local_targets", True)
    repo = MemoryRepo()
    set_repo(repo)
    manager = RunManager()
    monkeypatch.setattr(rm, "pool", pool)
    monkeypatch.setattr(runs_api, "manager", manager)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        yield client, manager, repo, pool
    set_repo(None)


def body(url):
    return {"target_url": url, "goal": "Choose a plan and reach the policy confirmation page.",
            "success_criteria": {"url_contains": "confirmed"}, "authorized": True}


async def create_and_run(client, manager, url):
    t0 = time.monotonic()
    r = await client.post("/runs", json=body(url))
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    t_create = time.monotonic() - t0
    r = await client.post(f"/runs/{run_id}/start")
    assert r.status_code == 202, r.text
    t_start = time.monotonic() - t0 - t_create
    await asyncio.wait_for(manager.wait(run_id), timeout=300)
    return run_id, t_create, t_start


async def test_full_cohort_run_through_api(env, demo_site_url):
    client, manager, repo, pool = env
    run_id, t_create, t_start = await create_and_run(client, manager, demo_site_url)
    assert t_create < 1.0 and t_start < 1.0

    run = (await client.get(f"/runs/{run_id}")).json()
    assert run["status"] == "completed", run.get("error")
    assert len(run["personas"]) == 6
    statuses = {p["persona_id"]: p["task_status"] for p in run["personas"]}
    assert all(s not in ("pending", "active") for s in statuses.values()), statuses
    assert statuses["power-01"] == "success"
    assert run["metrics"]["success_count"] >= 1

    # Isolation: typed values only ever come from the persona's own identity or the chaos edge-case list.
    from app.personas.policies import EDGE_CASE_INPUTS
    from app.personas.templates import TEMPLATES_BY_TYPE
    events = await repo.get_events(run_id)
    for p in run["personas"]:
        ident = set(TEMPLATES_BY_TYPE[p["persona_type"]].test_identity.values()) | {"123456"}
        typed = {e.payload["action"]["text"] for e in events
                 if e.persona_id == p["persona_id"] and e.type == "decision" and e.payload["action"]["action"] == "type"}
        allowed = ident | (set(EDGE_CASE_INPUTS) if p["persona_type"] == "chaos" else set())
        assert typed <= allowed, (p["persona_id"], typed - allowed)

    # Persistence: events contiguous, final states stored, findings stored.
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, len(seqs) + 1))
    assert all(p.task_status not in ("pending", "active") for p in await repo.get_personas(run_id))

    report = (await client.get(f"/runs/{run_id}/report")).json()
    assert set(report["metrics"]) >= {"completion_rate", "abandonment_rate", "average_actions", "unique_paths"}
    seq_set = set(seqs)
    for f in report["findings"]:
        assert f["evidence"] and all(ev["seq"] in seq_set for ev in f["evidence"])

    journey = (await client.get(f"/runs/{run_id}/personas/power-01/journey")).json()
    assert journey["persona"]["task_status"] == "success"
    assert journey["events"][0]["type"] == "persona_started" and journey["events"][-1]["type"] == "persona_finished"
    assert any(e["type"] == "screenshot" for e in journey["events"])

    # Resource cleanup: every BrowserContext closed.
    assert pool.browser.contexts == []


async def test_sse_replay_and_resume(env, demo_site_url):
    client, manager, repo, _ = env
    run_id, *_ = await create_and_run(client, manager, demo_site_url)

    async def read_stream(last_id=None):
        headers = {"Last-Event-ID": str(last_id)} if last_id else {}
        out = []
        async with client.stream("GET", f"/runs/{run_id}/events", headers=headers) as r:
            assert r.status_code == 200
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    out.append(json.loads(line[5:].strip()))
        return out

    full = await read_stream()
    assert full[0]["type"] == "run_status" and full[-1] == {**full[-1], "type": "run_status"}
    assert full[-1]["payload"]["status"] == "completed"
    resumed = await read_stream(last_id=40)
    assert [e["seq"] for e in resumed] == [e["seq"] for e in full if e["seq"] > 40]


async def test_live_stream_while_running(env, demo_site_url):
    client, manager, repo, _ = env
    r = await client.post("/runs", json=body(demo_site_url))
    run_id = r.json()["run_id"]
    received = []

    async def listen():
        async with client.stream("GET", f"/runs/{run_id}/events") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    received.append(json.loads(line[5:].strip()))

    listener = asyncio.create_task(listen())  # connects while cohort_ready and waits for deploy
    await asyncio.sleep(0.5)
    assert (await client.post(f"/runs/{run_id}/start")).status_code == 202
    await asyncio.wait_for(listener, timeout=300)
    seqs = [e["seq"] for e in received]
    assert seqs == sorted(set(seqs)) and seqs[0] == 1
    assert {e["persona_id"] for e in received if e["persona_id"]} == {
        "impatient-01", "low-literacy-01", "power-01", "cautious-01", "explorer-01", "chaos-01"}
    assert received[-1]["payload"]["status"] == "completed"


async def test_one_failing_persona_does_not_crash_run(env, demo_site_url, monkeypatch):
    client, manager, repo, pool = env
    real_session = pool.session

    def flaky(persona_id, url, device="desktop"):
        if persona_id == "cautious-01":
            raise RuntimeError("browser context could not be created")
        return real_session(persona_id, url, device)

    monkeypatch.setattr(pool, "session", flaky)
    run_id, *_ = await create_and_run(client, manager, demo_site_url)
    run = (await client.get(f"/runs/{run_id}")).json()
    st = {p["persona_id"]: p["task_status"] for p in run["personas"]}
    assert run["status"] == "completed"
    assert st["cautious-01"] == "error"
    assert st["power-01"] == "success"


async def test_second_start_conflicts_and_bad_requests(env, demo_site_url):
    client, manager, repo, _ = env
    r1 = (await client.post("/runs", json=body(demo_site_url))).json()["run_id"]
    r2 = (await client.post("/runs", json=body(demo_site_url))).json()["run_id"]
    assert (await client.post(f"/runs/{r1}/start")).status_code == 202
    resp = await client.post(f"/runs/{r2}/start")
    assert resp.status_code == 409 and "in progress" in resp.json()["detail"]
    assert (await client.post(f"/runs/{r1}/start")).status_code == 409  # already running
    assert (await client.get(f"/runs/{r2}/report")).status_code == 409
    assert (await client.get("/runs/nope")).status_code == 404
    assert (await client.post("/runs", json={**body(demo_site_url), "authorized": False})).status_code == 400
    await manager.wait(r1)


async def test_orphaned_runs_marked_failed(env):
    client, manager, repo, _ = env
    await repo.insert_run({"id": "orphan", "target_url": "x", "goal": "g", "status": "running", "created_at": "t"})
    await manager.recover_orphans()
    assert (await repo.get_run("orphan"))["status"] == "failed"
