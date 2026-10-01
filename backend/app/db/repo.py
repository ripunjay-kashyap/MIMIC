"""Persistence: Supabase in production, in-memory for tests/dev without Supabase. Same interface."""

import logging
from datetime import datetime
from typing import Any, Protocol

from app.config import get_settings
from app.db.client import get_db
from app.models.schemas import Finding, PersonaState, RunEvent

log = logging.getLogger(__name__)

BUCKET = "screenshots"


class Repo(Protocol):
    async def insert_run(self, row: dict[str, Any]) -> None: ...
    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None: ...
    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    async def runs_with_status(self, statuses: list[str]) -> list[dict[str, Any]]: ...
    async def upsert_personas(self, run_id: str, personas: list[PersonaState]) -> None: ...
    async def get_personas(self, run_id: str) -> list[PersonaState]: ...
    async def insert_events(self, events: list[RunEvent]) -> None: ...
    async def get_events(self, run_id: str, after_seq: int = 0, persona_id: str | None = None) -> list[RunEvent]: ...
    async def insert_findings(self, findings: list[Finding]) -> None: ...
    async def get_findings(self, run_id: str) -> list[Finding]: ...
    async def upload_screenshot(self, path: str, data: bytes) -> None: ...
    async def signed_urls(self, paths: list[str]) -> dict[str, str]: ...


def _persona_row(run_id: str, p: PersonaState) -> dict[str, Any]:
    state = p.model_dump(mode="json")
    config = {k: state[k] for k in ("persona_type", "label", "blurb", "digital_literacy", "patience", "risk_tolerance",
                                    "reading_tolerance", "exploration", "device", "llm_model", "max_actions",
                                    "max_failed_attempts", "abandon_frustration")}
    outcome = p.task_status if p.task_status not in ("pending", "active") else None
    return {"run_id": run_id, "id": p.persona_id, "persona_type": p.persona_type, "config": config, "state": state,
            "outcome": outcome}


def _event_row(e: RunEvent) -> dict[str, Any]:
    return e.model_dump(mode="json") | {"run_id": e.run_id}


class SupabaseRepo:
    async def _db(self):
        db = await get_db()
        if db is None:
            raise RuntimeError("Supabase not configured")
        return db

    async def insert_run(self, row):
        await (await self._db()).table("runs").insert(row).execute()

    async def update_run(self, run_id, fields):
        await (await self._db()).table("runs").update(fields).eq("id", run_id).execute()

    async def get_run(self, run_id):
        res = await (await self._db()).table("runs").select("*").eq("id", run_id).limit(1).execute()
        return res.data[0] if res.data else None

    async def runs_with_status(self, statuses):
        res = await (await self._db()).table("runs").select("id,status").in_("status", statuses).execute()
        return res.data

    async def upsert_personas(self, run_id, personas):
        if personas:
            await (await self._db()).table("personas").upsert([_persona_row(run_id, p) for p in personas]).execute()

    async def get_personas(self, run_id):
        res = await (await self._db()).table("personas").select("state").eq("run_id", run_id).execute()
        return [PersonaState.model_validate(r["state"]) for r in res.data]

    async def insert_events(self, events):
        if events:
            await (await self._db()).table("events").upsert([_event_row(e) for e in events]).execute()

    async def get_events(self, run_id, after_seq=0, persona_id=None):
        db = await self._db()
        out: list[RunEvent] = []
        page = 1000
        while True:
            q = db.table("events").select("*").eq("run_id", run_id).gt("seq", after_seq)
            if persona_id:
                q = q.eq("persona_id", persona_id)
            res = await q.order("seq").limit(page).execute()
            out.extend(RunEvent.model_validate(r) for r in res.data)
            if len(res.data) < page:
                return out
            after_seq = res.data[-1]["seq"]

    async def insert_findings(self, findings):
        if findings:
            rows = [f.model_dump(mode="json", exclude={"id"}) for f in findings]
            await (await self._db()).table("findings").insert(rows).execute()

    async def get_findings(self, run_id):
        res = await (await self._db()).table("findings").select("*").eq("run_id", run_id).execute()
        return [Finding.model_validate(r) for r in res.data]

    async def upload_screenshot(self, path, data):
        await (await self._db()).storage.from_(BUCKET).upload(path, data, {"content-type": "image/jpeg", "upsert": "true"})

    async def signed_urls(self, paths):
        if not paths:
            return {}
        res = await (await self._db()).storage.from_(BUCKET).create_signed_urls(paths, 3600)
        out = {}
        for item in res:
            url = item.get("signedURL") or item.get("signedUrl")
            if url and item.get("path"):
                out[item["path"]] = url
        return out


class MemoryRepo:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.personas: dict[str, dict[str, PersonaState]] = {}
        self.events: dict[str, dict[int, RunEvent]] = {}
        self.findings: dict[str, list[Finding]] = {}
        self.screenshots: dict[str, bytes] = {}

    async def insert_run(self, row):
        self.runs[row["id"]] = dict(row)

    async def update_run(self, run_id, fields):
        self.runs[run_id].update({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()})

    async def get_run(self, run_id):
        return self.runs.get(run_id)

    async def runs_with_status(self, statuses):
        return [{"id": k, "status": v["status"]} for k, v in self.runs.items() if v["status"] in statuses]

    async def upsert_personas(self, run_id, personas):
        bucket = self.personas.setdefault(run_id, {})
        for p in personas:
            bucket[p.persona_id] = p.model_copy(deep=True)

    async def get_personas(self, run_id):
        return list(self.personas.get(run_id, {}).values())

    async def insert_events(self, events):
        for e in events:
            self.events.setdefault(e.run_id, {})[e.seq] = e

    async def get_events(self, run_id, after_seq=0, persona_id=None):
        evs = sorted(self.events.get(run_id, {}).values(), key=lambda e: e.seq)
        return [e for e in evs if e.seq > after_seq and (persona_id is None or e.persona_id == persona_id)]

    async def insert_findings(self, findings):
        for f in findings:
            self.findings.setdefault(f.run_id, []).append(f)

    async def get_findings(self, run_id):
        return list(self.findings.get(run_id, []))

    async def upload_screenshot(self, path, data):
        self.screenshots[path] = data

    async def signed_urls(self, paths):
        return {}


_repo: Repo | None = None


def get_repo() -> Repo:
    global _repo
    if _repo is None:
        _repo = SupabaseRepo() if get_settings().supabase_enabled else MemoryRepo()
        log.info("using %s", type(_repo).__name__)
    return _repo


def set_repo(repo: Repo | None) -> None:
    """Tests inject a MemoryRepo."""
    global _repo
    _repo = repo
