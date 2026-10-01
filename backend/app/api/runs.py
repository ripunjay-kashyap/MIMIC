"""Run API (docs/API_CONTRACT.md)."""

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.api.ratelimit import limit_runs
from app.config import get_settings
from app.db.repo import get_repo
from app.models.schemas import CreateRunRequest, RunEvent, RunSummary
from app.orchestrator.run_manager import RunNotFound, manager

router = APIRouter(prefix="/runs")

WAIT_FOR_START_S = 15 * 60
LIVE_POLL_S = 15


@router.get("/golden")
async def golden_run() -> dict:
    """A known-good completed run for judges/demo fallback (GOLDEN_RUN_ID)."""
    rid = get_settings().golden_run_id
    row = await get_repo().get_run(rid) if rid else None
    if not row or row["status"] != "completed":
        return JSONResponse({"detail": "No golden run configured."}, status_code=404)
    return {"run_id": rid, "goal": row["goal"], "target_url": row["target_url"], "completed_at": row.get("completed_at")}


@router.post("", response_model=RunSummary, dependencies=[Depends(limit_runs("create"))])
async def create_run(req: CreateRunRequest) -> RunSummary:
    return await manager.create_run(req)


@router.post("/{run_id}/start", status_code=202, dependencies=[Depends(limit_runs("start"))])
async def start_run(run_id: str) -> dict:
    await manager.start_run(run_id)
    return {"run_id": run_id, "status": "running"}


@router.get("/{run_id}", response_model=RunSummary)
async def get_run(run_id: str) -> RunSummary:
    return await manager.get_run(run_id)


def _sse(ev: RunEvent) -> dict:
    return {"id": str(ev.seq), "data": json.dumps(ev.model_dump(mode="json"), ensure_ascii=False)}


@router.get("/{run_id}/events")
async def events(run_id: str, request: Request):
    row = await get_repo().get_run(run_id)
    if row is None:
        raise RunNotFound(run_id)
    header = request.headers.get("last-event-id") or request.query_params.get("after") or "0"
    last_seen = int(header) if header.isdigit() else 0

    async def stream():
        nonlocal last_seen
        # A cohort_ready run: hold the connection until the swarm is deployed.
        waited = 0.0
        while manager.buses.get(run_id) is None and waited < WAIT_FOR_START_S:
            current = await get_repo().get_run(run_id) if waited % 5 < 0.5 else None
            if current and current["status"] not in ("cohort_ready", "created"):
                break
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.5)
            waited += 0.5

        bus = manager.buses.get(run_id)
        if bus is None:  # finished before this process started (or after a restart): replay from DB
            for ev in await get_repo().get_events(run_id, after_seq=last_seen):
                yield _sse(ev)
            return

        q = bus.subscribe()  # subscribe BEFORE replaying history so nothing falls in between
        try:
            for ev in list(bus.history):
                if ev.seq > last_seen:
                    last_seen = ev.seq
                    yield _sse(ev)
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=LIVE_POLL_S)
                except asyncio.TimeoutError:
                    if (not bus.is_subscribed(q) and q.empty()) or await request.is_disconnected():
                        return
                    continue
                if ev is None:
                    return
                if ev.seq > last_seen:
                    last_seen = ev.seq
                    yield _sse(ev)
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(stream(), ping=15, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{run_id}/report")
async def report(run_id: str):
    row = await get_repo().get_run(run_id)
    if row is None:
        raise RunNotFound(run_id)
    if row["status"] != "completed":
        return JSONResponse({"detail": f"Run is {row['status']}; the report is available once it completes."},
                            status_code=409)
    findings = await get_repo().get_findings(run_id)
    paths = sorted({ev.screenshot_path for f in findings for ev in f.evidence if ev.screenshot_path})
    urls = await get_repo().signed_urls(paths)
    sev = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (sev.get(f.severity, 3), -len(f.personas)))
    out = []
    for f in findings:
        d = f.model_dump(mode="json")
        for ev in d["evidence"]:
            ev["screenshot_url"] = urls.get(ev.get("screenshot_path") or "")
        out.append(d)
    return {"run_id": run_id, "status": row["status"], "metrics": row.get("metrics") or {}, "findings": out}


@router.get("/{run_id}/personas/{persona_id}/journey")
async def journey(run_id: str, persona_id: str):
    summary = await manager.get_run(run_id)
    persona = next((p for p in summary.personas if p.persona_id == persona_id), None)
    if persona is None:
        return JSONResponse({"detail": f"Persona {persona_id} not found in run."}, status_code=404)
    bus = manager.buses.get(run_id)
    if bus is not None:
        evs = [e for e in bus.history if e.persona_id == persona_id]
    else:
        evs = await get_repo().get_events(run_id, persona_id=persona_id)
    paths = [e.payload.get("path") for e in evs if e.type == "screenshot" and e.payload.get("path")]
    paths += [e.payload.get("screenshot_path") for e in evs if e.type == "escalation" and e.payload.get("screenshot_path")]
    urls = await get_repo().signed_urls(paths)
    out = []
    for e in evs:
        d = e.model_dump(mode="json")
        if e.type == "screenshot":
            d["payload"] = {**d["payload"], "url": urls.get(e.payload.get("path"))}
        elif e.type == "escalation":
            d["payload"] = {**d["payload"], "screenshot_url": urls.get(e.payload.get("screenshot_path") or "")}
        out.append(d)
    return {"persona": persona.model_dump(mode="json"), "events": out}
