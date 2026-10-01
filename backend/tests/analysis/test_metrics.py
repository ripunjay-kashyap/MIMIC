from app.analysis import compute_metrics
from app.models.schemas import Finding

from .builders import persona


def finding(category, personas):
    return Finding(run_id="run", category=category, severity="low", personas=personas, evidence=[], observed="Fixture")


def test_six_personas_exact_metrics():
    states = [
        persona("power-01", task_status="success", action_count=3, visited_paths=["/demo/", "/demo/", "/end"], current_frustration=0.126),
        persona("low_literacy-01", task_status="failed", action_count=4, visited_paths=["/demo/index.html", "/end"], backtracks=1, current_frustration=0.374),
        persona("impatient-01", task_status="abandoned", action_count=5, visited_paths=["/a", "/b", "/a"], backtracks=2, current_frustration=0.999),
        persona("explorer-01", task_status="budget_exhausted", action_count=8, visited_paths=["/a", "/b"], backtracks=3, current_frustration=0.5),
        persona("cautious-01", task_status="blocked_by_verification", action_count=2, visited_paths=["/a", "/b", "/b"], current_frustration=0.123),
        persona("chaos-01", task_status="error", action_count=0),
    ]
    findings = [finding("stuck_on_page", ["power-01", "chaos-01"]), finding("backtrack", ["power-01"]), finding("route_divergence", ["power-01", "chaos-01"])]
    assert compute_metrics(states, findings) == {
        "completion_rate": 0.167, "abandonment_rate": 0.167,
        "success_count": 1, "failure_count": 1, "abandoned_count": 1,
        "budget_exhausted_count": 1, "blocked_count": 1, "error_count": 1,
        "average_actions": 3.67, "median_actions": 3.5, "unique_paths": 4,
        "repeated_friction_points": 1, "backtracks_total": 6,
        "frustration_at_termination": {
            "power-01": 0.13, "low_literacy-01": 0.37, "impatient-01": 1.0,
            "explorer-01": 0.5, "cautious-01": 0.12, "chaos-01": 0.0,
        },
    }


def test_empty_metrics():
    metrics = compute_metrics([], [])
    assert metrics.pop("frustration_at_termination") == {}
    assert len(metrics) == 13
    assert all(value == 0 for value in metrics.values())


def test_path_collapsing_preserves_backtracks_and_normalizes_urls():
    states = [
        persona("power-01", visited_paths=["https://test/demo/index.html?a=1", "/demo/#x", "/b"]),
        persona("chaos-01", visited_paths=["/demo/", "/b", "/demo/"]),
    ]
    assert compute_metrics(states, [])["unique_paths"] == 2


def test_repeated_friction_counts_unique_personas():
    assert compute_metrics([], [finding("dead_end", ["power-01", "power-01"])])["repeated_friction_points"] == 0
