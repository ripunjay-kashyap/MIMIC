import pytest

from app.analysis import detect_signals

from .builders import Journey, cohort


def signals(kind, *journeys):
    states, events = cohort(*journeys)
    return [s for s in detect_signals(states, events) if s.type == kind]


@pytest.mark.parametrize("repeats,expected", [(2, 0), (3, 1), (5, 1)])
def test_stuck_on_page_threshold_and_one_signal_per_run(repeats, expected):
    j = Journey()
    for _ in range(repeats):
        j.step(page_hash="same")
    assert len(signals("stuck_on_page", j)) == expected


def test_stuck_runs_reset_on_hash_or_page_change():
    j = Journey()
    for hash_ in ["a", "a", "a", "b", "a", "a", "a"]:
        j.step(page_hash=hash_)
    assert len(signals("stuck_on_page", j)) == 2
    j = Journey().step("learn.html", page_hash="same").step("learn.html", page_hash="same").step("explore.html", page_hash="same")
    assert signals("stuck_on_page", j) == []


@pytest.mark.parametrize("ok,expected", [(True, 1), (False, 0)])
def test_backtrack_requires_success_and_uses_url_before(ok, expected):
    j = Journey().step("https://test/demo/learn.html?q=1#x", "back", to="index.html", ok=ok)
    found = signals("backtrack", j)
    assert len(found) == expected
    if found:
        assert found[0].page == "/demo/learn.html"
        assert len(found[0].seq_refs) == 2


@pytest.mark.parametrize("second_page,second_ok,expected", [("verify.html", False, 1), ("details.html", False, 0), ("verify.html", True, 0)])
def test_repeated_failure_same_page(second_page, second_ok, expected):
    j = Journey().step(ok=False).step(second_page, ok=second_ok)
    assert len(signals("repeated_failure", j)) == expected


@pytest.mark.parametrize("tag,action,to,expected", [
    ("edge_case_input", "click", "verify.html", 1),
    ("deterministic", "click", "verify.html", 0),
    ("edge_case_input", "back", "index.html", 0),
    ("edge_case_input", "click", "details.html", 0),
])
def test_invalid_input_accepted_requires_tag_and_forward_navigation(tag, action, to, expected):
    j = Journey().step("details.html", "type", tags=[tag], text="12345")
    j.step("details.html", "type", label="Name", text="Test User")
    j.step("details.html", action, to=to)
    assert len(signals("invalid_input_accepted", j)) == expected


def test_invalid_input_does_not_leak_across_back_navigation():
    j = Journey().step("details.html", "type", tags=["edge_case_input"], text="12345")
    j.step("details.html", "back", to="plans.html").step("plans.html", to="details.html")
    j.step("details.html", to="verify.html")
    assert signals("invalid_input_accepted", j) == []


@pytest.mark.parametrize("status,expected", [("abandoned", 1), ("failed", 1), ("budget_exhausted", 1), ("success", 0), ("error", 0), ("blocked_by_verification", 0)])
def test_abandon_point_status_and_last_observation(status, expected):
    j = Journey().step("details.html", to="verify.html").finish(status)
    found = signals("abandon_point", j)
    assert len(found) == expected
    if found:
        assert found[0].page == "/demo/details.html"
        assert found[0].detail["status"] == status


@pytest.mark.parametrize("delta,status,expected", [(0.1, "success", 1), (0.099, "success", 0), (0.01, "abandoned", 1)])
def test_risk_hesitation_threshold_or_abandonment(delta, status, expected):
    j = Journey().step("pay.html", signals=["risk_page"], delta=delta).finish(status)
    assert len(signals("risk_hesitation", j)) == expected


def test_risk_hesitation_does_not_attribute_other_page_abandonment():
    j = Journey().step("pay.html", signals=["risk_page"], delta=0.01)
    j.step("pay.html", "back", to="review.html").step("review.html").finish("abandoned")
    assert signals("risk_hesitation", j) == []
    assert signals("risk_hesitation", Journey().step("pay.html", delta=0.5).finish("abandoned")) == []


@pytest.mark.parametrize("long_count,second_status,expected", [(7, "success", 1), (6, "success", 0), (7, "failed", 0)])
def test_long_path_strict_threshold_and_two_successes(long_count, second_status, expected):
    fast = Journey("power-01").step().finish()
    slow = Journey("chaos-01").step().finish(second_status)
    fast.state.action_count, slow.state.action_count = 4, long_count
    found = signals("long_path", fast, slow)
    assert len(found) == expected
    if found:
        assert found[0].persona_id == "chaos-01" and found[0].page is None


@pytest.mark.parametrize("elements,expected", [(0, 1), (1, 0)])
def test_dead_end_no_elements(elements, expected):
    assert len(signals("dead_end", Journey().step("learn.html", elements=elements))) == expected


@pytest.mark.parametrize("attempts,exit_kind,expected", [(2, "back", 1), (2, "finish", 0), (1, "back", 0), (2, "forward", 0)])  # finishing is an abandon_point
def test_dead_end_action_exit_rule(attempts, exit_kind, expected):
    j = Journey()
    for _ in range(attempts):
        j.step("explore.html")
    if exit_kind == "finish":
        j.finish("budget_exhausted")
    else:
        j.step("explore.html", "back" if exit_kind == "back" else "click", to="index.html")
    assert len(signals("dead_end", j)) == expected


def test_dead_end_resets_between_visits():
    j = Journey().step("explore.html").step("explore.html", to="index.html")
    j.step("index.html", to="explore.html").step("explore.html").finish("failed")
    assert signals("dead_end", j) == []


@pytest.mark.parametrize("tags,prompt,observation_number,expected", [
    (["double_click"], "Total ₹4,812 Payment ₹4,812 Payment ₹4,812", 1, 1),
    (["double_click"], "₹ 4812 ₹4812", 3, 1),
    ([], "Total ₹4,812 Payment ₹4,812", 1, 0),
    (["double_click"], "Total ₹4,812", 1, 0),
    (["double_click"], "₹4,812 ₹4,812", 4, 0),
])
def test_duplicate_submit_amount_counts_and_window(tags, prompt, observation_number, expected):
    j = Journey().step("pay.html", tags=tags, prompt="Total ₹4,812")
    for _ in range(observation_number - 1):
        j.step("pay.html", "wait", prompt="Total ₹4,812")
    j.step("confirmed.html", "wait", prompt=prompt)
    found = signals("duplicate_submit_effect", j)
    assert len(found) == expected
    if found:
        assert found[0].page == "/demo/pay.html"


@pytest.mark.parametrize("action,label,changed,gap,expected", [
    ("wait", None, True, 1, 1), ("click", "Send OTP", True, 2, 1),
    ("click", "Verify OTP", True, 1, 0), ("wait", None, False, 1, 0),
    ("wait", None, True, 3, 0),
])
def test_delayed_feedback_wait_retry_and_step_window(action, label, changed, gap, expected):
    j = Journey().step(label="Send OTP")
    for _ in range(gap - 1):
        j.step(action="scroll")
    j.step(action=action, label=label, changed=changed)
    assert len(signals("delayed_feedback", j)) == expected


def test_delayed_feedback_state_signal_and_initial_click_constraints():
    assert signals("delayed_feedback", Journey().step(signals=["delayed_change"]))
    for initial in [{"changed": True}, {"ok": False}, {"to": "pay.html"}]:
        j = Journey().step(**initial).step("pay.html" if "to" in initial else "verify.html", "wait", changed=True)
        assert signals("delayed_feedback", j) == []


@pytest.mark.parametrize("alert,expected", [
    ("INVALID INPUT", 1), ("Something went wrong!", 1), ("Error: try again", 1),
    ("Failed", 1), ("Error: enter a valid ten digit mobile number", 0),
    ("Choose a plan", 0), ("errorless", 0),
])
def test_generic_error_message_short_matching_alerts(alert, expected):
    assert len(signals("generic_error_message", Journey().step(alerts=[alert]))) == expected


@pytest.mark.parametrize("prompt,expected", [
    ('[1] checkbox "Share with partners" checked', 1),
    ('[1] checkbox "AUTO-RENEW" checked (below the fold)', 1),
    ('[1] checkbox "Marketing consent" unchecked', 0),
    ('[1] checkbox "Remember me" checked', 0),
    ('[1] button "Share" checked', 0),
])
def test_prechecked_consent_pattern(prompt, expected):
    assert len(signals("prechecked_consent", Journey().step("pay.html", prompt=prompt))) == expected


def test_prechecked_consent_only_first_observation_of_normalized_page():
    j = Journey().step("pay.html", prompt='checkbox "Share data" unchecked')
    j.step("https://test/demo/pay.html?q=2", prompt='checkbox "Share data" checked')
    assert signals("prechecked_consent", j) == []


@pytest.mark.parametrize("second_route,status,expected", [
    (["/demo/", "/review", "/end"], "success", 2),
    (["/demo/index.html", "/demo/", "/end"], "success", 0),
    (["/demo/", "/review", "/end"], "abandoned", 0),
])
def test_route_divergence_successful_collapsed_paths(second_route, status, expected):
    a = Journey("power-01").step().finish()
    b = Journey("chaos-01").step().finish(status)
    a.state.visited_paths, b.state.visited_paths = ["/demo/", "/end"], second_route
    found = signals("route_divergence", a, b)
    assert len(found) == expected
    assert all(s.page is None for s in found)


def test_other_persona_events_cannot_complete_a_detector_pattern():
    a = Journey("power-01").step(page_hash="same").step(page_hash="same")
    b = Journey("chaos-01").step(page_hash="same")
    assert signals("stuck_on_page", a, b) == []
    a = Journey("power-01").step("details.html", "type", tags=["edge_case_input"])
    b = Journey("chaos-01").step("details.html", to="verify.html")
    assert signals("invalid_input_accepted", a, b) == []


def test_backtrack_pairs_only_same_step_decision_and_result():
    j = Journey().step(action="back", to="index.html")
    j.events[2] = j.events[2].model_copy(update={"step": 2})
    assert signals("backtrack", j) == []
