"""Single shared Chromium process; one BrowserContext per persona (plan Phase 3)."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, Playwright, async_playwright

from app.browser.session import PersonaSession
from app.config import get_settings

log = logging.getLogger(__name__)


class BrowserPool:
    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(get_settings().max_concurrent_personas)

    @property
    def ready(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def start(self) -> None:
        async with self._lock:
            if self.ready:
                return
            settings = get_settings()
            args = ["--disable-dev-shm-usage"]
            if os.environ.get("IN_CONTAINER") == "1":
                args.append("--no-sandbox")
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=settings.browser_headless, args=args)
            log.info("chromium launched: %s", self._browser.version)

    async def stop(self) -> None:
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._pw:
                await self._pw.stop()
                self._pw = None

    @property
    def browser(self) -> Browser:
        if not self.ready:
            raise RuntimeError("browser not ready")
        return self._browser  # type: ignore[return-value]

    @asynccontextmanager
    async def session(self, persona_id: str, target_url: str, device: str = "desktop") -> AsyncIterator[PersonaSession]:
        """Isolated BrowserContext for one persona; bounded by MAX_CONCURRENT_PERSONAS; always closed."""
        async with self.semaphore:
            if not self.ready:
                await self.start()
            s = await PersonaSession.create(self.browser, self._pw.devices, persona_id, target_url, device)
            try:
                yield s
            finally:
                await s.close()


pool = BrowserPool()
