"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { getGoldenRun, getJourney, getReport, getRun, MOCK } from "@/lib/api";
import {
  buildJourneyGraph, checkGraphMatchesPersonas, findingAnchor, normalizeJourneyPath, personaNodeSequence, plural,
  type JourneyGraph, type JourneyNode,
} from "@/lib/journeyGraph";
import type { EvidenceRef, Finding, PersonaState, RunEvent, TaskStatus } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { categoryTitle } from "./FindingCard";
import { capitalize, EndIcon, severityTints, wrapLabel } from "./JourneyMap";
import { ErrorState, Loading } from "./ResourceState";
import { PersonaGlyph, PersonaSprite, personaColors, personaNames, personaStyle } from "./PersonaSprite";
import { statusLabel } from "./StatusChip";

async function loadCaseStudy() {
  const golden = await getGoldenRun();
  const run = await getRun(golden.run_id);
  if (run.status !== "completed") throw new Error("The featured run is not completed yet. Please try again shortly.");
  const [report, journeys] = await Promise.all([
    getReport(run.run_id),
    Promise.all(run.personas.map(persona => getJourney(run.run_id, persona.persona_id))),
  ]);
  const personas = journeys.map(journey => journey.persona);
  const events = [...new Map(journeys.flatMap(journey => journey.events).map(event => [event.seq, event])).values()].sort((a, b) => a.seq - b.seq);
  return { run, report, personas, events };
}

type CaseData = Awaited<ReturnType<typeof loadCaseStudy>>;
type Decision = Extract<RunEvent, { type: "decision" }>;
type Shot = Extract<RunEvent, { type: "screenshot" }>;
interface Quote { persona: PersonaState; text: string; step: number | null; seq: number }

const severityRank = { high: 2, medium: 1, low: 0 };
const numberWords = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const numberWord = (n: number) => numberWords[n] ?? String(n);
const shortName = (persona: PersonaState) => personaNames[persona.persona_type] ?? persona.label;
const list = (items: string[]) => items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
const stepKey = (personaId: string, step: number | null) => `${personaId}|${step}`;
// Policy-generated reasoning such as "(chaos) going back mid-flow" is not the persona's own voice.
const usable = (text: string | undefined) => !!text?.trim() && !text.trim().startsWith("(");
const outcomeVerbs: Record<TaskStatus, [string, string]> = {
  success: ["reached", "reached"], abandoned: ["gave up on", "gave up"], failed: ["failed on", "failed"],
  budget_exhausted: ["ran out of steps on", "ran out of steps"], blocked_by_verification: ["blocked on", "blocked"],
  error: ["hit an error on", "hit an error"], active: ["was still on", "still browsing"], pending: ["waiting on", "never started"],
};

/** Fades a section in once it scrolls into view; reduced motion shows it immediately (CSS). */
function Reveal({ className = "", label, children }: { className?: string; label: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setVisible(true); observer.disconnect(); }
    }, { threshold: .12, rootMargin: "0px 0px -6% 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <section ref={ref} className={`story-section reveal ${className}`} data-visible={visible || undefined} aria-label={label}>{children}</section>;
}

function StatusMark({ status, color, size = 18 }: { status: TaskStatus; color: string; size?: number }) {
  return <svg className="status-mark" width={size} height={size} viewBox="-10 -10 20 20" aria-hidden="true">
    <circle r={9} fill={color} stroke="#fff" strokeWidth={1.5} />
    <g fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><EndIcon status={status} /></g>
  </svg>;
}

function permutations<T>(items: T[]): T[][] {
  if (items.length <= 1) return [items];
  return items.flatMap((item, index) => permutations([...items.slice(0, index), ...items.slice(index + 1)]).map(rest => [item, ...rest]));
}

/** Map order left to right; pages that share a map column are ordered so recorded routes cross the fewest columns. */
function laneColumns(graph: JourneyGraph) {
  const groups: JourneyNode[][] = [];
  for (const node of [...graph.nodes].sort((a, b) => a.x - b.x || a.y - b.y)) {
    if (groups.at(-1)?.[0].x === node.x) groups.at(-1)!.push(node);
    else groups.push([node]);
  }
  const order: JourneyNode[] = [];
  groups.forEach((group, index) => {
    const later = groups.slice(index + 1).flat();
    const candidates = group.length > 1 && group.length <= 5 ? permutations(group) : [group];
    const span = (candidate: JourneyNode[]) => {
      const position = new Map([...order, ...candidate, ...later].map((node, i) => [node.path, i]));
      return graph.transitions.reduce((total, t) => total + Math.abs((position.get(t.to) ?? 0) - (position.get(t.from) ?? 0)), 0);
    };
    order.push(...candidates.reduce((best, candidate) => span(candidate) < span(best) ? candidate : best));
  });
  return order;
}

/** Each persona's recorded route as a lane: pages left to right, rightward arcs above, leftward arcs below. */
function RouteLanes({ graph, personas, highlight }: { graph: JourneyGraph; personas: PersonaState[]; highlight?: JourneyNode }) {
  const columns = laneColumns(graph);
  const column = new Map(columns.map((node, index) => [node.path, index]));
  const LEFT = 170, COL = 96, TOP = 92, LANE = 76, RIGHT = 150;
  const width = LEFT + columns.length * COL + RIGHT;
  const height = TOP + personas.length * LANE + 8;
  const x = (path: string) => LEFT + (column.get(path) ?? 0) * COL + COL / 2;
  return (
    <svg className="lanes-svg" viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`Recorded routes of ${personas.length} personas across ${columns.length} pages. The same routes are listed as text below.`}>
      {highlight && column.has(highlight.path) && (
        <rect className="lanes-highlight" x={x(highlight.path) - COL / 2 + 4} y={8} width={COL - 8} height={height - 12} rx={18}
          fill={highlight.friction ? severityTints[highlight.friction.severity].fill : "#F3EEE5"} />
      )}
      {columns.map(node => {
        const lines = wrapLabel(node.label, 13, 3);
        return (
          <g key={node.path} className="lanes-column">
            <title>{node.label} · {node.path}</title>
            {lines.map((line, index) => (
              <text key={index} x={x(node.path)} y={TOP - 30 - (lines.length - 1 - index) * 16} textAnchor="middle" className="lanes-page">{line}</text>
            ))}
            {node.friction && <circle cx={x(node.path)} cy={TOP - 14} r={4} fill={severityTints[node.friction.severity].ink}><title>{plural(node.friction.count, "finding")}</title></circle>}
          </g>
        );
      })}
      {personas.map((persona, laneIndex) => {
        const pid = persona.persona_id;
        const y = TOP + laneIndex * LANE + LANE / 2;
        const color = personaColors[persona.persona_type];
        const transitions = graph.transitions.filter(t => t.persona_id === pid);
        const visited = new Set(personaNodeSequence(graph, pid));
        const pairs = new Map<string, { from: string; to: string; kind: "back" | "forward"; count: number; order: number }>();
        transitions.forEach((t, order) => {
          const key = `${t.from}→${t.to}`;
          const pair = pairs.get(key) ?? { from: t.from, to: t.to, kind: t.kind, count: 0, order };
          pair.count++;
          if (t.kind === "back") pair.kind = "back";
          pairs.set(key, pair);
        });
        const end = graph.ends.find(e => e.persona_id === pid);
        const endPath = end?.node ?? graph.current[pid];
        const status = end?.status ?? persona.task_status;
        const route = personaNodeSequence(graph, pid).map(path => graph.nodes.find(n => n.path === path)?.label ?? path).join(" → ");
        return (
          <g key={pid} className="lane" style={{ "--lane": laneIndex } as CSSProperties}>
            <title>{`${persona.label}: ${route || "no recorded pages"} · ${statusLabel(status)}`}</title>
            <line x1={LEFT + COL / 2} x2={LEFT + (columns.length - .5) * COL} y1={y} y2={y} className="lane-track" />
            <g transform={`translate(12 ${y - 18})`}><g transform="scale(.75)"><PersonaGlyph type={persona.persona_type} /></g></g>
            <text x={56} y={y + 5} className="lane-name">{shortName(persona)}</text>
            {[...pairs.values()].map(pair => {
              const x1 = x(pair.from), x2 = x(pair.to);
              const back = (column.get(pair.to) ?? 0) < (column.get(pair.from) ?? 0);
              const lift = 16 + Math.min(Math.abs(x2 - x1) / COL, 4) * 5;
              const cy = back ? y + lift : y - lift;
              return (
                <g key={`${pair.from}→${pair.to}`}>
                  <path className={`lane-arc${pair.kind === "back" ? " is-back" : ""}`} d={`M ${x1} ${y} Q ${(x1 + x2) / 2} ${cy} ${x2} ${y}`}
                    pathLength={pair.kind === "back" ? undefined : 1} fill="none" stroke={color} strokeWidth={Math.min(1.5 + pair.count, 6)}
                    strokeDasharray={pair.kind === "back" ? "5 5" : undefined} strokeLinecap="round"
                    style={{ "--order": pair.order } as CSSProperties} />
                  {pair.count > 1 && <text x={(x1 + x2) / 2} y={back ? y + lift + 6 : y - lift - 1} textAnchor="middle" className="lane-count">{pair.count}×</text>}
                </g>
              );
            })}
            {columns.map(node => visited.has(node.path)
              ? <circle key={node.path} cx={x(node.path)} cy={y} r={5.5} fill={color} stroke="#fff" strokeWidth={1.5} />
              : <circle key={node.path} cx={x(node.path)} cy={y} r={3} fill="#FBF8F3" stroke="#D9CFBF" strokeWidth={1.2} />)}
            {endPath && column.has(endPath) && (
              <g className="lane-end" transform={`translate(${x(endPath)} ${y})`}>
                <circle r={10} fill={color} stroke="#fff" strokeWidth={2} />
                <g fill="none" stroke="#fff" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><EndIcon status={status} /></g>
              </g>
            )}
            <text x={LEFT + columns.length * COL + 22} y={y - 1} className="lane-outcome">{statusLabel(status)}</text>
            <text x={LEFT + columns.length * COL + 22} y={y + 17} className="lane-actions">{plural(persona.action_count, "action")}</text>
          </g>
        );
      })}
    </svg>
  );
}

function QuoteBlock({ quote, runId }: { quote: Quote; runId: string }) {
  return (
    <figure className="quote" style={personaStyle(quote.persona.persona_type)}>
      <PersonaSprite type={quote.persona.persona_type} size={44} />
      <div>
        <blockquote>“{quote.text}”</blockquote>
        <figcaption>
          {shortName(quote.persona)}{quote.step !== null ? `, step ${quote.step}` : ""}
          {" · "}<Link href={`/runs/${runId}/personas/${quote.persona.persona_id}?step=${quote.seq}`}>Replay this step</Link>
        </figcaption>
      </div>
    </figure>
  );
}

function LoadedCaseStudy({ data }: { data: CaseData }) {
  const { run, report, personas, events } = data;
  const story = useMemo(() => {
    const graph = buildJourneyGraph(events, personas, report.findings);
    const nodes = new Map(graph.nodes.map(node => [node.path, node]));
    const pageOfStep = new Map<string, string>();
    for (const event of events) {
      if (event.type === "observation" && event.persona_id) {
        const value = event.payload.path || event.url;
        if (value) pageOfStep.set(stepKey(event.persona_id, event.step), normalizeJourneyPath(value));
      }
    }
    const decisions = events.filter((event): event is Decision => event.type === "decision" && usable(event.payload.action.thought));
    const persona = (pid: string | null) => personas.find(p => p.persona_id === pid);
    const toQuote = (event: Decision): Quote | null => {
      const who = persona(event.persona_id);
      return who ? { persona: who, text: event.payload.action.thought.trim(), step: event.step, seq: event.seq } : null;
    };
    // The persona's words on a page: its final give-up there, else the first time it turned back, else its last thought there.
    function quoteOnPage(pid: string, path: string) {
      const here = decisions.filter(d => d.persona_id === pid && pageOfStep.get(stepKey(pid, d.step)) === path);
      const pick = here.find(d => d.payload.action.action === "give_up") ?? here.find(d => d.payload.action.action === "back") ?? here.at(-1);
      return pick ? toQuote(pick) : null;
    }
    function quoteForEvidence(evidence: EvidenceRef[]) {
      for (const ref of evidence) {
        const event = events.find(e => e.seq === ref.seq && e.persona_id === ref.persona_id);
        if (!event || event.step === null) continue;
        const decision = decisions.find(d => d.persona_id === ref.persona_id && d.step === event.step);
        if (decision) return toQuote(decision);
      }
      return null;
    }
    const hottest = [...graph.nodes].filter(node => node.friction).sort((a, b) =>
      b.friction!.personas.length - a.friction!.personas.length
      || severityRank[b.friction!.severity] - severityRank[a.friction!.severity]
      || b.friction!.count - a.friction!.count)[0];
    const spotlightQuotes = hottest ? personas.filter(p => hottest.friction!.personas.includes(p.persona_id)).flatMap(p => {
      const quote = quoteOnPage(p.persona_id, hottest.path);
      return quote ? [quote] : [];
    }) : [];
    const shot = hottest ? events.find((event): event is Shot => event.type === "screenshot" && !!event.payload.url
      && !!event.persona_id && hottest.friction!.personas.includes(event.persona_id)
      && !!event.url && normalizeJourneyPath(event.url) === hottest.path) : undefined;
    const ranked = [...report.findings].sort((a, b) => severityRank[b.severity] - severityRank[a.severity] || b.personas.length - a.personas.length);
    const others = ranked.filter(finding => finding.page !== hottest?.path).slice(0, 3)
      // Journey-wide findings point at final steps whose words are not about the finding itself.
      .map(finding => ({ finding, quote: finding.page ? quoteForEvidence(finding.evidence) : null }));
    const endGroups = new Map<string, { path: string; status: TaskStatus; names: string[] }>();
    for (const end of graph.ends) {
      const who = persona(end.persona_id);
      if (!who || !end.node) continue;
      const key = `${end.node}|${end.status}`;
      const group = endGroups.get(key) ?? { path: end.node, status: end.status, names: [] };
      group.names.push(shortName(who));
      endGroups.set(key, group);
    }
    const whereTheyEnded = [...endGroups.values()].map(group =>
      `${list(group.names)} ${outcomeVerbs[group.status][0]} ${nodes.get(group.path)?.label ?? group.path}`);
    const routes = new Set(personas.map(p => personaNodeSequence(graph, p.persona_id).join(">"))).size;
    const sameStart = personas.length > 1 && new Set(personas.map(p => graph.starts[p.persona_id])).size === 1;
    return {
      graph, nodes, hottest, spotlightQuotes, shot, others, whereTheyEnded, routes, sameStart,
      mismatches: checkGraphMatchesPersonas(graph, personas),
    };
  }, [events, personas, report.findings]);

  const { graph, nodes, hottest, spotlightQuotes, shot, others, whereTheyEnded, routes, sameStart, mismatches } = story;
  const successes = personas.filter(p => p.task_status === "success");
  const rest = personas.filter(p => p.task_status !== "success");
  const restSummary = (["abandoned", "failed", "budget_exhausted", "blocked_by_verification", "error", "active", "pending"] as const)
    .map(status => [status, rest.filter(p => p.task_status === status).length] as const)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${numberWord(count).toLowerCase()} ${outcomeVerbs[status][1]}`);
  const recorded = new Date(run.created_at);
  let host = run.target_url;
  let seededDemo = false;
  try {
    const url = new URL(run.target_url);
    host = url.host;
    // Our own seeded target (served by the MIMIC backend at /demo/), not any site with a /demo path.
    seededDemo = /\/demo\/?$/.test(url.pathname) && /mimic-backend|^localhost(:\d+)?$|^127\.0\.0\.1(:\d+)?$/.test(url.host);
  } catch { /* Keep the recorded URL. */ }
  const hotFindings = hottest ? [...new Set(hottest.findings.map(f => categoryTitle(f.category).toLowerCase()))] : [];
  const stuckCount = hottest?.friction?.personas.length ?? 0;
  const shotPersona = shot ? personas.find(p => p.persona_id === shot.persona_id) : undefined;
  const routeText = routes === 1 ? "one shared route" : `${numberWord(routes).toLowerCase()} different routes`;

  return (
    <article className="story">
      <header className="story-hero">
        <p className="kicker">Case study · {MOCK ? "Synthetic fixture" : "One recorded run"}</p>
        <h1 className="display">{numberWord(personas.length)} personas. <em>One goal.</em></h1>
        <blockquote className="story-goal">“{run.goal}”</blockquote>
        <p className="story-meta">
          Recorded {Number.isNaN(recorded.getTime()) ? "" : `${recorded.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })} `}on {seededDemo ? "SurakshaSetu, a demo insurance site we built with 13 known usability defects" : host}.
          {" "}Every number, route, quote and screenshot on this page comes from that run.
        </p>
        <ol className="story-cast" aria-label="Who took part and how it ended">
          {personas.map(persona => (
            <li key={persona.persona_id} style={personaStyle(persona.persona_type)} data-status={persona.task_status}>
              <PersonaSprite type={persona.persona_type} size={64} />
              <strong>{shortName(persona)}</strong>
              <span className="cast-outcome">
                <StatusMark status={persona.task_status} color={personaColors[persona.persona_type]} size={16} />
                {statusLabel(persona.task_status)}
              </span>
            </li>
          ))}
        </ol>
        <p className="story-verdict">
          {numberWord(successes.length)} of {numberWord(personas.length).toLowerCase()} reached the goal.
          {restSummary.length > 0 && <> <span>{restSummary.join(", ").replace(/^./, c => c.toUpperCase())}.</span></>}
        </p>
      </header>

      {mismatches.length > 0 && <p className="notice">The recorded events and saved path summaries differ for {new Set(mismatches.map(message => message.split(":")[0])).size} personas. This page follows the recorded events; inspect the text journeys below.</p>}

      <Reveal className="story-routes" label="Where they went">
        <div className="story-copy">
          <p className="kicker">Where they went</p>
          <h2>{(sameStart ? `Same start, ${routeText}` : routeText.replace(/^./, c => c.toUpperCase()))}.</h2>
          {whereTheyEnded.length > 0 && <p className="story-dek">{whereTheyEnded.join(". ")}.</p>}
        </div>
        <figure className="lanes">
          <div className="lanes-scroll" tabIndex={0} role="region" aria-label="Recorded routes, scrollable">
            <RouteLanes graph={graph} personas={personas} highlight={hottest} />
          </div>
          <figcaption>Each line is one persona&apos;s recorded route through the site. Arcs above the line move right, arcs below move left, and dashed arcs were a Back action. Filled dots are pages they reached; a dot under a page name means it has findings.</figcaption>
        </figure>
      </Reveal>

      {hottest && (
        <Reveal className="story-spotlight" label="Where they got stuck">
          <div className="spotlight-copy">
            <p className="kicker">Where they got stuck</p>
            <h2>{hottest.label}</h2>
            <p className="story-dek">
              {numberWord(stuckCount)} of {numberWord(personas.length).toLowerCase()} personas ran into trouble on this page
              {hotFindings.length ? `: ${list(hotFindings)}` : ""}.
            </p>
            <div className="quotes">
              {spotlightQuotes.map(quote => <QuoteBlock key={quote.seq} quote={quote} runId={run.run_id} />)}
            </div>
            {spotlightQuotes.length > 0 && <p className="quote-note">Quotes are each persona&apos;s reasoning at that step, written by its model during the run.</p>}
          </div>
          {shot?.payload.url && (
            <figure className="spotlight-shot">
              <Link href={`/runs/${run.run_id}/personas/${shot.persona_id}?step=${shot.seq}`} aria-label={`Open ${shotPersona ? shortName(shotPersona) : "persona"}'s replay at this screenshot`}>
                {/* Signed screenshot URLs are used directly, as in replay. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={shot.payload.url} alt={`Recorded screenshot of ${hottest.label}`} />
              </Link>
              <figcaption>Recorded screenshot · {shotPersona ? shortName(shotPersona) : shot.persona_id}{shot.step !== null ? `, step ${shot.step}` : ""}</figcaption>
            </figure>
          )}
        </Reveal>
      )}

      {others.length > 0 && (
        <Reveal className="story-findings" label="What else we found">
          <div className="story-copy">
            <p className="kicker">What else we found</p>
            <h2>{plural(report.findings.length, "finding")}, each tied to a recorded step.</h2>
            <p className="story-dek">A few that did not happen on {hottest?.label ?? "a single page"}:</p>
          </div>
          <ol className="story-finding-list">
            {others.map(({ finding, quote }) => <StoryFinding key={findingAnchor(finding)} finding={finding} quote={quote} runId={run.run_id} label={finding.page ? nodes.get(normalizeJourneyPath(finding.page))?.label : undefined} />)}
          </ol>
        </Reveal>
      )}

      <Reveal className="story-close" label="Open the evidence">
        <h2>See it for yourself.</h2>
        <p className="story-dek">Read every finding with its evidence, or replay any persona step by step.</p>
        <p className="story-actions">
          <Link className="button" href={`/runs/${run.run_id}/report`}>Open the full report</Link>
          <Link className="button secondary" href="/">Run your own test</Link>
        </p>
        <ul className="replay-links" aria-label="Replay a persona">
          {personas.map(persona => (
            <li key={persona.persona_id} style={personaStyle(persona.persona_type)}>
              <Link href={`/runs/${run.run_id}/personas/${persona.persona_id}`}>
                <PersonaSprite type={persona.persona_type} size={36} />
                <span>Replay {shortName(persona)}</span>
              </Link>
            </li>
          ))}
        </ul>
        <details className="case-transcript">
          <summary>Recorded journeys as text</summary>
          <ol>
            {personas.map(persona => <li key={persona.persona_id}>
              <Link href={`/runs/${run.run_id}/personas/${persona.persona_id}`}>{persona.label}</Link>
              {": "}{personaNodeSequence(graph, persona.persona_id).map(path => nodes.get(path)?.label || path).join(" → ") || "No recorded pages"}
              {" · "}{statusLabel(persona.task_status)}
            </li>)}
          </ol>
          <p className="muted small">Run {run.run_id}. Pages are arranged left to right for readability; routes keep the recorded navigation order.</p>
        </details>
      </Reveal>
    </article>
  );
}

function StoryFinding({ finding, quote, runId, label }: { finding: Finding; quote: Quote | null; runId: string; label?: string }) {
  return (
    <li className={`story-finding finding-${finding.severity}`}>
      <div className="story-finding-head">
        <span className={`severity severity-${finding.severity}`}>{capitalize(finding.severity)}</span>
        <h3>{categoryTitle(finding.category)}{finding.page ? <span> on {label ?? finding.page}</span> : <span> across the journey</span>}</h3>
      </div>
      <p>{finding.observed}</p>
      {quote && <QuoteBlock quote={quote} runId={runId} />}
      <Link className="story-finding-link" href={`/runs/${runId}/report#${findingAnchor(finding)}`}>Evidence and interpretation →</Link>
    </li>
  );
}

export function CaseStudy() {
  const { data, error, loading, retry } = useResource(loadCaseStudy);
  if (loading) return <Loading label="Loading the featured run and its recorded journeys…" />;
  if (error || !data) return <div className="empty-state">
    <p className="kicker">Case study</p>
    <h1>The evidence is not available yet.</h1>
    <p className="lead">A completed featured run is needed for this story.</p>
    <ErrorState error={error} retry={retry} />
    <Link className="button secondary" href="/">Configure a run →</Link>
  </div>;
  return <LoadedCaseStudy data={data} />;
}
