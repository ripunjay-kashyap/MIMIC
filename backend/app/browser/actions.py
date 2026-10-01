"""Execute an AgentAction against a PersonaSession. Never raises for agent mistakes: returns ActionResult(ok=False)."""

import hashlib
import time

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.browser.session import PersonaSession
from app.models.schemas import ActionResult, AgentAction

ACTION_TIMEOUT_MS = 5000
SETTLE_MS = 300
WAIT_MS = 2000

_SIG_JS = "() => location.href + '|' + (document.body ? document.body.innerText.length + ':' + document.body.innerText.slice(0, 2000) : '')"


async def _signature(session: PersonaSession) -> str:
    try:
        raw = await session.page.evaluate(_SIG_JS)
    except PlaywrightError:
        raw = session.page.url + "|navigating"
    return hashlib.sha1(raw.encode()).hexdigest()


async def _settle(session: PersonaSession) -> None:
    try:
        await session.page.wait_for_load_state("domcontentloaded", timeout=ACTION_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass
    await session.page.wait_for_timeout(SETTLE_MS)


async def execute(session: PersonaSession, action: AgentAction, *, double_click: bool = False) -> ActionResult:
    page = session.page
    url_before = page.url
    sig_before = await _signature(session)
    dialogs_before = len(session.dialogs)
    blocked_before = len(session.blocked_navigations)
    t0 = time.monotonic()
    error: str | None = None

    try:
        if action.action in ("click", "type", "select"):
            obs = session.last_observation
            el = obs.element(action.element_id) if obs else None
            if el is None:
                error = "element_not_found"
            elif el.risky:
                error = "risky_action_blocked"
            else:
                loc = page.locator(f'[data-mimic-id="{action.element_id}"]')
                if await loc.count() == 0:
                    error = "element_not_found"
                elif action.action == "click":
                    if double_click:
                        await loc.dblclick(timeout=ACTION_TIMEOUT_MS)
                    else:
                        await loc.click(timeout=ACTION_TIMEOUT_MS)
                elif action.action == "type":
                    await loc.fill(action.text or "", timeout=ACTION_TIMEOUT_MS)
                else:
                    try:
                        await loc.select_option(label=action.text or "", timeout=ACTION_TIMEOUT_MS)
                    except PlaywrightError:
                        await loc.select_option(value=action.text or "", timeout=ACTION_TIMEOUT_MS)
        elif action.action == "scroll":
            await page.evaluate("() => window.scrollBy(0, Math.round(window.innerHeight * 0.8))")
        elif action.action == "back":
            resp = await page.go_back(wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS)
            if not page.url.startswith(("http://", "https://")):
                # Went back past the start page (about:blank): undo, the persona can't leave the site this way.
                await page.go_forward(wait_until="domcontentloaded", timeout=ACTION_TIMEOUT_MS)
                error = "no_history"
            elif resp is None and page.url == url_before:
                error = "no_history"
        elif action.action == "wait":
            await page.wait_for_timeout(WAIT_MS)
        # done / give_up: no browser operation; the state engine decides what they mean.
    except PlaywrightTimeout:
        error = "timeout"
    except PlaywrightError as e:
        msg = str(e).splitlines()[0]
        error = "offsite_navigation_blocked" if "ERR_ABORTED" in msg and session.blocked_navigations else f"action_failed: {msg[:120]}"

    if action.action not in ("done", "give_up", "wait"):
        await _settle(session)

    if len(session.blocked_navigations) > blocked_before and error is None:
        error = "offsite_navigation_blocked"

    url_after = page.url
    sig_after = await _signature(session)
    return ActionResult(
        ok=error is None,
        error=error,
        url_before=url_before,
        url_after=url_after,
        navigated=url_after != url_before,
        page_changed=sig_after != sig_before,
        dialogs=session.dialogs[dialogs_before:],
        duration_ms=int((time.monotonic() - t0) * 1000),
    )
