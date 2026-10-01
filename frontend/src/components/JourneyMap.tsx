"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  buildJourneyGraph, findingAnchor, personaNodeSequence,
  type JourneyGraph, type JourneyNode,
} from "@/lib/journeyGraph";
import type { Finding, PersonaState, RunEvent, RunStatus, TaskStatus } from "@/lib/types";

// Okabe–Ito colors, fixed by behavioral type rather than arrival order.
const colors: Record<PersonaState["persona_type"], string> = {
  impatient: "#D55E00", low_literacy: "#0072B2", power: "#009E73",
  cautious: "#CC79A7", explorer: "#E69F00", chaos: "#56B4E9",
};
const severityColors = { high: "#b94145", medium: "#b77918", low: "#7c8795" };
const emptyFindings: Finding[] = [];
const statusIcon = (status: TaskStatus) => status === "success" ? "✓"
  : status === "abandoned" || status === "failed" ? "✗"
    : status === "budget_exhausted" ? "⌛"
      : status === "error" || status === "blocked_by_verification" ? "⚠"
        : status === "active" ? "●" : "○";
const statusLabel = (status: TaskStatus) => status.replaceAll("_", " ");

function curve(from: JourneyNode, to: JourneyNode, index: number, kind: "back" | "forward") {
  const direction = kind === "back" ? 1 : -1;
  return {
    x: (from.x + to.x) / 2,
    y: (from.y + to.y) / 2 + direction * (50 + index * 16),
  };
}
function edgePath(from: JourneyNode, to: JourneyNode, index: number, kind: "back" | "forward") {
  const control = curve(from, to, index, kind);
  return `M ${from.x} ${from.y} Q ${control.x} ${control.y} ${to.x} ${to.y}`;
}

function LiveDot({ graph, persona, index, color, opacity }: {
  graph: JourneyGraph; persona: PersonaState; index: number; color: string; opacity: number;
}) {
  const dot = useRef<SVGCircleElement>(null);
  const seen = useRef<number | null>(null);
  const transition = graph.transitions.findLast(t => t.persona_id === persona.persona_id);
  const current = graph.nodes.find(node => node.path === graph.current[persona.persona_id]);
  const from = graph.nodes.find(node => node.path === transition?.from);
  const to = graph.nodes.find(node => node.path === transition?.to);

  useEffect(() => {
    if (!dot.current || !current) return;
    const circle = dot.current;
    const latest = transition?.seq ?? 0;
    const animate = seen.current !== null && latest > seen.current && from && to;
    seen.current = latest;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    function place(x: number, y: number) {
      circle.setAttribute("cx", String(x));
      circle.setAttribute("cy", String(y));
    }
    const restingY = current.y + 43 + index * 3;
    if (!animate || reducedMotion) {
      place(current.x, restingY);
      return;
    }
    const control = curve(from, to, index, transition!.kind);
    const start = performance.now();
    circle.dataset.animating = "true";
    function tick(now: number) {
      const t = Math.min(1, (now - start) / 500);
      const u = 1 - t;
      place(u * u * from!.x + 2 * u * t * control.x + t * t * to!.x,
        u * u * from!.y + 2 * u * t * control.y + t * t * to!.y);
      if (t < 1) frame = requestAnimationFrame(tick);
      else {
        circle.dataset.animating = "false";
        place(current!.x, restingY);
      }
    }
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); circle.dataset.animating = "false"; };
  // Coordinates, not graph identity: unrelated SSE messages must not cancel a navigation animation.
  }, [current?.path, current?.x, current?.y, from?.x, from?.y, to?.x, to?.y, transition?.seq, transition?.kind, index]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!current) return null;
  return (
    <circle ref={dot} className="journey-dot" data-persona={persona.persona_id}
      r={7} fill={color} stroke="white" strokeWidth={2} opacity={opacity}>
      <title>{persona.label} · {current.label}</title>
    </circle>
  );
}

function NodePanel({ node, personas, runId, close }: {
  node: JourneyNode; personas: PersonaState[]; runId: string; close: () => void;
}) {
  const visitors = personas.filter(p => node.visits.some(v => v.persona_id === p.persona_id));
  return (
    <aside className="journey-panel" aria-label={`Page details: ${node.label}`}>
      <div className="section-heading">
        <h3>{node.label}</h3>
        <button className="button secondary" onClick={close} aria-label="Close page details">×</button>
      </div>
      <p className="url-path">{node.path}</p>
      <h4>Observed visits</h4>
      {!visitors.length && <p className="muted">No observation recorded on this page.</p>}
      <ul className="journey-visitors">
        {visitors.map(persona => {
          const visits = node.visits.filter(v => v.persona_id === persona.persona_id);
          return (
            <li key={persona.persona_id}>
              <strong>{persona.label} · {visits.length} visits</strong>
              <div className="journey-evidence">
                {visits.map(visit => (
                  <Link key={visit.seq} href={`/runs/${runId}/personas/${persona.persona_id}?step=${visit.seq}`}>
                    {visit.step === null ? `Event ${visit.seq}` : `Step ${visit.step}`} ↗
                  </Link>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      <h4>Findings on this page</h4>
      {!node.findings.length && <p className="muted">No findings supplied for this page.</p>}
      {node.findings.map((finding, index) => (
        <div className="journey-finding" key={index}>
          <span className={`severity severity-${finding.severity}`}>{finding.severity}</span>
          <p>{finding.observed}</p>
          <Link href={`/runs/${runId}/report#${findingAnchor(finding)}`}>Finding in report →</Link>
          <div className="journey-evidence">
            {finding.evidence.map((evidence, i) => (
              <Link key={i} href={`/runs/${runId}/personas/${evidence.persona_id}?step=${evidence.seq}`}>
                {evidence.persona_id} · Event {evidence.seq} ↗
              </Link>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}

function MapContent({ graph, personas, runId, status }: {
  graph: JourneyGraph; personas: PersonaState[]; runId: string; status: RunStatus;
}) {
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const nodes = new Map(graph.nodes.map(node => [node.path, node]));
  const selectedNode = selectedPath ? nodes.get(selectedPath) : null;
  const opacity = (pid: string) => selectedPersona && selectedPersona !== pid ? .15 : 1;
  const personaIndex = (pid: string) => Math.max(0, personas.findIndex(p => p.persona_id === pid));
  const color = (pid: string) => colors[personas[personaIndex(pid)]?.persona_type] || "#536175";
  const summary = `${graph.nodes.length} pages, ${graph.transitions.length} recorded page transitions, ${graph.ends.length} finished personas.`;
  return (
    <section className="panel journey-map" aria-label="Journey map">
      <div className="section-heading">
        <h2>Journey map</h2>
        <span className="muted small">{status === "running" ? "Live · " : ""}{summary}</span>
      </div>
      <div className="journey-legend" aria-label="Highlight a persona">
        {personas.map(persona => (
          <button key={persona.persona_id} type="button" aria-pressed={selectedPersona === persona.persona_id}
            onClick={() => setSelectedPersona(selectedPersona === persona.persona_id ? null : persona.persona_id)}
            style={{ borderColor: colors[persona.persona_type], opacity: opacity(persona.persona_id) }}>
            <span style={{ color: colors[persona.persona_type] }} aria-hidden="true">{statusIcon(persona.task_status)}</span>
            {persona.label}
            <span className="journey-chip-status">{statusLabel(persona.task_status)}</span>
          </button>
        ))}
      </div>
      {selectedPersona && (
        <Link className="journey-replay" href={`/runs/${runId}/personas/${selectedPersona}`}>Replay →</Link>
      )}
      <p className="muted small journey-help">Select a page for evidence. Dashed routes include a back action. Rings show finding severity.</p>
      {!graph.nodes.length && <p className="muted">Waiting for the first recorded page observation.</p>}
      <div className={`journey-layout${selectedNode ? " has-selection" : ""}`}>
        <div className="journey-scroll" tabIndex={0} role="region" aria-label="Scrollable journey diagram">
          <svg className="journey-svg" viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label={summary}>
            <title>Recorded persona journeys</title>
            {graph.edges.map(edge => {
              const from = nodes.get(edge.from)!;
              const to = nodes.get(edge.to)!;
              const key = JSON.stringify([edge.from, edge.to, edge.persona_id]);
              const index = personaIndex(edge.persona_id);
              const label = `${personas[index]?.label || edge.persona_id} · ${edge.count}×`;
              return (
                <path key={key} className="journey-edge" data-persona={edge.persona_id} data-kind={edge.kind}
                  d={edgePath(from, to, index, edge.kind)} fill="none" stroke={color(edge.persona_id)}
                  strokeWidth={2 + edge.count} strokeDasharray={edge.kind === "back" ? "7 5" : undefined}
                  opacity={opacity(edge.persona_id)}>
                  <title>{label}</title>
                </path>
              );
            })}
            {graph.nodes.map(node => {
              const ends = graph.ends.filter(end => end.node === node.path);
              const success = ends.some(end => end.status === "success");
              return (
                <g key={node.path} className="journey-node" data-path={node.path} transform={`translate(${node.x} ${node.y})`}
                  role="button" tabIndex={0} aria-label={`${node.label}, ${node.visits.length} visits, ${node.friction?.count || 0} ${node.friction?.count === 1 ? "finding" : "findings"}`}
                  aria-pressed={selectedPath === node.path} onClick={() => setSelectedPath(node.path)}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedPath(node.path); }
                  }}>
                  <title>{node.label} · {node.path}</title>
                  {node.friction && (
                    <rect className="journey-halo" x={-77} y={-38} width={154} height={76} rx={14}
                      fill="none" stroke={severityColors[node.friction.severity]} strokeWidth={3} />
                  )}
                  <rect x={-70} y={-31} width={140} height={62} rx={9} fill="white"
                    stroke={success ? "#46977a" : selectedPath === node.path ? "#294e9c" : "#becbd9"} strokeWidth={success ? 2.5 : 1.5} />
                  <text textAnchor="middle" y={-5} className="journey-node-label">
                    {node.label.length > 19 ? `${node.label.slice(0, 18)}…` : node.label}
                  </text>
                  <text textAnchor="middle" y={17} className="journey-node-visits">{node.visits.length} visits</text>
                  {node.friction && (
                    <g transform="translate(0 -51)">
                      <rect x={-46} y={-13} width={92} height={23} rx={6} fill="white" stroke={severityColors[node.friction.severity]} />
                      <text textAnchor="middle" y={3} className="journey-finding-count" fill={severityColors[node.friction.severity]}>
                        {node.friction.count} {node.friction.count === 1 ? "finding" : "findings"}
                      </text>
                    </g>
                  )}
                  {ends.map((end, index) => (
                    <text key={end.persona_id} className="journey-end" x={-55 + index * 23} y={58}
                      fill={color(end.persona_id)} opacity={opacity(end.persona_id)}>
                      <title>{personas.find(p => p.persona_id === end.persona_id)?.label || end.persona_id} · {statusLabel(end.status)}</title>
                      {statusIcon(end.status)}
                    </text>
                  ))}
                </g>
              );
            })}
            {status === "running" && personas.filter(p => !graph.ends.some(end => end.persona_id === p.persona_id)).map(persona => (
              <LiveDot key={persona.persona_id} graph={graph} persona={persona} index={personaIndex(persona.persona_id)}
                color={color(persona.persona_id)} opacity={opacity(persona.persona_id)} />
            ))}
          </svg>
        </div>
        {selectedNode && <NodePanel node={selectedNode} personas={personas} runId={runId} close={() => setSelectedPath(null)} />}
      </div>
      <details className="journey-text">
        <summary>Journey as text</summary>
        <ul>
          {personas.map(persona => (
            <li key={persona.persona_id} data-persona={persona.persona_id}>
              <strong>{persona.label}</strong>: {personaNodeSequence(graph, persona.persona_id).map(path => nodes.get(path)?.label || path).join(" → ") || "No recorded pages"}
              {" · "}{statusLabel(graph.ends.find(end => end.persona_id === persona.persona_id)?.status || persona.task_status)}
            </li>
          ))}
        </ul>
      </details>
      {!!graph.journeyWide.length && (
        <div className="journey-wide">
          <h3>Journey-wide findings</h3>
          <ul>{graph.journeyWide.map((finding, index) => (
            <li key={index}><Link href={`/runs/${runId}/report#${findingAnchor(finding)}`}>{finding.severity}: {finding.observed}</Link></li>
          ))}</ul>
        </div>
      )}
    </section>
  );
}

export function JourneyMap({ events, personas, findings = emptyFindings, runId, status }: {
  events: RunEvent[]; personas: PersonaState[]; findings?: Finding[]; runId: string; status: RunStatus;
}) {
  // Coalesce rendering, never the source stream: each frame reads the complete retained event array.
  const [frameData, setFrameData] = useState({ events, personas, findings, status });
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFrameData({ events, personas, findings, status }));
    return () => cancelAnimationFrame(frame);
  }, [events, personas, findings, status]);
  const graph = useMemo(() => buildJourneyGraph(frameData.events, frameData.personas, frameData.findings), [frameData]);
  return <MapContent graph={graph} personas={frameData.personas} runId={runId} status={frameData.status} />;
}
