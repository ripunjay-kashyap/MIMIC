"""Event sinks. MemorySink is for tests/scripts; the Supabase-backed sink lives in orchestrator/event_bus.py."""

import itertools
from pathlib import Path
from typing import Any

from app.models.schemas import RunEvent


class MemorySink:
    def __init__(self, run_id: str, screenshot_dir: Path | None = None, echo: bool = False) -> None:
        self.run_id = run_id
        self.events: list[RunEvent] = []
        self.screenshot_dir = screenshot_dir
        self.echo = echo
        self._seq = itertools.count(1)

    async def emit(self, type: str, persona_id: str | None, step: int | None, url: str | None,
                   payload: dict[str, Any]) -> int:
        ev = RunEvent(run_id=self.run_id, seq=next(self._seq), persona_id=persona_id, type=type, step=step,
                      url=url, payload=payload)
        self.events.append(ev)
        if self.echo:
            print(_line(ev))
        return ev.seq

    async def screenshot(self, persona_id: str, step: int, reason: str, data: bytes) -> str | None:
        path = f"{self.run_id}/{persona_id}/{step:03d}_{reason}.jpg"
        if self.screenshot_dir:
            f = self.screenshot_dir / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        return path

    def of(self, persona_id: str, type: str | None = None) -> list[RunEvent]:
        return [e for e in self.events if e.persona_id == persona_id and (type is None or e.type == type)]


def _line(ev: RunEvent) -> str:
    p = ev.payload
    if ev.type == "decision":
        a = p["action"]
        extra = f" '{p.get('element_label')}'" if p.get("element_label") else ""
        text = f" text={a.get('text')!r}" if a.get("text") is not None else ""
        return f"[{ev.persona_id} #{ev.step}] DECIDE {a['action']}{extra}{text} ({p['model']}{', ' + ','.join(p['policy_tags']) if p['policy_tags'] else ''}) — {a['thought']}"
    if ev.type == "action_result":
        r = p["result"]
        return f"[{ev.persona_id} #{ev.step}]   -> {'ok' if r['ok'] else 'FAIL ' + str(r['error'])} {r['url_after']} ({r['duration_ms']}ms)"
    if ev.type == "state_update":
        s = p["state"]
        return f"[{ev.persona_id} #{ev.step}]   state frus={s['current_frustration']:.2f} prog={s['progress']:.2f} signals={p['signals']}"
    if ev.type == "persona_finished":
        return f"[{ev.persona_id}] FINISHED {p['status']} — {p['reason']}"
    if ev.type == "observation":
        return f"[{ev.persona_id} #{ev.step}] SEE {p['summary']}"
    return f"[{ev.persona_id}] {ev.type}"
