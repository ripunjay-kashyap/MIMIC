"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  buildJourneyGraph, findingAnchor, personaNodeSequence, plural, visitLabel,
  type JourneyGraph, type JourneyNode,
} from "@/lib/journeyGraph";
import type { Finding, PersonaState, RunEvent, RunStatus, TaskStatus } from "@/lib/types";
import { PersonaGlyph, PersonaSprite, personaColors as colors, personaNames, personaStyle, personaTypeFromId } from "./PersonaSprite";
import { statusLabel } from "./StatusChip";

export const severityTints = {
  high: { fill: "#F8DDD7", ink: "#AE3328" },
  medium: { fill: "#F6E6C2", ink: "#8A5A00" },
  low: { fill: "#ECE7DF", ink: "#5D564D" },
};
const emptyFindings: Finding[] = [];
export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
const SLOT = 22;
// One slot per persona under a page, so end markers and travellers never overlap.
const slotX = (index: number, count: number) => (index - (count - 1) / 2) * SLOT;
type Decision = Extract<RunEvent, { type: "decision" }>;
export const lastDecision = (events: RunEvent[], personaId: string) =>
  events.findLast((event): event is Decision => event.type === "decision" && event.persona_id === personaId);

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

export function wrapLabel(label: string, max = 18, maxLines = 2): string[] {
  const lines: string[] = [];
  for (const word of label.split(/\s+/).filter(Boolean)) {
    const last = lines.at(-1);
    if (last !== undefined && `${last} ${word}`.length <= max) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  const fit = (line: string) => line.length > max ? `${line.slice(0, max - 1)}…` : line;
  if (lines.length <= maxLines) return lines.map(fit);
  return [...lines.slice(0, maxLines - 1).map(fit), `${lines.slice(maxLines - 1).join(" ").slice(0, max - 1)}…`];
}

export function EndIcon({ status }: { status: TaskStatus }) {
  if (status === "success") return <path d="M-3.6 .3l2.4 2.4 4.8-5" />;
  if (status === "abandoned" || status === "failed") return <path d="M-2.8 -2.8l5.6 5.6M2.8 -2.8l-5.6 5.6" />;
  if (status === "budget_exhausted") return <path d="M-3.4 0h.1M0 0h.1M3.4 0h.1" />;
  return <path d="M0 -3.6v3.4M0 3.4v.1" />;
}

function LiveDot({ graph, persona, index, count, color, opacity }: {
  graph: JourneyGraph; persona: PersonaState; index: number; count: number; color: string; opacity: number;
}) {
  const marker = useRef<SVGGElement>(null);
  const seen = useRef<number | null>(null);
  const transition = graph.transitions.findLast(t => t.persona_id === persona.persona_id);
  const current = graph.nodes.find(node => node.path === graph.current[persona.persona_id]);
  const from = graph.nodes.find(node => node.path === transition?.from);
  const to = graph.nodes.find(node => node.path === transition?.to);

  // Layout effect: place the traveller before paint, so it never flashes at the origin.
  useLayoutEffect(() => {
    if (!marker.current || !current) return;
    const group = marker.current;
    const latest = transition?.seq ?? 0;
    const animate = seen.current !== null && latest > seen.current && from && to;
    seen.current = latest;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    const place = (x: number, y: number) => group.setAttribute("transform", `translate(${x} ${y})`);
    const restX = current.x + slotX(index, count);
    const restY = current.y + 52;
    if (!animate || reducedMotion) {
      place(restX, restY);
      return;
    }
    const control = curve(from, to, index, transition!.kind);
    const start = performance.now();
    group.dataset.animating = "true";
    function tick(now: number) {
      const t = Math.min(1, (now - start) / 650);
      const e = t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      const u = 1 - e;
      place(u * u * from!.x + 2 * u * e * control.x + e * e * to!.x,
        u * u * from!.y + 2 * u * e * control.y + e * e * to!.y);
      if (t < 1) frame = requestAnimationFrame(tick);
      else {
        group.dataset.animating = "false";
        place(restX, restY);
      }
    }
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); group.dataset.animating = "false"; };
  // Coordinates, not graph identity: unrelated SSE messages must not cancel a navigation animation.
  }, [current?.path, current?.x, current?.y, from?.x, from?.y, to?.x, to?.y, transition?.seq, transition?.kind, index, count]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!current) return null;
  return (
    <g ref={marker} className="journey-dot" data-persona={persona.persona_id} opacity={opacity}>
      <title>{persona.label} · {current.label}</title>
      <circle r={13} fill="#fff" stroke={color} strokeWidth={2} />
      <g transform="translate(-11 -11) scale(.4583)" aria-hidden="true"><PersonaGlyph type={persona.persona_type} /></g>
    </g>
  );
}

function NodePanel({ node, personas, runId, close }: {
  node: JourneyNode; personas: PersonaState[]; runId: string; close: () => void;
}) {
  const visitors = personas.filter(p => node.visits.some(v => v.persona_id === p.persona_id));
  return (
    <aside className="journey-panel" aria-label={`Page details: ${node.label}`}>
      <div className="journey-panel-head">
        <div>
          <h3>{node.label}</h3>
          <p className="url-path">{node.path}</p>
        </div>
        <button className="button secondary small" onClick={close} aria-label="Close page details">Close</button>
      </div>
      <div className="journey-panel-body">
        <section>
          <h4>Steps on this page</h4>
          {!visitors.length && <p className="muted">No observation recorded on this page.</p>}
          <ul className="journey-visitors">
            {visitors.map(persona => {
              const visits = node.visits.filter(v => v.persona_id === persona.persona_id);
              return (
                <li key={persona.persona_id}>
                  <PersonaSprite type={persona.persona_type} size={28} />
                  <div>
                    <strong>{persona.label} · {plural(visits.length, "step")}</strong>
                    <div className="journey-evidence">
                      {visits.map(visit => (
                        <Link key={visit.seq} href={`/runs/${runId}/personas/${persona.persona_id}?step=${visit.seq}`}>
                          {visit.step === null ? `Event ${visit.seq}` : `Step ${visit.step}`}
                        </Link>
                      ))}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
        <section>
          <h4>Findings on this page</h4>
          {!node.findings.length && <p className="muted">No findings supplied for this page.</p>}
          {node.findings.map((finding, index) => (
            <div className="journey-finding" key={index}>
              <span className={`severity severity-${finding.severity}`}>{capitalize(finding.severity)}</span>
              <p>{finding.observed}</p>
              <Link href={`/runs/${runId}/report#${findingAnchor(finding)}`}>Finding in report →</Link>
              <div className="journey-evidence">
                {finding.evidence.map((evidence, i) => (
                  <Link key={i} href={`/runs/${runId}/personas/${evidence.persona_id}?step=${evidence.seq}`}>
                    {personaName(evidence.persona_id)} · Event {evidence.seq}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </section>
      </div>
    </aside>
  );
}

export function personaName(personaId: string) {
  const type = personaTypeFromId(personaId);
  return type === "ghost" ? personaId : personaNames[type];
}

function personStatus(persona: PersonaState, graph: JourneyGraph, nodes: Map<string, JourneyNode>) {
  const end = graph.ends.find(e => e.persona_id === persona.persona_id);
  const status = end?.status ?? persona.task_status;
  const path = end ? end.node : graph.current[persona.persona_id];
  const place = path ? nodes.get(path)?.label ?? path : null;
  if (status === "pending") return "Waiting to start";
  if (status === "active" && !place) return "Opening the site";
  return place ? `${statusLabel(status)} · ${place}` : statusLabel(status);
}

function MapContent({ graph, personas, events, runId, status, showThoughts }: {
  graph: JourneyGraph; personas: PersonaState[]; events: RunEvent[]; runId: string; status: RunStatus; showThoughts: boolean;
}) {
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const nodes = new Map(graph.nodes.map(node => [node.path, node]));
  const selectedNode = selectedPath ? nodes.get(selectedPath) : null;
  const opacity = (pid: string) => selectedPersona && selectedPersona !== pid ? .15 : 1;
  const personaIndex = (pid: string) => Math.max(0, personas.findIndex(p => p.persona_id === pid));
  const color = (pid: string) => colors[personas[personaIndex(pid)]?.persona_type] || "#8A847B";
  const count = Math.max(personas.length, 1);
  const summary = `${plural(graph.nodes.length, "page")}, ${plural(graph.transitions.length, "recorded page transition")}, ${plural(graph.ends.length, "finished persona")}.`;
  return (
    <section className="journey-map" aria-label="Journey map">
      <div className="journey-head">
        <h2>Journey map</h2>
        <p className="journey-summary">{status === "running" && <span className="live-pill">Live</span>}{summary}</p>
      </div>
      <div className="journey-body">
        <div className="journey-canvas">
          {!graph.nodes.length && <p className="journey-empty">Waiting for the first recorded page observation.</p>}
          <div className="journey-scroll" tabIndex={0} role="region" aria-label="Scrollable journey diagram">
            <svg className="journey-svg" viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label={summary}>
              <title>Recorded persona journeys</title>
              {graph.nodes.filter(node => node.friction).map(node => (
                <rect key={node.path} className="journey-halo" x={node.x - 84} y={node.y - 46} width={168} height={92} rx={24}
                  fill={severityTints[node.friction!.severity].fill} />
              ))}
              {graph.edges.map(edge => {
                const from = nodes.get(edge.from)!;
                const to = nodes.get(edge.to)!;
                const key = JSON.stringify([edge.from, edge.to, edge.persona_id]);
                const index = personaIndex(edge.persona_id);
                const label = `${personas[index]?.label || edge.persona_id} · ${edge.count}×`;
                return (
                  <path key={key} className="journey-edge" data-persona={edge.persona_id} data-kind={edge.kind}
                    d={edgePath(from, to, index, edge.kind)} fill="none" stroke={color(edge.persona_id)}
                    strokeWidth={Math.min(2 + edge.count, 8)} strokeDasharray={edge.kind === "back" ? "7 6" : undefined}
                    opacity={opacity(edge.persona_id)}>
                    <title>{label}</title>
                  </path>
                );
              })}
              {graph.nodes.map(node => {
                const ends = graph.ends.filter(end => end.node === node.path);
                const success = ends.some(end => end.status === "success");
                const selected = selectedPath === node.path;
                const lines = wrapLabel(node.label);
                const tint = node.friction ? severityTints[node.friction.severity] : null;
                return (
                  <g key={node.path} className="journey-node" data-path={node.path} transform={`translate(${node.x} ${node.y})`}
                    role="button" tabIndex={0} aria-label={`${node.label}, ${visitLabel(graph, node)}, ${plural(node.friction?.count || 0, "finding")}`}
                    aria-pressed={selected} onClick={() => setSelectedPath(node.path)}
                    onKeyDown={event => {
                      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedPath(node.path); }
                    }}>
                    <title>{node.label} · {node.path}</title>
                    <rect className="journey-node-card" x={-70} y={-33} width={140} height={66} rx={14}
                      fill={success ? "#EAF4EC" : "#fff"} stroke={selected ? "#221E1A" : success ? "#2B7049" : "#D9CFBF"}
                      strokeWidth={selected || success ? 2 : 1.2} />
                    {lines.map((line, index) => (
                      <text key={index} textAnchor="middle" y={(lines.length > 1 ? -10 : -3) + index * 16} className="journey-node-label">{line}</text>
                    ))}
                    <text textAnchor="middle" y={lines.length > 1 ? 24 : 17} className="journey-node-visits">{visitLabel(graph, node)}</text>
                    {node.friction && tint && (
                      <g transform="translate(0 -46)">
                        <rect x={-42} y={-12} width={84} height={22} rx={11} fill="#fff" stroke={tint.ink} strokeWidth={1.2} />
                        <text textAnchor="middle" y={3.5} className="journey-finding-count" fill={tint.ink}>
                          {plural(node.friction.count, "finding")}
                        </text>
                      </g>
                    )}
                    {ends.map(end => (
                      <g key={end.persona_id} className="journey-end" transform={`translate(${slotX(personaIndex(end.persona_id), count)} 52)`}
                        opacity={opacity(end.persona_id)}>
                        <title>{personas.find(p => p.persona_id === end.persona_id)?.label || end.persona_id} · {statusLabel(end.status)}</title>
                        <circle r={9} fill={color(end.persona_id)} stroke="#fff" strokeWidth={1.5} />
                        <g fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><EndIcon status={end.status} /></g>
                      </g>
                    ))}
                  </g>
                );
              })}
              {status === "running" && personas.filter(p => !graph.ends.some(end => end.persona_id === p.persona_id)).map(persona => (
                <LiveDot key={persona.persona_id} graph={graph} persona={persona} index={personaIndex(persona.persona_id)} count={count}
                  color={color(persona.persona_id)} opacity={opacity(persona.persona_id)} />
              ))}
            </svg>
          </div>
          <p className="journey-help">Select a page to see its evidence. Dashed routes include a back action, tinted pages have findings, and markers under a page show where each persona stopped.</p>
          {selectedNode && <NodePanel node={selectedNode} personas={personas} runId={runId} close={() => setSelectedPath(null)} />}
        </div>
        <div className="journey-legend" aria-label="Highlight a persona">
          {personas.map(persona => {
            const pid = persona.persona_id;
            const thought = showThoughts ? lastDecision(events, pid)?.payload.action.thought : undefined;
            const end = graph.ends.find(e => e.persona_id === pid);
            return (
              <div key={pid} className="journey-person" style={personaStyle(persona.persona_type)}
                data-status={end?.status ?? persona.task_status} data-dimmed={selectedPersona && selectedPersona !== pid ? "true" : undefined}>
                <button type="button" aria-pressed={selectedPersona === pid}
                  onClick={() => setSelectedPersona(selectedPersona === pid ? null : pid)}>
                  <PersonaSprite type={persona.persona_type} size={38} />
                  <span className="journey-person-text">
                    <strong>{persona.label}</strong>
                    <span className="journey-person-status">{personStatus(persona, graph, nodes)}</span>
                  </span>
                </button>
                {thought && <p className="journey-person-thought">“{thought}”</p>}
                <Link className="journey-person-replay" href={`/runs/${runId}/personas/${pid}`} aria-label={`Replay ${persona.label}`} title="Replay">
                  <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden="true"><path d="M3.5 2.2v9.6L11.6 7z" fill="currentColor" /></svg>
                </Link>
              </div>
            );
          })}
        </div>
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
            <li key={index}>
              <span className={`severity severity-${finding.severity}`}>{capitalize(finding.severity)}</span>
              <Link href={`/runs/${runId}/report#${findingAnchor(finding)}`}>{finding.observed}</Link>
            </li>
          ))}</ul>
        </div>
      )}
    </section>
  );
}

export function JourneyMap({ events, personas, findings = emptyFindings, runId, status, showThoughts = false }: {
  events: RunEvent[]; personas: PersonaState[]; findings?: Finding[]; runId: string; status: RunStatus; showThoughts?: boolean;
}) {
  // Coalesce rendering, never the source stream: each frame reads the complete retained event array.
  const [frameData, setFrameData] = useState({ events, personas, findings, status });
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFrameData({ events, personas, findings, status }));
    return () => cancelAnimationFrame(frame);
  }, [events, personas, findings, status]);
  const graph = useMemo(() => buildJourneyGraph(frameData.events, frameData.personas, frameData.findings), [frameData]);
  return <MapContent graph={graph} personas={frameData.personas} events={frameData.events} runId={runId}
    status={frameData.status} showThoughts={showThoughts} />;
}
