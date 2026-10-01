"""Pure, evidence-backed rules. Per-persona detectors take events in seq order.

`detect_signals` partitions and orders events, then enriches Signal.detail with
`screenshot_paths` (evidence seq -> storage path). This lets the public clustering
API attach screenshots without event access, global state, or I/O.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import groupby

from app.browser.observe import normalize_path
from app.models.schemas import PersonaState, RunEvent

from .metrics import collapsed_path


@dataclass
class Signal:
    type: str
    persona_id: str
    page: str | None
    seq_refs: list[int]
    detail: dict


def _page(event: RunEvent) -> str | None:
    url = event.url or event.payload.get("path")
    return normalize_path(url) if url else None


def _signal(kind: str, refs: list[RunEvent], page: str | None, **detail) -> Signal:
    return Signal(kind, refs[0].persona_id, page, sorted({e.seq for e in refs}), detail)


def _actions(events: list[RunEvent]) -> list[tuple[RunEvent, RunEvent]]:
    decisions = {}
    pairs = []
    for event in events:
        if event.type == "decision":
            decisions[event.step] = event
        elif event.type == "action_result" and event.step in decisions:
            pairs.append((decisions.pop(event.step), event))
    return pairs


def _action(decision: RunEvent) -> str | None:
    return decision.payload.get("action", {}).get("action")


def _before(result: RunEvent) -> str | None:
    url = result.payload.get("result", {}).get("url_before")
    return normalize_path(url) if url else _page(result)


def detect_stuck_on_page(events: list[RunEvent]) -> list[Signal]:
    observations = [e for e in events if e.type == "observation"]
    signals = []
    for (page, page_hash), group in groupby(
        observations, key=lambda e: (_page(e), e.payload.get("page_hash"))
    ):
        refs = list(group)
        if page_hash and len(refs) >= 3:
            signals.append(_signal("stuck_on_page", refs, page, observations=len(refs)))
    return signals


def detect_backtrack(events: list[RunEvent]) -> list[Signal]:
    return [
        _signal("backtrack", [d, r], _before(r))
        for d, r in _actions(events)
        if _action(d) == "back" and r.payload.get("result", {}).get("ok") is True
    ]


def detect_repeated_failure(events: list[RunEvent]) -> list[Signal]:
    pages = defaultdict(list)
    for event in events:
        if event.type == "action_result" and event.payload.get("result", {}).get("ok") is False:
            pages[_before(event)].append(event)
    return [
        _signal("repeated_failure", refs, page, failures=len(refs))
        for page, refs in pages.items() if len(refs) >= 2
    ]


def detect_invalid_input_accepted(events: list[RunEvent]) -> list[Signal]:
    signals = []
    pending = {}
    for decision, result in _actions(events):
        page = _before(result)
        if "edge_case_input" in decision.payload.get("policy_tags", []):
            pending[page] = decision
        data = result.payload.get("result", {})
        destination = normalize_path(data["url_after"]) if data.get("url_after") else None
        if data.get("navigated") and destination != page:
            if page in pending and _action(decision) != "back":
                signals.append(_signal(
                    "invalid_input_accepted", [pending[page], decision, result], page,
                    destination=destination,
                ))
            # A tagged input cannot support a later, unrelated visit to this page.
            pending.clear()
    return signals


def detect_abandon_point(events: list[RunEvent]) -> list[Signal]:
    signals = []
    last_observation = None
    for event in events:
        if event.type == "observation":
            last_observation = event
        elif event.type == "persona_finished" and event.payload.get("status") in {
            "abandoned", "failed", "budget_exhausted",
        }:
            refs = [last_observation, event] if last_observation else [event]
            signals.append(_signal(
                "abandon_point", refs, _page(last_observation) if last_observation else None,
                status=event.payload["status"],
            ))
    return signals


def detect_risk_hesitation(events: list[RunEvent]) -> list[Signal]:
    signals = []
    risks = defaultdict(list)
    last_observation = None
    for event in events:
        if event.type == "observation":
            last_observation = event
        elif event.type == "state_update" and "risk_page" in event.payload.get("signals", []):
            page = _page(event)
            risks[page].append(event)
            delta = event.payload.get("deltas", {}).get("current_frustration", 0)
            if delta >= 0.1:
                signals.append(_signal("risk_hesitation", [event], page, frustration_delta=delta))
        elif event.type == "persona_finished" and event.payload.get("status") == "abandoned":
            # State updates describe the post-action page; terminal URL wins here.
            page = _page(event) or (_page(last_observation) if last_observation else None)
            if page in risks:
                signals.append(_signal("risk_hesitation", [*risks[page], event], page, status="abandoned"))
    return signals


def _success_refs(persona: PersonaState, events: list[RunEvent]) -> list[RunEvent]:
    own = [e for e in events if e.persona_id == persona.persona_id]
    terminal = [e for e in own if e.type == "persona_finished" and e.payload.get("status") == "success"]
    # Partial event histories can still cite real observations/results, never invented seqs.
    return terminal[-1:] or [e for e in own if e.type in {"observation", "action_result"}][-1:]


def detect_long_path(personas: list[PersonaState], events: list[RunEvent]) -> list[Signal]:
    successes = [p for p in personas if p.task_status == "success"]
    if len(successes) < 2:
        return []
    shortest = min(p.action_count for p in successes)
    return [
        _signal("long_path", refs, None, actions=p.action_count, shortest_actions=shortest)
        for p in successes
        if p.action_count > 1.5 * shortest and (refs := _success_refs(p, events))
    ]


def detect_dead_end(events: list[RunEvent]) -> list[Signal]:
    signals = [
        _signal("dead_end", [e], _page(e), reason="no_interactive_elements")
        for e in events if e.type == "observation" and e.payload.get("element_count") == 0
    ]
    pairs = {r.seq: (d, r) for d, r in _actions(events)}
    page = None
    attempts = []
    for event in events:
        if event.type == "observation":
            if _page(event) != page:
                page, attempts = _page(event), []
        elif event.seq in pairs:
            decision, result = pairs[event.seq]
            before, data = _before(result), result.payload.get("result", {})
            if before != page:
                page, attempts = before, []
            action = _action(decision)
            if action == "back" and data.get("ok") and data.get("navigated"):
                if len(attempts) >= 2:
                    signals.append(_signal("dead_end", [*attempts, decision, result], page, reason="back_only_exit"))
                page, attempts = _page(result), []
            elif data.get("navigated"):
                page, attempts = _page(result), []
            elif action not in {"back", "done", "give_up"}:
                attempts.append(result)
    # Terminating on a page is an abandon_point, not a dead end (avoids double-reporting).
    return signals


_AMOUNT = re.compile(r"₹\s?[\d,]+")
_SUBMIT = re.compile(r"\b(proceed|pay|submit|confirm|continue|verify|buy|place order|checkout)\b", re.IGNORECASE)


def _amounts(event: RunEvent) -> Counter:
    return Counter(re.sub(r"[\s,]", "", m) for m in _AMOUNT.findall(event.payload.get("prompt", "")))


def detect_duplicate_submit_effect(events: list[RunEvent]) -> list[Signal]:
    signals = []
    last_observations = {}
    for index, event in enumerate(events):
        if event.type == "observation":
            last_observations[_page(event)] = event
        elif event.type == "decision" and "double_click" in event.payload.get("policy_tags", []):
            if not _SUBMIT.search(event.payload.get("element_label") or ""):
                continue  # only submissions can be duplicated (not navigation links)
            page = _page(event)
            baseline = last_observations.get(page)
            if baseline is None:
                continue
            amounts = _amounts(baseline)
            following = [e for e in events[index + 1:] if e.type == "observation"][:3]
            for observation in following:
                # Same amount shown more often than before (e.g. two payment lines), not new prices on a new page.
                increases = {amount: n for amount, n in _amounts(observation).items() if amounts[amount] and n > amounts[amount]}
                if increases:
                    signals.append(_signal(
                        "duplicate_submit_effect", [baseline, event, observation], page,
                        amounts_before=dict(amounts), amounts_after=dict(_amounts(observation)),
                    ))
                    break
    return signals


def detect_delayed_feedback(events: list[RunEvent]) -> list[Signal]:
    signals = [
        _signal("delayed_feedback", [e], _page(e), reason="delayed_change")
        for e in events if e.type == "state_update" and "delayed_change" in e.payload.get("signals", [])
    ]
    pairs = _actions(events)
    for index, (decision, result) in enumerate(pairs):
        data = result.payload.get("result", {})
        if _action(decision) != "click" or not data.get("ok") or data.get("page_changed") or data.get("navigated"):
            continue
        page, label = _before(result), decision.payload.get("element_label")
        for next_decision, next_result in pairs[index + 1:]:
            if decision.step is None or next_decision.step is None:
                continue
            if next_decision.step > decision.step + 2:
                break
            if next_decision.step <= decision.step:
                continue
            next_data = next_result.payload.get("result", {})
            if _before(next_result) != page:
                break
            retry = _action(next_decision) == "wait" or (
                _action(next_decision) == "click" and label is not None
                and next_decision.payload.get("element_label") == label
            )
            if retry and next_data.get("page_changed"):
                signals.append(_signal("delayed_feedback", [decision, result, next_decision, next_result], page, reason="wait_or_retry"))
                break
            if next_data.get("navigated") or next_data.get("page_changed"):
                break
    return signals


_GENERIC_ERROR = re.compile(r"\b(?:invalid input|something went wrong|error|try again|failed)\b", re.I)


def detect_generic_error_message(events: list[RunEvent]) -> list[Signal]:
    signals = []
    for event in events:
        if event.type == "observation":
            alerts = [a for a in event.payload.get("alerts", []) if len(a.split()) <= 4 and _GENERIC_ERROR.search(a)]
            if alerts:
                signals.append(_signal("generic_error_message", [event], _page(event), alerts=alerts))
    return signals


_CONSENT = re.compile(r'\bcheckbox\s+"[^"\n]*(?:share|partner|consent|marketing|auto-renew)[^"\n]*"\s+checked\b', re.I)


def detect_prechecked_consent(events: list[RunEvent]) -> list[Signal]:
    seen, signals = set(), []
    for event in events:
        if event.type != "observation" or _page(event) in seen:
            continue
        seen.add(_page(event))
        if _CONSENT.search(event.payload.get("prompt", "")):
            signals.append(_signal("prechecked_consent", [event], _page(event)))
    return signals


def detect_route_divergence(personas: list[PersonaState], events: list[RunEvent]) -> list[Signal]:
    successes = [p for p in personas if p.task_status == "success"]
    if len({collapsed_path(p.visited_paths) for p in successes}) < 2:
        return []
    return [
        _signal("route_divergence", refs, None, path=list(collapsed_path(p.visited_paths)))
        for p in successes if (refs := _success_refs(p, events))
    ]


_PERSONA_DETECTORS = (
    detect_stuck_on_page, detect_backtrack, detect_repeated_failure,
    detect_invalid_input_accepted, detect_abandon_point, detect_risk_hesitation,
    detect_dead_end, detect_duplicate_submit_effect, detect_delayed_feedback,
    detect_generic_error_message, detect_prechecked_consent,
)


def detect_signals(personas: list[PersonaState], events: list[RunEvent]) -> list[Signal]:
    ordered = sorted(events, key=lambda e: e.seq)
    by_persona = defaultdict(list)
    screenshots = {}
    for event in ordered:
        if event.persona_id is not None:
            by_persona[event.persona_id].append(event)
        if event.type == "screenshot" and event.step is not None and event.payload.get("path"):
            screenshots.setdefault((event.persona_id, event.step), event.payload["path"])
    signals = [
        signal for pid in sorted(by_persona) for detector in _PERSONA_DETECTORS
        for signal in detector(by_persona[pid])
    ]
    signals.extend(detect_long_path(personas, ordered))
    signals.extend(detect_route_divergence(personas, ordered))
    lookup = {(e.persona_id, e.seq): e for e in ordered}
    for signal in signals:
        signal.detail["screenshot_paths"] = {
            seq: screenshots[(signal.persona_id, event.step)]
            for seq in signal.seq_refs
            if (event := lookup[(signal.persona_id, seq)]).step is not None
            and (signal.persona_id, event.step) in screenshots
        }
    return sorted(signals, key=lambda s: (s.type, s.page or "", s.persona_id, s.seq_refs))
