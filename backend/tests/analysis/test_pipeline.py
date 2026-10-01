import copy
import json
import subprocess
import sys
from pathlib import Path

from app.analysis import analyze
from scripts.evaluate_run import evaluate

from .builders import RUN_ID, Journey, cohort, persona
from .demo_fixture import demo_cohort


def test_demo_cohort_recall_and_evidence_integrity():
    states, events = demo_cohort()
    metrics, findings = analyze(RUN_ID, states, events)
    evaluation = evaluate(findings)
    assert evaluation["recall"] >= 0.7
    assert {"D4", "D6", "D11"} <= set(evaluation["found"])
    assert "D12" not in evaluation["found"] + evaluation["missed"]
    assert metrics["success_count"] == 2 and metrics["abandoned_count"] == 2
    lookup = {(e.persona_id, e.seq): e for e in events}
    for finding in findings:
        assert finding.evidence
        assert set(finding.personas) <= {p.persona_id for p in states}
        for ref in finding.evidence:
            assert (ref.persona_id, ref.seq) in lookup
            if ref.screenshot_path:
                source = lookup[(ref.persona_id, ref.seq)]
                assert any(e.type == "screenshot" and e.persona_id == ref.persona_id and e.step == source.step and e.payload["path"] == ref.screenshot_path for e in events)


def test_pipeline_is_deterministic_and_does_not_mutate_inputs():
    states, events = demo_cohort()
    original = copy.deepcopy((states, events))
    expected = analyze(RUN_ID, states, events)
    assert analyze(RUN_ID, list(reversed(states)), list(reversed(events))) == expected
    assert analyze(RUN_ID, states, events) == expected
    assert (states, events) == original


def test_empty_events_zero_step_error_and_unknown_event_type():
    assert analyze(RUN_ID, [], [])[1] == []
    error_persona = persona(task_status="error")
    metrics, findings = analyze(RUN_ID, [error_persona], [])
    assert metrics["error_count"] == 1 and metrics["average_actions"] == 0 and not findings
    j = Journey().step(alerts=["Invalid input"]).finish("failed")
    states, events = cohort(j)
    expected = analyze(RUN_ID, states, events)
    # EventType is a Literal today; model_copy simulates a future persisted event
    # without changing the shared schema owned by the backend agent.
    unknown = events[0].model_copy(update={"seq": 999, "type": "future_event", "payload": {"ignored": True}})
    expanded = [e.model_copy(update={"payload": {**e.payload, "future_field": [1, 2, 3]}}) for e in events]
    assert analyze(RUN_ID, states, [*expanded, unknown]) == expected


def test_successes_without_events_never_fabricate_evidence():
    states = [persona("power-01", task_status="success", action_count=2, visited_paths=["/a"]), persona("chaos-01", task_status="success", action_count=8, visited_paths=["/b"])]
    assert analyze(RUN_ID, states, [])[1] == []


def test_analysis_excludes_evidence_from_other_runs():
    states, events = cohort(Journey().step(alerts=["Invalid input"]))
    foreign = [e.model_copy(update={"run_id": "another-run"}) for e in events]
    assert analyze(RUN_ID, states, foreign)[1] == []


def test_evaluation_cli(tmp_path):
    states, events = demo_cohort()
    findings = analyze(RUN_ID, states, events)[1]
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([f.model_dump() for f in findings]))
    result = subprocess.run(
        [sys.executable, "scripts/evaluate_run.py", str(path)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == evaluate(findings)


def test_evaluation_cli_rejects_non_list(tmp_path):
    path = tmp_path / "bad-findings.json"
    path.write_text('{"findings": []}')
    result = subprocess.run(
        [sys.executable, "scripts/evaluate_run.py", str(path)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "expected a JSON list" in result.stderr
