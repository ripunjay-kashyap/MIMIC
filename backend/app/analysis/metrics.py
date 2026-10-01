"""Deterministic cohort metrics, using final persona states."""

from collections import Counter
from itertools import groupby
from statistics import mean, median

from app.browser.observe import normalize_path
from app.models.schemas import Finding, PersonaState


def collapsed_path(paths: list[str]) -> tuple[str, ...]:
    return tuple(path for path, _ in groupby(normalize_path(p) for p in paths))


def compute_metrics(personas: list[PersonaState], findings: list[Finding]) -> dict:
    counts = Counter(p.task_status for p in personas)
    actions = [p.action_count for p in personas]
    total = len(personas)
    return {
        "completion_rate": round(counts["success"] / total, 3) if total else 0.0,
        "abandonment_rate": round(counts["abandoned"] / total, 3) if total else 0.0,
        "success_count": counts["success"],
        "failure_count": counts["failed"],
        "abandoned_count": counts["abandoned"],
        "budget_exhausted_count": counts["budget_exhausted"],
        "blocked_count": counts["blocked_by_verification"],
        "error_count": counts["error"],
        "average_actions": round(mean(actions), 2) if actions else 0.0,
        "median_actions": round(median(actions), 2) if actions else 0.0,
        "unique_paths": len({collapsed_path(p.visited_paths) for p in personas}),
        "repeated_friction_points": sum(
            len(set(f.personas)) >= 2 and f.category != "route_divergence" for f in findings
        ),
        "backtracks_total": sum(p.backtracks for p in personas),
        "frustration_at_termination": {
            p.persona_id: round(p.current_frustration, 2) for p in sorted(personas, key=lambda p: p.persona_id)
        },
    }
