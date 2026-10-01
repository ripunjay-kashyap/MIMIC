"""Pure deterministic analysis; synthesis is an independent, optional later pass."""

from app.models.schemas import Finding, PersonaState, RunEvent

from .clustering import cluster_findings
from .detectors import Signal, detect_signals
from .metrics import compute_metrics

__all__ = ["Signal", "compute_metrics", "detect_signals", "cluster_findings", "analyze"]


def analyze(
    run_id: str, personas: list[PersonaState], events: list[RunEvent],
) -> tuple[dict, list[Finding]]:
    # Run IDs scope evidence even if a caller accidentally passes a mixed history.
    signals = detect_signals(personas, [e for e in events if e.run_id == run_id])
    findings = cluster_findings(run_id, signals, len(personas))
    return compute_metrics(personas, findings), findings
