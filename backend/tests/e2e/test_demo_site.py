"""Browser checks for the deliberately flawed, deterministic SurakshaSetu demo."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo_site"
DETAILS = {"Full name": "Asha Verma", "Mobile number": "9876543210", "PIN code": "560001", "Date of birth": "15/08/1990"}


@pytest.fixture(scope="module")
def demo_url():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(DEMO_DIR)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            if process.poll() is not None:
                pytest.fail("Demo HTTP server exited before becoming ready")
            try:
                with urlopen(url, timeout=0.5) as response:
                    assert response.status == 200
                break
            except (URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    pytest.fail("Demo HTTP server did not become ready")
                time.sleep(0.05)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def select_basic(page, demo_url):
    page.goto(demo_url + "/index.html")
    page.get_by_role("link", name="Get a Quote", exact=True).click()
    page.locator(".plan-card").filter(has=page.get_by_role("heading", name="Basic", exact=True)).get_by_role("button", name="Select", exact=True).click()
    expect(page).to_have_url(re.compile(r"/details\.html$"))


def fill_details(page, **overrides):
    for label, value in (DETAILS | overrides).items():
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Continue", exact=True).click()


def reach_verify(page, demo_url):
    select_basic(page, demo_url)
    fill_details(page)
    expect(page).to_have_url(re.compile(r"/verify\.html$"))


def reach_pay(page, demo_url):
    reach_verify(page, demo_url)
    page.get_by_role("button", name="Send OTP", exact=True).click()
    expect(page.get_by_label("Enter OTP", exact=True)).to_be_visible(timeout=5000)
    page.get_by_label("Enter OTP", exact=True).fill("123456")
    page.get_by_role("button", name="Verify", exact=True).click()
    expect(page.get_by_role("heading", name="Confirm your details")).to_be_visible()
    for key, value in zip(("name", "mobile", "pin", "dob"), DETAILS.values()):
        expect(page.locator(f'[data-detail="{key}"]')).to_have_text(value)
    expect(page.locator("[data-plan-name]")).to_have_text("Basic")
    page.get_by_role("button", name="Confirm & Continue", exact=True).click()
    expect(page.get_by_label("Auto-renew and share my data with partners")).to_be_checked()
    expect(page.get_by_text("Total payable: ₹4,812 + applicable charges*", exact=True)).to_be_visible()


def finish_happy_path(page, demo_url):
    reach_pay(page, demo_url)
    page.get_by_role("button", name="Proceed", exact=True).click()
    expect(page.get_by_test_id("policy-confirmed")).to_be_visible()
    expect(page.get_by_test_id("payment-line")).to_have_text(["Payment 1: ₹4,812 — successful"])
    return page.locator("body").inner_text()


def test_happy_path(page, demo_url):
    finish_happy_path(page, demo_url)
    expect(page.get_by_text("SS-2026-000123", exact=True)).to_be_visible()
    assert page.evaluate("JSON.parse(sessionStorage.getItem('ss_payments'))") == [{"n": 1, "amount": 4812}]


def test_learn_is_dead_end(page, demo_url):
    page.goto(demo_url + "/learn.html")
    expect(page.locator("a[href]")).to_have_count(0)
    expect(page.locator("button")).to_have_count(0)
    expect(page.locator("header")).to_have_count(0)
    assert page.locator("main p").count() >= 6


def test_short_mobile_is_accepted_and_bad_pin_is_generic(page, demo_url):
    select_basic(page, demo_url)
    fill_details(page, **{"Mobile number": "12345", "PIN code": "12"})
    expect(page.get_by_role("alert")).to_have_text("Invalid input")
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/details\.html$"))
    page.get_by_label("PIN code", exact=True).fill("560001")
    page.get_by_role("button", name="Continue", exact=True).click()
    expect(page).to_have_url(re.compile(r"/verify\.html$"))


def test_otp_delay(page, demo_url):
    reach_verify(page, demo_url)
    before = page.locator("body").inner_text()
    page.get_by_role("button", name="Send OTP", exact=True).click()
    page.wait_for_timeout(1000)
    expect(page.get_by_label("Enter OTP", exact=True)).not_to_be_visible()
    expect(page.get_by_role("button", name="Send OTP", exact=True)).to_be_enabled()
    assert page.locator("body").inner_text() == before
    page.wait_for_timeout(2500)
    expect(page.get_by_label("Enter OTP", exact=True)).to_be_visible()
    expect(page.get_by_role("status")).to_have_text("OTP sent to +91 ••••••10")


def test_double_submit_creates_two_payments(page, demo_url):
    reach_pay(page, demo_url)
    page.get_by_role("button", name="Proceed", exact=True).dblclick()
    expect(page.get_by_role("button", name="Proceed", exact=True)).to_be_enabled()
    expect(page.get_by_test_id("policy-confirmed")).to_be_visible()
    expect(page.get_by_test_id("payment-line")).to_have_text([
        "Payment 1: ₹4,812 — successful", "Payment 2: ₹4,812 — successful",
    ])
    assert page.evaluate("JSON.parse(sessionStorage.getItem('ss_payments'))") == [
        {"n": 1, "amount": 4812}, {"n": 2, "amount": 4812},
    ]


def test_deterministic_confirmation(browser, demo_url):
    confirmations = []
    for _ in range(2):
        context = browser.new_context()
        try:
            confirmations.append(finish_happy_path(context.new_page(), demo_url))
        finally:
            context.close()
    assert confirmations[0] == confirmations[1]


def test_seeded_issue_ground_truth():
    issues = json.loads((DEMO_DIR / "SEEDED_ISSUES.json").read_text())
    allowed = {"stuck_on_page", "backtrack", "repeated_failure", "invalid_input_accepted", "abandon_point", "risk_hesitation", "long_path", "dead_end", "duplicate_submit_effect", "delayed_feedback", "route_divergence"}
    assert len(issues) == 13
    assert {issue["id"] for issue in issues} == {f"D{n}" for n in range(1, 13)} | {"D2b"}
    for issue in issues:
        assert issue["expected_signals"] and set(issue["expected_signals"]) <= allowed
        assert issue["detectable_by"] in {"text", "behavior", "visual"}
        assert (DEMO_DIR / issue["page"]).is_file()
        assert issue["description"] and issue["category"]
    assert [issue["id"] for issue in issues if issue["detectable_by"] == "visual"] == ["D12"]


@pytest.mark.parametrize("file", ["details", "verify", "review", "pay", "confirmed"])
def test_direct_access_without_session(page, demo_url, file):
    page.goto(f"{demo_url}/{file}.html")
    expect(page.get_by_role("heading", name="Session expired. Start again", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Start again", exact=True)).to_have_attribute("href", "index.html")
    expect(page.get_by_test_id("policy-confirmed")).to_have_count(0)


@pytest.mark.parametrize("dob", ["31/02/1990", "15/13/1990", "1990-08-15", "15/08/2020", "15/08/2090"])
def test_invalid_or_underage_dob(page, demo_url, dob):
    select_basic(page, demo_url)
    fill_details(page, **{"Date of birth": dob})
    expect(page.get_by_role("alert")).to_have_text("Invalid input")
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/details\.html$"))


def test_otp_restart_and_wrong_code(page, demo_url):
    reach_verify(page, demo_url)
    page.get_by_role("button", name="Send OTP", exact=True).click()
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Send OTP", exact=True).click()
    page.wait_for_timeout(1500)
    expect(page.get_by_label("Enter OTP", exact=True)).not_to_be_visible()
    expect(page.get_by_label("Enter OTP", exact=True)).to_be_visible(timeout=2500)
    page.get_by_label("Enter OTP", exact=True).fill("000000")
    page.get_by_role("button", name="Verify", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("Something went wrong")
    expect(page.get_by_role("alert")).to_be_visible()


def test_explore_advisor_dead_end(page, demo_url):
    page.goto(demo_url + "/explore.html")
    expect(page.get_by_role("button")).to_have_count(1)
    page.get_by_role("button", name="Talk to an advisor", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("All our advisors are busy. Please try later.")
    expect(page.get_by_role("navigation").get_by_role("link")).to_have_count(4)


def test_mobile_ctas_below_fold(page, demo_url):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(demo_url + "/index.html")
    assert page.locator(".hero-image").bounding_box()["height"] >= 844
    for label in ("Get Started", "Get a Quote", "Explore Plans"):
        assert page.get_by_role("link", name=label, exact=True).bounding_box()["y"] >= 844


def test_all_pages_have_local_assets_and_noindex(page, demo_url):
    external = []
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(demo_url + "/") else None)
    for file in sorted(DEMO_DIR.glob("*.html")):
        page.goto(f"{demo_url}/{file.name}")
        expect(page.locator('meta[name="robots"]')).to_have_attribute("content", "noindex")
        if file.name != "learn.html":
            assert page.get_by_role("navigation").get_by_role("link").all_text_contents() == ["Home", "Plans", "Claims", "Help"]
        assert page.locator('[href^="/"], [src^="/"], [href^="http"], [src^="http"]').count() == 0
    assert external == []
