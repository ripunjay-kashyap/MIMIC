"""Gate 3: observation quality, actions, isolation, guards, resource sanity. No LLM."""

import asyncio
import os
import subprocess

import pytest

from app.browser.actions import execute
from app.browser.guards import TargetRejected, validate_target_url
from app.browser.observe import estimate_tokens
from app.config import get_settings
from app.models.schemas import AgentAction


def by_label(obs, label):
    el = next((e for e in obs.elements if e.label == label), None)
    assert el is not None, f"{label!r} not in {[e.label for e in obs.elements]}"
    return el.id


def click(obs, label):
    return AgentAction(action="click", element_id=by_label(obs, label))


def type_(obs, label, text):
    return AgentAction(action="type", element_id=by_label(obs, label), text=text)


async def walk_to(session, base, page_name):
    """Drive a session via actions to a given page of the happy path."""
    await session.goto_start()
    steps = {
        "plans": [("click", "Get a Quote")],
        "details": [("click", "Get a Quote"), ("click", "Select")],
    }
    for kind, label in steps[page_name]:
        obs = await session.observe()
        r = await execute(session, click(obs, label))
        assert r.ok, r


# ---------------------------------------------------------------- observation

PAGES_AND_NEXT_STEP = {
    "index.html": "Get a Quote",
    "plans.html": "Select",
    "explore.html": "Talk to an advisor",
    "claims.html": "Home",
    "help.html": "Home",
}


@pytest.mark.parametrize("page_name,expected", PAGES_AND_NEXT_STEP.items())
async def test_observation_contains_next_step_and_is_compact(pool, demo_site_url, page_name, expected):
    async with pool.session("p", demo_site_url + page_name) as s:
        await s.goto_start()
        obs = await s.observe()
        assert any(e.label == expected for e in obs.elements)
        prompt = obs.to_prompt()
        assert estimate_tokens(prompt) <= 1000, estimate_tokens(prompt)
        assert obs.page_hash


async def test_learn_page_has_no_elements(pool, demo_site_url):
    async with pool.session("p", demo_site_url + "learn.html") as s:
        await s.goto_start()
        obs = await s.observe()
        assert obs.elements == []
        assert "(no interactive elements)" in obs.to_prompt()
        assert "…(more text below)" in obs.to_prompt()  # long article is truncated


async def test_form_elements_render_labels_values_and_checkbox(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await walk_to(s, demo_site_url, "details")
        obs = await s.observe()
        rendered = obs.to_prompt()
        assert 'input[tel] "Mobile number" value=""' in rendered
        assert 'input[text] "Date of birth" value=""' in rendered


async def test_mobile_device_marks_ctas_below_fold(pool, demo_site_url):
    async with pool.session("p", demo_site_url, device="mobile") as s:
        await s.goto_start()
        obs = await s.observe()
        cta = next(e for e in obs.elements if e.label == "Get a Quote")
        assert cta.below_fold, "seeded mobile layout defect D12 should push CTAs below the fold"


# ---------------------------------------------------------------- actions

async def test_click_type_back_scroll_wait(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await walk_to(s, demo_site_url, "details")
        obs = await s.observe()
        assert s.page.url.endswith("details.html")

        r = await execute(s, type_(obs, "Mobile number", "9876543210"))
        assert r.ok and not r.navigated
        assert await s.page.input_value("#mobile") == "9876543210"

        r = await execute(s, AgentAction(action="scroll"))
        assert r.ok
        r = await execute(s, AgentAction(action="wait"))
        assert r.ok and r.duration_ms >= 1900

        r = await execute(s, AgentAction(action="back"))
        assert r.ok and r.navigated and r.url_after.endswith("plans.html")


async def test_generic_error_is_observed_as_page_message(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await walk_to(s, demo_site_url, "details")
        obs = await s.observe()
        r = await execute(s, click(obs, "Continue"))
        assert r.ok and not r.navigated and r.page_changed
        obs = await s.observe()
        assert "Invalid input" in obs.alerts


async def test_stale_or_bogus_element_returns_failure_not_exception(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        await s.observe()
        r = await execute(s, AgentAction(action="click", element_id=999))
        assert not r.ok and r.error == "element_not_found"


async def test_back_with_no_history(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        r = await execute(s, AgentAction(action="back"))
        assert not r.ok and r.error == "no_history"


async def test_double_click_creates_duplicate_payment(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        # Seed the session state directly (this test is about dblclick, not the flow).
        await s.page.evaluate("""() => {
          sessionStorage.setItem('ss_plan', JSON.stringify('Basic'));
          sessionStorage.setItem('ss_details', JSON.stringify({name:'A',mobile:'9876543210',pin:'560001',dob:'15/08/1990'}));
          sessionStorage.setItem('ss_verified', 'true');
          sessionStorage.setItem('ss_payments', '[]');
        }""")
        await s.page.goto(demo_site_url + "pay.html")
        obs = await s.observe()
        r = await execute(s, click(obs, "Proceed"), double_click=True)
        assert r.ok
        # Two clicks -> two delayed redirects; wait for the second payment line rather than a URL.
        await s.page.wait_for_selector("[data-testid=payment-line] >> nth=1", timeout=8000)
        assert await s.page.locator("[data-testid=payment-line]").count() == 2
        obs = await s.observe()  # must not crash even if a redirect is still settling
        assert obs.path.endswith("confirmed.html")


# ---------------------------------------------------------------- isolation

async def test_six_parallel_sessions_are_isolated(pool, demo_site_url):
    names = [f"Persona {i}" for i in range(6)]

    async def fill(i):
        async with pool.session(f"p{i}", demo_site_url) as s:
            await walk_to(s, demo_site_url, "details")
            obs = await s.observe()
            r = await execute(s, type_(obs, "Full name", names[i]))
            assert r.ok
            await asyncio.sleep(0.3)  # let all six fill concurrently
            plan = await s.page.evaluate("() => sessionStorage.getItem('ss_plan')")
            cookies = await s.context.cookies()
            return await s.page.input_value("#full-name"), plan, cookies

    results = await asyncio.gather(*(fill(i) for i in range(6)))
    assert [r[0] for r in results] == names
    assert all(r[1] == '"Basic"' for r in results)
    assert all(r[2] == [] for r in results)

    # A fresh session sees none of it.
    async with pool.session("fresh", demo_site_url + "details.html") as s:
        await s.goto_start()
        assert "Session expired" in await s.page.inner_text("main")


# ---------------------------------------------------------------- guards

async def test_offsite_navigation_is_blocked(pool, demo_site_url):
    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        await s.page.evaluate("""() => {
          const a = document.createElement('a'); a.href = 'https://example.com/'; a.textContent = 'Partner site';
          document.querySelector('main').append(a);
        }""")
        obs = await s.observe()
        r = await execute(s, click(obs, "Partner site"))
        assert not r.ok and r.error == "offsite_navigation_blocked"
        assert s.page.url.startswith(demo_site_url)


async def test_verification_page_detected(pool, demo_site_url):
    from app.browser.guards import detect_verification

    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        assert await detect_verification(s.page) is None
        await s.page.set_content(
            "<title>Just a moment...</title><iframe src='https://challenges.cloudflare.com/x'></iframe>"
        )
        assert await detect_verification(s.page) == "challenge page title"


async def test_risky_actions_blocked_on_non_demo_targets(pool, demo_site_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_target_hosts", [])
    async with pool.session("p", demo_site_url) as s:
        await s.goto_start()
        await s.page.set_content("<button>Pay now</button><button>Continue</button>")
        obs = await s.observe()
        pay = next(e for e in obs.elements if e.label == "Pay now")
        assert pay.risky and "[RISKY: blocked]" in obs.to_prompt()
        r = await execute(s, AgentAction(action="click", element_id=pay.id))
        assert r.error == "risky_action_blocked"


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/", "ftp://example.com"]
)
async def test_ssrf_targets_rejected(url, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_local_targets", False)
    with pytest.raises(TargetRejected):
        await validate_target_url(url)


async def test_public_target_accepted(monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_local_targets", False)
    assert await validate_target_url("https://example.com/") == "https://example.com/"


# ---------------------------------------------------------------- resources

def _chromium_rss_mb() -> float:
    """RSS of this test process's descendants only (not the user's own Chrome)."""
    rows = subprocess.run(["ps", "-eo", "pid,ppid,rss"], capture_output=True, text=True).stdout.splitlines()[1:]
    procs = [tuple(map(int, r.split())) for r in rows]
    tree, frontier = set(), {os.getpid()}
    while frontier:
        frontier = {pid for pid, ppid, _ in procs if ppid in frontier} - tree
        tree |= frontier
    return sum(rss for pid, _, rss in procs if pid in tree) / 1024


async def test_resource_usage_six_contexts(pool, demo_site_url, capsys):
    sessions = []
    ctxs = [pool.session(f"p{i}", demo_site_url) for i in range(6)]
    for c in ctxs:
        sessions.append(await c.__aenter__())
    await asyncio.gather(*(walk_to(s, demo_site_url, "details") for s in sessions))
    peak = _chromium_rss_mb()
    for c in ctxs:
        await c.__aexit__(None, None, None)
    with capsys.disabled():
        print(f"\n[resource] chromium RSS with 6 contexts: {peak:.0f} MB (pid {os.getpid()})")
    assert peak < 3000
