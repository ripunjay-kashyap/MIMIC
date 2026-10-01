"""In-memory sliding-window limits for run creation/start (single always-on container, so memory is enough).

Protects LLM quota on the public URL. Limits are per client IP plus a global cap.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings


class SlidingWindow:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_s: float) -> tuple[bool, int]:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return False, int(window_s - (now - q[0])) + 1
        q.append(now)
        return True, 0


_window = SlidingWindow()


def client_ip(request: Request) -> str:
    # Behind Modal's proxy the client is the first X-Forwarded-For entry.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_runs(kind: str):
    async def dep(request: Request) -> None:
        s = get_settings()
        ip = client_ip(request)
        per_ip = s.runs_per_ip_per_hour if kind == "start" else s.runs_per_ip_per_hour * 3
        ok, retry = _window.allow(f"{kind}:{ip}", per_ip, 3600)
        if ok:
            ok, retry = _window.allow(f"{kind}:global", s.runs_global_per_hour * (1 if kind == "start" else 3), 3600)
        if not ok:
            raise HTTPException(status_code=429, detail=f"Rate limit reached for {kind}s. Try again in {retry // 60 + 1} min.",
                                headers={"Retry-After": str(retry)})

    return dep


def reset() -> None:
    _window.hits.clear()
