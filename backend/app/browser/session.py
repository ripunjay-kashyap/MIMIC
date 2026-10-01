"""One isolated browser session (BrowserContext + Page) per persona."""

import logging
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Route
from playwright.async_api import Error as PlaywrightError

from app.browser.guards import host_of, is_demo_target
from app.browser.observe import Observation, observe

log = logging.getLogger(__name__)

DESKTOP = {"viewport": {"width": 1280, "height": 800}}
MOBILE_DEVICE = "Pixel 7"  # Android: the common case for Bharat users


class PersonaSession:
    def __init__(self, persona_id: str, target_url: str, context: BrowserContext, page: Page) -> None:
        self.persona_id = persona_id
        self.target_url = target_url
        self.target_host = host_of(target_url)
        self.demo_target = is_demo_target(target_url)
        self.context = context
        self.page = page
        self.dialogs: list[str] = []
        self.blocked_navigations: list[str] = []
        self.last_observation: Observation | None = None

    @classmethod
    async def create(cls, browser: Browser, playwright_devices: dict, persona_id: str, target_url: str,
                     device: str = "desktop") -> "PersonaSession":
        opts = dict(playwright_devices[MOBILE_DEVICE]) if device == "mobile" else dict(DESKTOP)
        context = await browser.new_context(**opts, locale="en-IN", timezone_id="Asia/Kolkata")
        context.set_default_timeout(5000)
        page = await context.new_page()
        session = cls(persona_id, target_url, context, page)
        await context.route("**/*", session._route)
        page.on("dialog", session._on_dialog)
        return session

    async def _route(self, route: Route) -> None:
        req = route.request
        # Only top-level document navigations are fenced to the target host; subresources (CDNs) are allowed.
        if req.is_navigation_request() and req.frame == self.page.main_frame:
            host = (urlparse(req.url).hostname or "").lower()
            if req.url.startswith(("http://", "https://")) and host != self.target_host:
                self.blocked_navigations.append(req.url)
                await route.abort("aborted")  # "aborted" keeps the current page; other codes show chrome-error://
                return
        await route.continue_()

    async def _on_dialog(self, dialog) -> None:
        self.dialogs.append(f"{dialog.type}: {dialog.message}"[:200])
        await dialog.dismiss()

    async def goto_start(self) -> None:
        await self.page.goto(self.target_url, wait_until="domcontentloaded", timeout=20000)

    async def observe(self) -> Observation:
        # Pages may navigate on their own (delayed redirects); retry if the context is torn down mid-evaluate.
        for attempt in range(4):
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                self.last_observation = await observe(self.page, demo_target=self.demo_target)
                return self.last_observation
            except PlaywrightError:
                if attempt == 3:
                    raise
                await self.page.wait_for_timeout(500)
        raise RuntimeError("unreachable")

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(type="jpeg", quality=60, full_page=False)

    async def close(self) -> None:
        try:
            await self.context.close()
        except Exception as e:  # noqa: BLE001
            log.warning("context close failed for %s: %s", self.persona_id, e)
