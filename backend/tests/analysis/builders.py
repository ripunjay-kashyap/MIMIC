"""Small scripted journeys with complete contract payloads and stable timestamps."""

from datetime import datetime, timezone

from app.browser.observe import normalize_path
from app.models.schemas import ActionResult, AgentAction, PersonaState, RunEvent

RUN_ID = "analysis-test-run"
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def persona(pid="power-01", **changes) -> PersonaState:
    data = dict(
        persona_id=pid, persona_type=pid.split("-")[0], label=pid, blurb="Synthetic fixture",
        goal="Complete an insurance purchase", digital_literacy=0.5, patience=0.5,
        risk_tolerance=0.5, reading_tolerance=0.5, exploration=0.5,
        max_actions=30, max_failed_attempts=3, abandon_frustration=0.8,
    )
    data.update(changes)
    return PersonaState(**data)


def url(page: str) -> str:
    if "://" in page:
        return page
    return "https://demo.test" + (page if page.startswith("/") else "/demo/" + page)


class Journey:
    def __init__(self, pid="power-01", *, run_id=RUN_ID, **changes):
        self.state = persona(pid, **changes)
        self.events = []
        self.run_id = run_id
        self.step_number = 0
        self.current_url = None

    def emit(self, kind, payload, *, event_url=None, step=None):
        event = RunEvent(
            run_id=self.run_id, seq=len(self.events) + 1, persona_id=self.state.persona_id,
            ts=NOW, type=kind, step=self.step_number if step is None else step,
            url=event_url or self.current_url, payload=payload,
        )
        self.events.append(event)
        return event

    def step(
        self, page="verify.html", action="click", *, to=None, page_hash=None,
        prompt="Page text\n[0] button \"Continue\"", elements=1, alerts=(),
        ok=True, changed=False, navigated=None, label="Continue", tags=(), text=None,
        signals=(), delta=0.0, screenshot=False,
    ):
        self.step_number += 1
        before, after = url(page), url(to or page)
        self.current_url = before
        self.emit("observation", {
            "title": page, "element_count": elements, "summary": f"{page} · {elements} elements",
            "path": normalize_path(before), "page_hash": page_hash or f"{page}-{self.step_number}",
            "alerts": list(alerts), "prompt": prompt,
        })
        agent_action = AgentAction(
            action=action, element_id=0 if action in {"click", "type", "select"} else None,
            text=text, thought="Follow the scripted journey", confidence=0.8, expects="Task progress",
        )
        self.emit("decision", {
            "action": agent_action.model_dump(), "model": "synthetic", "element_label": label,
            "policy_tags": list(tags),
        })
        result = ActionResult(
            ok=ok, error=None if ok else "Action failed", url_before=before, url_after=after,
            navigated=before != after if navigated is None else navigated,
            page_changed=changed or before != after, dialogs=[], duration_ms=10,
        )
        self.current_url = after
        self.emit("action_result", {"result": result.model_dump()})
        self.state.task_status = "active"
        counted = action not in {"done", "give_up"}
        self.state.action_count += int(counted)
        self.state.failed_attempts += int(not ok)
        self.state.backtracks += int(action == "back" and ok)
        self.state.current_frustration = min(1.0, round(self.state.current_frustration + delta, 3))
        for path in [normalize_path(before), normalize_path(after)]:
            if not self.state.visited_paths or path != self.state.visited_paths[-1]:
                self.state.visited_paths.append(path)
        self.emit("state_update", {
            "state": self.state.model_dump(),
            "deltas": {"action_count": int(counted), "current_frustration": delta},
            "signals": list(signals),
        })
        if screenshot:
            self.emit("screenshot", {
                "reason": "fixture", "path": f"{self.run_id}/{self.state.persona_id}/{self.step_number:03d}.jpg",
                "url": None,
            })
        return self

    def finish(self, status="success"):
        self.state.task_status = status
        self.state.termination_reason = f"Fixture ended: {status}"
        if status == "success":
            self.state.progress = 1.0
        self.emit("persona_finished", {
            "status": status, "reason": self.state.termination_reason, "state": self.state.model_dump(),
        })
        return self


def cohort(*journeys):
    # Interleave persona steps, preserving ordering within each persona. seq is
    # globally unique, as it is in a real run's SSE history.
    events = sorted(
        [e for j in journeys for e in j.events],
        key=lambda e: (e.step or 0, e.persona_id, e.seq),
    )
    return [j.state for j in journeys], [e.model_copy(update={"seq": i}) for i, e in enumerate(events, 1)]
