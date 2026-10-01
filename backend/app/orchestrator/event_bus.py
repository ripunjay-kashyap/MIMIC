"""Per-run event bus: monotonic seq, live fan-out to SSE subscribers, batched persistence, screenshot uploads.

Implements the agent's EventSink protocol. Persistence failures are logged, never raised into agents.
"""

import asyncio
import itertools
import logging
from typing import Any

from app.db.repo import get_repo
from app.models.schemas import PersonaState, RunEvent

log = logging.getLogger(__name__)

FLUSH_INTERVAL_S = 0.5
FLUSH_BATCH = 20
SUBSCRIBER_QUEUE = 1000


class RunEventBus:
    def __init__(self, run_id: str, start_seq: int = 0) -> None:
        self.run_id = run_id
        self._seq = itertools.count(start_seq + 1)
        self.history: list[RunEvent] = []  # full in-memory history for live replay
        self._pending: list[RunEvent] = []
        self._dirty_personas: dict[str, PersonaState] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._closed = False
        self._uploads: set[asyncio.Task] = set()
        self._flusher = asyncio.create_task(self._flush_loop())
        self._flush_lock = asyncio.Lock()

    # ---------------------------------------------------------------- EventSink
    async def emit(self, type: str, persona_id: str | None, step: int | None, url: str | None,
                   payload: dict[str, Any]) -> int:
        ev = RunEvent(run_id=self.run_id, seq=next(self._seq), persona_id=persona_id, type=type, step=step,
                      url=url, payload=payload)
        self.history.append(ev)
        self._pending.append(ev)
        if type in ("state_update", "persona_finished", "persona_started"):
            state = payload.get("state") or payload.get("persona")
            if state:
                self._dirty_personas[state["persona_id"]] = PersonaState.model_validate(state)
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                # Slow client: drop it; the SSE handler notices and closes, the browser reconnects with Last-Event-ID.
                log.warning("dropping slow SSE subscriber on run %s", self.run_id)
                self._subscribers.discard(q)
        if len(self._pending) >= FLUSH_BATCH:
            asyncio.create_task(self.flush())
        return ev.seq

    async def screenshot(self, persona_id: str, step: int, reason: str, data: bytes) -> str | None:
        path = f"{self.run_id}/{persona_id}/{step:03d}_{reason}.jpg"
        task = asyncio.create_task(self._upload(path, data))
        self._uploads.add(task)
        task.add_done_callback(self._uploads.discard)
        return path

    async def _upload(self, path: str, data: bytes) -> None:
        try:
            await get_repo().upload_screenshot(path, data)
        except Exception as e:  # noqa: BLE001
            log.warning("screenshot upload failed %s: %s", path, e)

    # ---------------------------------------------------------------- persistence
    async def flush(self) -> None:
        async with self._flush_lock:
            events, self._pending = self._pending, []
            personas, self._dirty_personas = list(self._dirty_personas.values()), {}
            repo = get_repo()
            try:
                await repo.insert_events(events)
            except Exception as e:  # noqa: BLE001
                log.warning("event flush failed (%d events), will retry: %s", len(events), e)
                self._pending = events + self._pending
            try:
                await repo.upsert_personas(self.run_id, personas)
            except Exception as e:  # noqa: BLE001
                log.warning("persona flush failed: %s", e)
                for p in personas:
                    self._dirty_personas.setdefault(p.persona_id, p)

    async def _flush_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            if self._pending or self._dirty_personas:
                await self.flush()

    async def close(self) -> None:
        """Flush everything, wait for uploads, end all live subscriptions."""
        self._closed = True
        self._flusher.cancel()
        if self._uploads:
            await asyncio.gather(*self._uploads, return_exceptions=True)
        for _ in range(3):
            await self.flush()
            if not self._pending:
                break
            await asyncio.sleep(0.5)
        for q in list(self._subscribers):
            q.put_nowait(None)
        self._subscribers.clear()

    # ---------------------------------------------------------------- live subscription
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE)
        if self._closed:
            q.put_nowait(None)
        else:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def is_subscribed(self, q: asyncio.Queue) -> bool:
        return q in self._subscribers

    @property
    def closed(self) -> bool:
        return self._closed
