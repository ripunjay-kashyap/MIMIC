from app.analysis import Signal, analyze, cluster_findings, detect_signals

from .builders import RUN_ID, Journey, cohort


def test_two_stuck_personas_cluster_with_real_evidence_and_screenshots():
    journeys = [Journey(pid) for pid in ["power-01", "chaos-01"]]
    for j in journeys:
        for _ in range(3):
            j.step(page_hash="unchanged", screenshot=True)
    states, events = cohort(*journeys)
    signals = [s for s in detect_signals(states, events) if s.type == "stuck_on_page"]
    findings = cluster_findings(RUN_ID, signals, 2)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "medium"
    assert finding.personas == ["chaos-01", "power-01"]
    assert finding.source == "template" and finding.id is None and finding.run_id == RUN_ID
    assert len(finding.evidence) == 6
    assert {e.persona_id for e in finding.evidence[:2]} == set(finding.personas)
    lookup = {(e.persona_id, e.seq): e for e in events}
    for ref in finding.evidence:
        event = lookup[(ref.persona_id, ref.seq)]
        screenshot = next(e for e in events if e.type == "screenshot" and e.persona_id == ref.persona_id and e.step == event.step)
        assert ref.screenshot_path == screenshot.payload["path"]
    assert "2 of 2 agents" in finding.observed
    assert "may" in finding.interpretation


def test_screenshot_is_never_borrowed_from_other_persona_or_step():
    a = Journey("power-01").step(alerts=["Invalid input"])
    a.step(screenshot=True)
    b = Journey("chaos-01").step(screenshot=True)
    states, events = cohort(a, b)
    _, findings = analyze(RUN_ID, states, events)
    finding = next(f for f in findings if f.category == "generic_error_message")
    assert finding.evidence[0].screenshot_path is None


def test_severity_sorting_unique_personas_and_page_grouping():
    def signal(kind, pid="power-01", page="/a", status=None):
        return Signal(kind, pid, page, [1], {"status": status})

    signals = [
        signal("backtrack"), signal("backtrack"), signal("backtrack", page="/b"),
        signal("stuck_on_page"), signal("stuck_on_page", "chaos-01"),
        signal("abandon_point", status="abandoned"),
        signal("abandon_point", page="/b", status="failed"),
        signal("risk_hesitation", page="/pay", status="abandoned"),
        *[signal("dead_end", pid) for pid in ["power-01", "chaos-01", "explorer-01"]],
        *[signal("route_divergence", pid, None) for pid in ["power-01", "chaos-01", "explorer-01"]],
    ]
    findings = cluster_findings(RUN_ID, signals, 6)
    assert findings[0].category == "dead_end" and findings[0].severity == "high"
    by_key = {(f.category, f.page): f for f in findings}
    assert by_key[("abandon_point", "/a")].severity == "high"
    assert by_key[("risk_hesitation", "/pay")].severity == "high"
    assert by_key[("stuck_on_page", "/a")].severity == "medium"
    assert by_key[("route_divergence", None)].severity == "low"
    assert by_key[("abandon_point", "/b")].severity == "low"
    assert by_key[("backtrack", "/a")].personas == ["power-01"]
    assert len(by_key[("backtrack", "/a")].evidence) == 1
    assert findings == cluster_findings(RUN_ID, list(reversed(signals)), 6)


def test_evidence_limit_prefers_one_reference_per_persona():
    signals = [Signal("stuck_on_page", f"p{i}", "/a", [i * 10 + j for j in range(8)], {}) for i in range(8)]
    finding = cluster_findings(RUN_ID, signals, 8)[0]
    assert len(finding.evidence) == len({e.persona_id for e in finding.evidence}) == 6


def test_no_finding_without_evidence():
    assert cluster_findings(RUN_ID, [Signal("dead_end", "power-01", "/a", [], {})], 1) == []
