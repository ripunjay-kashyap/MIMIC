"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { EventPayloads, RunEvent } from "@/lib/types";
import { ModelBadge, PolicyChips, SignalChips } from "./EvidenceChips";
import { pathOnly } from "./PersonaCard";

type Shot = Extract<RunEvent, { type: "screenshot" }>;

function Screenshot({ event }: { event: Shot }) {
  if (event.payload.url) {
    // Signed URLs go directly to the browser; never treat storage paths as URLs.
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="evidence-image" src={event.payload.url} alt={event.payload.reason} />;
  }
  return (
    <div className="screenshot-placeholder">
      <span>Screenshot unavailable</span>
      <code>{pathOnly(event.url)}</code>
    </div>
  );
}

function Decision({ payload }: { payload: EventPayloads["decision"] }) {
  const { action, llm_action: original } = payload;
  return (
    <>
      <div className="decision-heading">
        <h3>{action.action} · {payload.element_label || "Page"}</h3>
        <ModelBadge model={payload.model} />
      </div>
      {action.text !== null && <p className="typed-text">Typed text: <code>{action.text}</code></p>}
      <PolicyChips tags={payload.policy_tags || []} />
      {original && (
        <p className="muted model-original">
          model wanted: {original.action}{original.element_id !== null ? ` element ${original.element_id}` : ""}
        </p>
      )}
      <p className="replay-thought">{action.thought}</p>
      <p className="muted">
        Confidence {Math.round(action.confidence * 100)}% · Expected: {action.expects}
      </p>
    </>
  );
}

function Observation({ payload }: { payload: EventPayloads["observation"] }) {
  return (
    <>
      <p>{payload.summary}</p>
      {!!payload.alerts?.length && (
        <p className="observation-alerts"><strong>Page alerts:</strong> {payload.alerts.join(" · ")}</p>
      )}
      <details className="observation-prompt">
        <summary>What the persona saw</summary>
        <pre>{payload.prompt || "Observation text unavailable."}</pre>
      </details>
    </>
  );
}

function StateUpdate({ payload }: { payload: EventPayloads["state_update"] }) {
  return (
    <>
      <SignalChips signals={payload.signals} />
      <div className="deltas">
        {Object.entries(payload.deltas).map(([key, value]) => (
          <span key={key}>
            {key.replace("current_", "").replaceAll("_", " ")} {value >= 0 ? "+" : ""}
            {Number.isInteger(value) ? value : value.toFixed(2)}
          </span>
        ))}
      </div>
    </>
  );
}

export function Timeline({ events, target }: { events: RunEvent[]; target?: string }) {
  const groups = useMemo(() => {
    const map = new Map<number, RunEvent[]>();
    for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
      if (event.step === null) continue;
      map.set(event.step, [...(map.get(event.step) || []), event]);
    }
    return [...map.entries()].sort(([a], [b]) => a - b);
  }, [events]);
  // Evidence links contain event seq numbers despite the parameter name "step".
  const targetSeq = target === undefined ? null : Number(target);
  const targetEvent = events.find(event => event.seq === targetSeq);
  const initialStep = targetEvent?.step
    ?? groups.find(([step]) => step === targetSeq)?.[0]
    ?? groups[0]?.[0];
  const [selected, setSelected] = useState(initialStep);
  const [shot, setShot] = useState<Shot | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const selectedIndex = groups.findIndex(([step]) => step === selected);

  useEffect(() => {
    if (selected !== undefined && (target !== undefined || selected !== groups[0]?.[0])) {
      document.getElementById(`step-${selected}`)?.scrollIntoView({ block: "center" });
    }
  }, [selected, target, groups]);

  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      const editing = event.target instanceof HTMLElement
        && event.target.closest("input, textarea, select, [contenteditable=true]");
      if (shot || event.altKey || event.ctrlKey || event.metaKey || editing) return;
      const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!direction) return;
      const next = groups[selectedIndex + direction];
      if (next) {
        event.preventDefault();
        setSelected(next[0]);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [groups, selectedIndex, shot]);

  useEffect(() => {
    if (shot) dialog.current?.showModal();
  }, [shot]);

  if (!groups.length) return <div className="panel"><p>No steps recorded yet.</p></div>;

  return (
    <>
      <div className="timeline-controls">
        <button className="button secondary" disabled={selectedIndex <= 0} onClick={() => setSelected(groups[selectedIndex - 1][0])}>
          ← Previous step
        </button>
        <span className="muted">Use ← / → keys</span>
        <button className="button secondary" disabled={selectedIndex >= groups.length - 1} onClick={() => setSelected(groups[selectedIndex + 1][0])}>
          Next step →
        </button>
      </div>
      {target !== undefined && !targetEvent && !groups.some(([step]) => step === targetSeq) && (
        <p className="notice">The referenced event is not available in this journey.</p>
      )}
      <ol className="timeline">
        {groups.map(([step, items]) => (
          <li
            className={`panel timeline-step ${selected === step ? "selected-step" : ""}`}
            key={step}
            id={`step-${step}`}
            data-step={step}
            aria-current={selected === step ? "step" : undefined}
          >
            <div className="step-heading">
              <button className="step-selector" onClick={() => setSelected(step)}>Step {step}</button>
              <span className="url-path">{pathOnly(items.findLast(e => e.url)?.url)}</span>
            </div>
            {items.map(event => (
              <div className="timeline-event" key={event.seq} data-event-seq={event.seq}>
                {event.type === "observation" && <Observation payload={event.payload} />}
                {event.type === "decision" && <Decision payload={event.payload} />}
                {event.type === "action_result" && (
                  <p className={event.payload.result.ok ? "result-ok" : "result-error"}>
                    <strong>Result: {event.payload.result.ok ? "OK" : "Error"}</strong>
                    {event.payload.result.error && ` — ${event.payload.result.error}`} · {event.payload.result.duration_ms} ms
                  </p>
                )}
                {event.type === "state_update" && <StateUpdate payload={event.payload} />}
                {event.type === "screenshot" && (
                  <button className="screenshot-button" onClick={() => setShot(event)} aria-label={`Open screenshot for step ${step}`}>
                    <Screenshot event={event} />
                  </button>
                )}
                {event.type === "persona_finished" && <p><strong>Finished:</strong> {event.payload.reason}</p>}
                {event.type === "error" && <p className="result-error">{event.payload.message}</p>}
              </div>
            ))}
          </li>
        ))}
      </ol>
      <dialog ref={dialog} className="image-dialog" onClose={() => setShot(null)} aria-label="Full-size screenshot">
        <div className="dialog-heading">
          <h2>Screenshot · Step {shot?.step}</h2>
          <button className="button secondary" onClick={() => dialog.current?.close()}>Close</button>
        </div>
        {shot && <Screenshot event={shot} />}
      </dialog>
    </>
  );
}
