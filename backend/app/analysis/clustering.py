"""Group deterministic signals into factual findings with bounded evidence."""

from collections import defaultdict

from app.models.schemas import EvidenceRef, Finding

from .detectors import Signal


# Each observed clause follows "N of M agents". Interpretations are deliberately
# hedged: these rules describe synthetic journeys, not confirmed product defects.
_TEMPLATES = {
    "stuck_on_page": (
        "had at least 3 consecutive observations with the same page hash on {page}",
        "The page may not make the next action or its outcome clear.",
        "Check the available actions and feedback at this point in the journey.",
    ),
    "backtrack": (
        "successfully used Back from {page}",
        "The route may not match what these agents expected to find.",
        "Review the links into this page and the onward navigation.",
    ),
    "repeated_failure": (
        "had at least 2 unsuccessful action results on {page}",
        "The controls or instructions may make successful interaction difficult.",
        "Inspect the failed actions, field requirements, and error feedback.",
    ),
    "invalid_input_accepted": (
        "entered policy-tagged edge-case input on {page} and subsequently navigated to another path without Back",
        "Input validation may allow an unexpected value to proceed.",
        "Review the tagged input and validation before the next page.",
    ),
    "abandon_point": (
        "ended abandoned, failed, or budget-exhausted with their last observation on {page}",
        "This stage may contain friction that prevents completion within the persona's constraints.",
        "Review the final observations, actions, and termination reasons.",
    ),
    "risk_hesitation": (
        "had a risk-page signal on {page} with a frustration increase of at least 0.1 or subsequent abandonment there",
        "The page may leave questions about commitment, privacy, or payment unanswered.",
        "Check the explanation of charges, permissions, and reversibility.",
    ),
    "long_path": (
        "succeeded using more than 1.5 times the fewest actions among successful agents",
        "Some routes may require extra effort or unnecessary steps.",
        "Compare the longer journeys with the shortest successful journey.",
    ),
    "dead_end": (
        "observed no interactive elements on {page}, or took at least 2 actions there without forward navigation before Back or termination",
        "The page may lack a discoverable onward route.",
        "Check whether a clear next action is available from this page.",
    ),
    "duplicate_submit_effect": (
        "used a policy-tagged double click on {page} followed within 3 observations by an increased occurrence count of a rupee amount",
        "Repeated submission may produce duplicate visible payment content.",
        "Inspect submission handling and compare the payment rows before and after the double click.",
    ),
    "delayed_feedback": (
        "had a delayed-change signal on {page}, or an unchanged click followed within 2 steps by a wait or same-label retry that changed the page",
        "The page may not acknowledge the action quickly enough, so users could think nothing happened.",
        "Check for loading indicators and response time after this action.",
    ),
    "generic_error_message": (
        "observed a short generic error message on {page}",
        "The error message may not explain how to recover.",
        "Check whether feedback identifies the affected field or action and gives a specific remedy.",
    ),
    "prechecked_consent": (
        "first observed {page} with a checked checkbox mentioning sharing, partners, consent, marketing, or auto-renewal",
        "The default selection may lead users to overlook a permission or commitment.",
        "Review the checkbox defaults and the explanation of each consent choice.",
    ),
    "route_divergence": (
        "succeeded in a cohort with different visited-path sequences after consecutive duplicates were collapsed",
        "Different successful routes may reflect alternative navigation choices; this alone does not establish friction.",
        "Compare the successful routes and whether each supports the intended task.",
    ),
}


def _evidence(signals: list[Signal]) -> list[EvidenceRef]:
    candidates = defaultdict(dict)
    for signal in signals:
        paths = signal.detail.get("screenshot_paths", {})
        for seq in sorted(set(signal.seq_refs)):
            ref = candidates[signal.persona_id].setdefault(seq, EvidenceRef(
                persona_id=signal.persona_id, seq=seq,
            ))
            ref.screenshot_path = ref.screenshot_path or paths.get(seq)
    # Round-robin selection gives each persona a reference before adding extras.
    queues = [list(refs.values()) for _, refs in sorted(candidates.items())]
    queues = [sorted(refs, key=lambda ref: ref.seq) for refs in queues]
    evidence = []
    for index in range(max((len(q) for q in queues), default=0)):
        for queue in queues:
            if index < len(queue):
                evidence.append(queue[index])
                if len(evidence) == 6:
                    return evidence
    return evidence


def cluster_findings(run_id: str, signals: list[Signal], n_personas: int) -> list[Finding]:
    groups = defaultdict(list)
    for signal in signals:
        # Unsupported signal kinds and signals without evidence cannot form findings.
        if signal.type in _TEMPLATES and signal.seq_refs:
            groups[(signal.type, signal.page)].append(signal)
    findings = []
    for (kind, page), group in groups.items():
        personas = sorted({s.persona_id for s in group})
        abandoned = any(
            s.type in {"abandon_point", "risk_hesitation"} and s.detail.get("status") == "abandoned"
            for s in group
        )
        severity = "high" if len(personas) >= 3 or abandoned else "medium" if len(personas) == 2 else "low"
        if kind == "route_divergence":
            severity = "low"
        observed, interpretation, investigation = _TEMPLATES[kind]
        findings.append(Finding(
            id=None, run_id=run_id, category=kind, severity=severity, page=page,
            personas=personas, evidence=_evidence(group),
            observed=f"{len(personas)} of {n_personas} agents {observed.format(page=page or 'an unrecorded page')}.",
            interpretation=interpretation, suggested_investigation=investigation, source="template",
        ))
    return sorted(findings, key=lambda f: (
        {"high": 0, "medium": 1, "low": 2}[f.severity], -len(f.personas), f.category, f.page or "",
    ))
