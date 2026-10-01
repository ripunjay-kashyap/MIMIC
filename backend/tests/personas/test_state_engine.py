"""Gate 4: deterministic state rules, termination precedence, policies, cohort, purity."""

import ast
from pathlib import Path

import pytest

from app.models.schemas import ActionResult, AgentAction, SuccessCriteria
from app.personas.cohort import DEMO_MILESTONES, generate_cohort, persona_id_for
from app.personas.policies import EDGE_CASE_INPUTS, PolicyMemory, apply_policy, rng_for
from app.personas.state_engine import StepInput, apply, mark_error

CRIT = SuccessCriteria(url_contains="confirmed")
BASE = "http://x/demo/"


def persona(ptype="power", **overrides):
    p = next(p for p in generate_cohort("Buy a policy") if p.persona_type == ptype)
    return p.model_copy(update=overrides)


def step(action="click", ok=True, *, path_before="/demo/", path_after=None, page_changed=True, navigated=None,
         hash_after=None, alerts_before=(), alerts_after=(), text="", duration=300, element_id=1, **kw):
    path_after = path_after or path_before
    navigated = (path_after != path_before) if navigated is None else navigated
    return StepInput(
        action=AgentAction(action=action, element_id=element_id),
        result=ActionResult(ok=ok, error=None if ok else "element_not_found", url_before="http://x" + path_before,
                            url_after="http://x" + path_after, navigated=navigated, page_changed=page_changed,
                            duration_ms=duration),
        path_before=path_before, path_after=path_after,
        page_hash_after=hash_after or f"h:{path_after}", alerts_before=list(alerts_before),
        alerts_after=list(alerts_after), text_after=text, **kw,
    )


def run(p, *steps, criteria=CRIT, milestones=DEMO_MILESTONES):
    outs = []
    for s in steps:
        out = apply(p, s, success_criteria=criteria, milestones=milestones)
        p = out.state
        outs.append(out)
    return p, outs


# ---------------------------------------------------------------- frustration rules

def test_failed_action_scales_with_patience():
    impatient, _ = run(persona("impatient"), step(ok=False))
    explorer, _ = run(persona("explorer"), step(ok=False))
    assert impatient.failed_attempts == explorer.failed_attempts == 1
    assert impatient.current_frustration == pytest.approx(0.20 * (1.2 - 0.15), abs=1e-3)
    assert impatient.current_frustration > explorer.current_frustration


def test_click_without_change_signals_but_type_does_not():
    _, [o1] = run(persona(), step("click", page_changed=False))
    _, [o2] = run(persona(), step("type", page_changed=False))
    assert "no_page_change" in o1.signals and o1.state.current_frustration > 0
    assert "no_page_change" not in o2.signals and o2.state.current_frustration == 0


def test_stuck_after_three_identical_pages():
    p, outs = run(persona("explorer"), *[step("scroll", page_changed=False, hash_after="same") for _ in range(3)])
    assert "stuck" not in outs[1].signals and "stuck" in outs[2].signals


def test_backtrack_counts_and_explorer_is_exempt_from_frustration():
    p, [o] = run(persona("low_literacy"), step("back", path_before="/demo/learn.html", path_after="/demo/"))
    assert p.backtracks == 1 and "backtrack" in o.signals and p.current_frustration == pytest.approx(0.05)
    e, _ = run(persona("explorer"), step("back", path_before="/demo/learn.html", path_after="/demo/"))
    assert e.backtracks == 1 and e.current_frustration == 0


def test_new_error_message_hits_low_literacy_harder():
    s = step("click", page_changed=True, alerts_after=["Invalid input"], path_before="/demo/details.html")
    low, [o] = run(persona("low_literacy", progress=0.333), s)  # already credited for reaching details
    power, _ = run(persona("power", progress=0.333), s)
    assert "error_message" in o.signals and low.current_frustration > power.current_frustration
    # Same alert still showing on the next step is not "new".
    _, [o2] = run(low, step("type", alerts_before=["Invalid input"], alerts_after=["Invalid input"],
                            path_before="/demo/details.html"))
    assert "error_message" not in o2.signals


def test_risk_page_only_on_arrival_and_trust_words_neutralize():
    text = "Total payable: ₹4,812 + applicable charges* Auto-renew and share my data with partners"
    cautious, [o] = run(persona("cautious"), step(path_before="/demo/review.html", path_after="/demo/pay.html", text=text))
    assert "risk_page" in o.signals
    # Staying on the page doesn't re-apply.
    _, [o2] = run(cautious, step("scroll", path_before="/demo/pay.html", text=text))
    assert "risk_page" not in o2.signals
    _, [o3] = run(persona("cautious"), step(path_before="/demo/review.html", path_after="/demo/pay.html",
                                            text=text + " 100% secure, refund policy"))
    assert "risk_page" not in o3.signals


def test_progress_from_milestones_reduces_frustration():
    p = persona("impatient", current_frustration=0.3)
    p, [o] = run(p, step(path_before="/demo/", path_after="/demo/plans.html"))
    assert p.progress == pytest.approx(1 / 6, abs=1e-3) and not p.progress_estimated
    assert "progress" in o.signals and p.current_frustration == pytest.approx(0.2)
    # Going back doesn't reduce progress.
    p, _ = run(p, step("back", path_before="/demo/plans.html", path_after="/demo/"))
    assert p.progress == pytest.approx(1 / 6, abs=1e-3)


def test_estimated_progress_without_milestones():
    p, _ = run(persona(), StepInput(**{**step().__dict__, "llm_progress_estimate": 0.4}), milestones=None)
    assert p.progress == 0.4 and p.progress_estimated


def test_delayed_change_signal():
    _, [o] = run(persona(), step(delayed_change=True))
    assert "delayed_change" in o.signals


# ---------------------------------------------------------------- termination

def test_success_on_criteria():
    p, _ = run(persona(), step(path_before="/demo/pay.html", path_after="/demo/confirmed.html"))
    assert p.task_status == "success" and p.progress == 1.0


def test_done_without_success_is_a_failed_attempt():
    p, [o] = run(persona(), step("done", path_before="/demo/plans.html"))
    assert p.task_status == "active" and p.failed_attempts == 1 and p.action_count == 0


def test_done_without_criteria_is_agent_claimed_success():
    p, _ = run(persona(), step("done"), criteria=None, milestones=None)
    assert p.task_status == "success" and p.termination_reason == "agent_claimed_success"


def test_give_up_while_calm_is_refused_but_allowed_when_frustrated():
    calm, _ = run(persona("impatient"), step("give_up"))
    assert calm.task_status == "active" and calm.current_frustration == pytest.approx(0.15)
    upset, _ = run(persona("impatient", current_frustration=0.4), step("give_up"))
    assert upset.task_status == "abandoned"


def test_frustration_threshold_abandons():
    p, _ = run(persona("impatient", current_frustration=0.5), step(ok=False))
    assert p.task_status == "abandoned"


def test_max_failed_attempts_fails():
    p, _ = run(persona("power", current_frustration=0.0), step(ok=False), step(ok=False))
    assert p.task_status == "failed" and p.failed_attempts == 2


def test_budget_exhausted():
    p = persona("power")
    p, outs = run(p, *[step("scroll", hash_after=f"h{i}") for i in range(p.max_actions)])
    assert p.task_status == "budget_exhausted" and p.action_count == p.max_actions


def test_precedence_success_beats_everything():
    p = persona("impatient", current_frustration=0.54, failed_attempts=1, action_count=7)
    p, _ = run(p, step(ok=False, path_before="/demo/pay.html", path_after="/demo/confirmed.html"))
    assert p.task_status == "success"


def test_precedence_verification_beats_abandon():
    p, _ = run(persona("impatient", current_frustration=0.54), step(ok=False, verification_blocked="captcha widget"))
    assert p.task_status == "blocked_by_verification"


def test_terminal_state_is_frozen_and_error_marking():
    p, _ = run(persona(), step(path_after="/demo/confirmed.html", path_before="/demo/pay.html"))
    out = apply(p, step(ok=False), success_criteria=CRIT, milestones=DEMO_MILESTONES)
    assert out.state == p and out.signals == []
    assert mark_error(persona(), "boom").task_status == "error"


def test_deltas_reported():
    _, [o] = run(persona(), step(ok=False))
    assert o.deltas["failed_attempts"] == 1 and o.deltas["action_count"] == 1 and o.deltas["current_frustration"] > 0


def test_input_state_not_mutated():
    p = persona()
    apply(p, step(ok=False), success_criteria=CRIT)
    assert p.failed_attempts == 0 and p.visited_paths == []


# ---------------------------------------------------------------- divergence on the same failure sequence

def test_same_failures_produce_different_terminations():
    failing = [step("click", page_changed=False, hash_after="same", path_before="/demo/verify.html") for _ in range(20)]
    ends = {}
    for ptype in ["impatient", "low_literacy", "power", "cautious", "explorer", "chaos"]:
        p, outs = run(persona(ptype), *failing)
        ends[ptype] = (len([o for o in outs if o.deltas]), p.task_status)
    steps_used = {k: v[0] for k, v in ends.items()}
    assert steps_used["impatient"] == min(steps_used.values())
    assert steps_used["explorer"] >= steps_used["power"]
    assert all(v[1] in ("abandoned", "budget_exhausted", "failed") for v in ends.values())


# ---------------------------------------------------------------- policies

def test_chaos_policy_is_deterministic_per_run_and_persona():
    def decisions(run_id):
        mem = PolicyMemory(rng=rng_for(run_id, "chaos-01"))
        p = persona("chaos", action_count=3)
        out = []
        for i in range(30):
            a = AgentAction(action="type" if i % 2 else "click", element_id=1, text="Zoya")
            d = apply_policy(p, a, path="/demo/details.html", page_text="", element_label="Mobile number",
                             element_kind="input[tel]", mem=mem)
            out.append((d.action.action, d.action.text, d.double_click, tuple(d.tags)))
        return out

    assert decisions("run-a") == decisions("run-a")
    assert decisions("run-a") != decisions("run-b")
    tags = {t for d in decisions("run-a") for t in d[3]}
    assert {"edge_case_input", "double_click"} <= tags
    assert all(d[1] in EDGE_CASE_INPUTS for d in decisions("run-a") if "edge_case_input" in d[3])


def test_impatient_cannot_wait_and_power_cannot_scroll():
    mem = PolicyMemory(rng=rng_for("r", "x"))
    d = apply_policy(persona("impatient"), AgentAction(action="wait"), path="/", page_text="", element_label=None,
                     element_kind=None, mem=mem)
    assert d.action.action == "scroll"
    d = apply_policy(persona("power"), AgentAction(action="scroll"), path="/", page_text="", element_label=None,
                     element_kind=None, mem=mem)
    assert d.action.action == "back"


def test_cautious_scrolls_before_committing_on_risk_page_once():
    mem = PolicyMemory(rng=rng_for("r", "c"))
    p = persona("cautious")
    click = AgentAction(action="click", element_id=3)
    kw = dict(path="/demo/pay.html", page_text="Total payable ₹4,812 + applicable charges", element_label="Proceed",
              element_kind="button", mem=mem)
    first = apply_policy(p, click, **kw)
    second = apply_policy(p, click, **kw)
    assert first.action.action == "scroll" and "deterministic" in first.tags
    assert second.action.action == "click"


# ---------------------------------------------------------------- cohort & purity

def test_cohort_shape_and_model_pinning():
    cohort = generate_cohort("Buy a policy")
    assert [p.persona_id for p in cohort] == [persona_id_for(t) for t in
                                              ["impatient", "low_literacy", "power", "cautious", "explorer", "chaos"]]
    models = [p.llm_model for p in cohort]
    assert all(models.count(m) == 2 for m in set(models))
    assert all(p.max_actions <= 20 and p.task_status == "pending" for p in cohort)
    assert any(p.device == "mobile" for p in cohort)


def test_state_engine_has_no_io_imports():
    src = Path(__file__).resolve().parents[2] / "app/personas/state_engine.py"
    tree = ast.parse(src.read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and m.startswith(("app.browser", "app.llm", "app.db", "playwright", "supabase")) for m in mods)


def test_co_pay_is_not_a_payment_risk_word():
    _, [o] = run(persona("cautious"), step(path_before="/demo/", path_after="/demo/explore.html",
                                           text="Co-pay 20% Sum Insured ₹5L"))
    assert "risk_page" not in o.signals


def test_arriving_on_risk_page_is_not_offset_by_progress():
    text = "Total payable: ₹4,812 + applicable charges*"
    p, [o] = run(persona("cautious", progress=0.667), step(path_before="/demo/review.html", path_after="/demo/pay.html",
                                                            text=text))
    assert {"risk_page", "progress"} <= set(o.signals)
    assert o.deltas["current_frustration"] >= 0.1  # what risk_hesitation looks for
