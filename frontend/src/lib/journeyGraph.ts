import type { Finding, PersonaState, RunEvent, TaskStatus } from "./types";

export interface JourneyVisit { persona_id: string; step: number | null; seq: number; }
export interface JourneyNode {
  path: string;
  label: string;
  visits: JourneyVisit[];
  x: number;
  y: number;
  findings: Finding[];
  friction: { severity: Finding["severity"]; count: number; personas: string[] } | null;
}
export interface JourneyTransition {
  persona_id: string;
  from: string;
  to: string;
  seq: number;
  kind: "back" | "forward";
}
export interface JourneyEdge {
  from: string;
  to: string;
  persona_id: string;
  kind: "back" | "forward";
  count: number;
  seqs: number[];
}
export interface JourneyGraph {
  width: number;
  height: number;
  nodes: JourneyNode[];
  edges: JourneyEdge[];
  transitions: JourneyTransition[];
  starts: Record<string, string>;
  current: Record<string, string>;
  ends: { persona_id: string; status: TaskStatus; node: string | null }[];
  journeyWide: Finding[];
}

const funnel = ["/demo/", ...["plans", "details", "verify", "review", "pay", "confirmed"].map(p => `/demo/${p}.html`)];
const severityRank = { low: 0, medium: 1, high: 2 };

export function normalizeJourneyPath(value: string): string {
  let path: string;
  try { path = new URL(value, "https://journey.invalid").pathname; }
  catch { path = value.split(/[?#]/)[0]; }
  return path === "/demo/index.html" ? "/demo/" : path;
}

function pageLabel(path: string, title?: string) {
  if (path === "/demo/") return "Home";
  const label = title?.split(/\s+[|–—]\s+|\s+-\s+/)[0].trim();
  if (label) return label;
  const name = path.split("/").filter(Boolean).at(-1)?.replace(/\.html$/, "").replaceAll("-", " ");
  return name ? name[0].toUpperCase() + name.slice(1) : "Home";
}

function layout(nodes: JourneyNode[], transitions: JourneyTransition[]) {
  const demo = nodes.some(node => node.path.startsWith("/demo/"));
  const columns = new Map<string, number>();
  const rows = new Map<string, number>();
  let side = 0;
  nodes.forEach((node, index) => {
    const mainColumn = demo ? funnel.indexOf(node.path) : index;
    if (mainColumn >= 0) columns.set(node.path, mainColumn);
  });
  // Nodes are inserted in evidence order; recursive lookup also handles a side-to-side route.
  function column(path: string, pending = new Set<string>()): number {
    if (columns.has(path)) return columns.get(path)!;
    if (pending.has(path)) return 0;
    pending.add(path);
    const parent = transitions.find(edge => edge.to === path)?.from;
    const value = (parent ? column(parent, pending) : 0) + .5;
    columns.set(path, value);
    return value;
  }
  for (const node of nodes) {
    column(node.path);
    if (demo && !funnel.includes(node.path)) rows.set(node.path, side++ % 2 === 0 ? 78 : 342);
  }
  const maxColumn = Math.max(demo ? 6 : 1, ...columns.values());
  for (const node of nodes) {
    node.x = 86 + (columns.get(node.path) || 0) / maxColumn * 1028;
    node.y = rows.get(node.path) ?? 210;
  }
}

export function buildJourneyGraph(events: RunEvent[], personas: PersonaState[], findings: Finding[] = []): JourneyGraph {
  const graph: JourneyGraph = {
    width: 1200, height: 420, nodes: [], edges: [], transitions: [],
    starts: {}, current: {}, ends: [], journeyWide: [],
  };
  const nodes = new Map<string, JourneyNode>();
  const edges = new Map<string, JourneyEdge>();
  const decisions = new Map<string, string>();
  const observed = new Map<string, string>();
  const ordered = [...new Map(events.map(event => [event.seq, event])).values()].sort((a, b) => a.seq - b.seq);
  function node(value: string) {
    const path = normalizeJourneyPath(value);
    if (!nodes.has(path)) nodes.set(path, { path, label: pageLabel(path), visits: [], x: 0, y: 0, findings: [], friction: null });
    return nodes.get(path)!;
  }
  // Persona snapshots supply identities/status to the renderer, never fabricated routes.
  void personas;
  for (const event of ordered) {
    const pid = event.persona_id;
    if (!pid) continue;
    const stepKey = JSON.stringify([pid, event.step]);
    if (event.type === "decision") decisions.set(stepKey, event.payload.action.action);
    if (event.type === "observation") {
      const value = event.payload.path || event.url;
      if (!value) continue;
      const page = node(value);
      page.label = pageLabel(page.path, event.payload.title);
      page.visits.push({ persona_id: pid, step: event.step, seq: event.seq });
      graph.starts[pid] ??= page.path;
      graph.current[pid] = page.path;
      observed.set(pid, page.path);
    }
    if (event.type === "action_result" && event.payload.result.navigated) {
      const result = event.payload.result;
      if (!result.url_before || !result.url_after) continue;
      const from = node(result.url_before).path;
      const to = node(result.url_after).path;
      graph.current[pid] = to;
      if (from === to) continue;
      const kind = decisions.get(stepKey) === "back" ? "back" : "forward";
      graph.transitions.push({ from, to, persona_id: pid, seq: event.seq, kind });
      const key = JSON.stringify([from, to, pid]);
      const edge = edges.get(key) || { from, to, persona_id: pid, kind, count: 0, seqs: [] };
      edge.count++;
      edge.seqs.push(event.seq);
      // Mixed repeated transitions retain individual kinds above; a dashed aggregate signals back usage.
      if (kind === "back") edge.kind = "back";
      edges.set(key, edge);
    }
    if (event.type === "persona_finished") {
      graph.ends = graph.ends.filter(end => end.persona_id !== pid);
      // Where the persona actually stopped: a final navigation (e.g. to the success page) has no later observation.
      graph.ends.push({ persona_id: pid, status: event.payload.status, node: graph.current[pid] ?? observed.get(pid) ?? null });
    }
  }
  for (const finding of findings) {
    if (finding.page === null) { graph.journeyWide.push(finding); continue; }
    const page = node(finding.page);
    page.findings.push(finding);
    const prior = page.friction;
    page.friction = {
      severity: prior && severityRank[prior.severity] > severityRank[finding.severity] ? prior.severity : finding.severity,
      count: (prior?.count || 0) + 1,
      personas: [...new Set([...(prior?.personas || []), ...finding.personas])],
    };
  }
  graph.nodes = [...nodes.values()];
  graph.edges = [...edges.values()];
  layout(graph.nodes, graph.transitions);
  return graph;
}

export function personaNodeSequence(graph: JourneyGraph, personaId: string): string[] {
  const paths = graph.starts[personaId] ? [graph.starts[personaId]] : [];
  for (const transition of graph.transitions.filter(t => t.persona_id === personaId)) {
    if (paths.at(-1) !== transition.from) paths.push(transition.from);
    if (paths.at(-1) !== transition.to) paths.push(transition.to);
  }
  return paths;
}

export function checkGraphMatchesPersonas(graph: JourneyGraph, personas: PersonaState[]): string[] {
  const messages: string[] = [];
  for (const persona of personas) {
    const expected = persona.visited_paths.map(normalizeJourneyPath).filter((p, i, all) => i === 0 || p !== all[i - 1]);
    const actual = personaNodeSequence(graph, persona.persona_id);
    if (JSON.stringify(expected) !== JSON.stringify(actual)) {
      messages.push(`${persona.persona_id}: graph ${JSON.stringify(actual)} != visited_paths ${JSON.stringify(expected)}`);
    }
    let last = graph.starts[persona.persona_id];
    for (const edge of graph.transitions.filter(t => t.persona_id === persona.persona_id)) {
      if (last !== edge.from) messages.push(`${persona.persona_id}: missing transition ${last || "(no observation)"} → ${edge.from} before seq ${edge.seq}`);
      last = edge.to;
    }
  }
  return messages;
}

export function findingAnchor(finding: Finding): string {
  // IDs can be null in older reports. Evidence provides a stable fallback across severity groups.
  const key = finding.id || JSON.stringify([finding.category, finding.page, finding.evidence, finding.observed]);
  // Avoid percent escapes in DOM IDs: browsers decode them when following fragment links.
  return `finding-${Array.from(key, char => /[a-zA-Z0-9-]/.test(char) ? char : `_${char.codePointAt(0)!.toString(16)}_`).join("")}`;
}

export function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** Observed visits; a page that was reached but never observed (e.g. a terminal success page) shows its arrivals. */
export function visitLabel(graph: JourneyGraph, node: JourneyNode) {
  if (node.visits.length) return plural(node.visits.length, "visit");
  const arrivals = new Set(graph.transitions.filter(t => t.to === node.path).map(t => t.persona_id)).size;
  return arrivals ? `reached by ${arrivals}` : plural(0, "visit");
}
