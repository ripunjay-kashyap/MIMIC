"""Run lifecycle: create (cohort_ready) -> start (running) -> aggregating -> completed | failed.

Personas run concurrently in isolated browser contexts. A crashing persona never crashes the run.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.agent.graph import Escalator, PersonaRunContext, run_persona
from app.analysis import analyze
from app.browser.guards import validate_target_url
from app.browser.pool import pool
from app.db.repo import get_repo
from app.models.schemas import CreateRunRequest, PersonaState, RunSummary, SuccessCriteria
from app.orchestrator.event_bus import RunEventBus
from app.personas.cohort import generate_cohort, milestones_for
from app.personas.state_engine import mark_error

log = logging.getLogger(__name__)

PERSONA_TIMEOUT_S = 6 * 60
RUN_TIMEOUT_S = 12 * 60
ACTIVE = ("running", "aggregating")


class RunConflict(Exception):
    pass


class RunNotFound(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunManager:
    def __init__(self) -> None:
        self.buses: dict[str, RunEventBus] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.live_personas: dict[str, dict[str, PersonaState]] = {}
        self.escalator_factory = None  # set by P8: (run_id) -> Escalator | None
        self.synthesizer = None  # set by P9 synthesis: async (goal, personas, findings) -> findings

    # ---------------------------------------------------------------- lifecycle
    async def recover_orphans(self) -> None:
        """Runs still marked active after a restart can never finish: mark them failed."""
        try:
            for row in await get_repo().runs_with_status(list(ACTIVE)):
                if row["id"] not in self.tasks:
                    await get_repo().update_run(row["id"], {"status": "failed", "error": "orphaned by backend restart",
                                                            "completed_at": _now()})
                    log.warning("marked orphaned run %s failed", row["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("orphan recovery failed: %s", e)

    async def create_run(self, req: CreateRunRequest) -> RunSummary:
        if not req.authorized:
            raise ValueError("You must confirm you are authorized to test this target.")
        await validate_target_url(req.target_url)
        run_id = str(uuid.uuid4())
        personas = generate_cohort(req.goal)
        created = _now()
        await get_repo().insert_run({
            "id": run_id, "target_url": req.target_url, "goal": req.goal,
            "success_criteria": req.success_criteria.model_dump() if req.success_criteria else None,
            "status": "cohort_ready", "created_at": created,
        })
        await get_repo().upsert_personas(run_id, personas)
        return RunSummary(run_id=run_id, target_url=req.target_url, goal=req.goal, status="cohort_ready",
                          created_at=created, personas=personas)

    async def start_run(self, run_id: str) -> None:
        row = await get_repo().get_run(run_id)
        if row is None:
            raise RunNotFound(run_id)
        if row["status"] != "cohort_ready":
            raise RunConflict(f"Run is {row['status']}; only a run in cohort_ready can be started.")
        active = [rid for rid, t in self.tasks.items() if not t.done()]
        if active:
            raise RunConflict(f"Another run ({active[0][:8]}…) is still in progress. Try again when it finishes.")
        await get_repo().update_run(run_id, {"status": "running", "started_at": _now()})
        bus = RunEventBus(run_id)
        self.buses[run_id] = bus
        self.tasks[run_id] = asyncio.create_task(self._execute(run_id, row, bus))

    async def _execute(self, run_id: str, row: dict, bus: RunEventBus) -> None:
        repo = get_repo()
        try:
            await bus.emit("run_status", None, None, None, {"status": "running"})
            personas = await repo.get_personas(run_id)
            self.live_personas[run_id] = {p.persona_id: p for p in personas}
            criteria = SuccessCriteria.model_validate(row["success_criteria"]) if row.get("success_criteria") else None
            milestones = milestones_for(row["target_url"])
            escalate: Escalator | None = self.escalator_factory(run_id) if self.escalator_factory else None

            async def one(p: PersonaState) -> PersonaState:
                try:
                    async with pool.session(p.persona_id, row["target_url"], device=p.device) as session:
                        ctx = PersonaRunContext(run_id=run_id, persona=p, session=session, sink=bus,
                                                success_criteria=criteria, milestones=milestones, escalate=escalate)
                        final = await asyncio.wait_for(run_persona(ctx), timeout=PERSONA_TIMEOUT_S)
                except asyncio.TimeoutError:
                    final = mark_error(p, f"persona timed out after {PERSONA_TIMEOUT_S}s")
                    await bus.emit("persona_finished", p.persona_id, None, None,
                                   {"status": "error", "reason": final.termination_reason, "state": final.model_dump()})
                except Exception as e:  # noqa: BLE001 - e.g. browser context failed to open
                    log.exception("persona %s failed outside the agent loop", p.persona_id)
                    final = mark_error(p, f"{type(e).__name__}: {e}")
                    await bus.emit("persona_finished", p.persona_id, None, None,
                                   {"status": "error", "reason": final.termination_reason, "state": final.model_dump()})
                self.live_personas[run_id][p.persona_id] = final
                return final

            finals = await asyncio.wait_for(asyncio.gather(*(one(p) for p in personas)), timeout=RUN_TIMEOUT_S)
            await repo.upsert_personas(run_id, finals)

            await repo.update_run(run_id, {"status": "aggregating"})
            await bus.emit("run_status", None, None, None, {"status": "aggregating"})
            await bus.flush()
            metrics, findings = analyze(run_id, finals, list(bus.history))
            if self.synthesizer:
                try:
                    findings = await self.synthesizer(row["goal"], finals, findings)
                except Exception as e:  # noqa: BLE001 - templates remain
                    log.warning("synthesis failed, keeping template interpretations: %s", e)
            await repo.insert_findings(findings)
            for f in findings:
                await bus.emit("finding", None, None, None, {"finding": f.model_dump(mode="json")})
            await repo.update_run(run_id, {"status": "completed", "metrics": metrics, "completed_at": _now()})
            await bus.emit("run_status", None, None, None, {"status": "completed"})
        except Exception as e:  # noqa: BLE001
            log.exception("run %s failed", run_id)
            try:
                await repo.update_run(run_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"[:500],
                                               "completed_at": _now()})
                await bus.emit("run_status", None, None, None, {"status": "failed"})
            except Exception:  # noqa: BLE001
                pass
        finally:
            await bus.close()
            self.live_personas.pop(run_id, None)

    # ---------------------------------------------------------------- queries
    async def get_run(self, run_id: str) -> RunSummary:
        row = await get_repo().get_run(run_id)
        if row is None:
            raise RunNotFound(run_id)
        personas = await get_repo().get_personas(run_id)
        live = dict(self.live_personas.get(run_id) or {})
        bus = self.buses.get(run_id)
        if bus is not None and not bus.closed:
            for ev in bus.history:  # latest state per persona, mid-run
                st = ev.payload.get("state") or ev.payload.get("persona")
                if st and ev.persona_id:
                    live[ev.persona_id] = PersonaState.model_validate(st)
        if live:
            personas = [live.get(p.persona_id, p) for p in personas]
        order = [p.persona_id for p in generate_cohort("x")]
        personas.sort(key=lambda p: order.index(p.persona_id) if p.persona_id in order else 99)
        return RunSummary(run_id=row["id"], target_url=row["target_url"], goal=row["goal"], status=row["status"],
                          created_at=row["created_at"], personas=personas, metrics=row.get("metrics"),
                          error=row.get("error"))

    def is_active(self, run_id: str) -> bool:
        t = self.tasks.get(run_id)
        return t is not None and not t.done()

    async def wait(self, run_id: str) -> None:
        t = self.tasks.get(run_id)
        if t:
            await t


manager = RunManager()
