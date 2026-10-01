import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildJourneyGraph, checkGraphMatchesPersonas, findingAnchor, normalizeJourneyPath, personaNodeSequence } from "./journeyGraph";
import { fixtureEvents, fixtureFindings, initialRun, snapshot } from "./mock/fixtures";
import type { Journey, RunEvent } from "./types";

const run = initialRun("graph-check", { target_url: "https://demo.invalid/demo/", goal: "Complete onboarding", authorized: true }, "2026-10-01T00:00:00Z");
const events = fixtureEvents(run);
const personas = snapshot(run, events).personas;
const findings = fixtureFindings(run.run_id, events);
const graph = buildJourneyGraph(events, personas, findings);
assert.equal(graph.nodes.length, 9);
assert(graph.edges.some(edge => edge.from === "/demo/learn.html" && edge.to === "/demo/" && edge.persona_id === "low_literacy-01" && edge.kind === "back"));
assert.equal(graph.ends.length, 6);
assert.equal(graph.ends.filter(end => end.status === "success").length, 2);
assert.equal(graph.ends.find(end => end.persona_id === "power-01")?.node, "/demo/confirmed.html");
assert.deepEqual(checkGraphMatchesPersonas(graph, personas), []);
assert.deepEqual(buildJourneyGraph([...events].reverse(), personas, findings), graph);
assert.deepEqual(buildJourneyGraph([...events, ...events], personas, findings), graph);
assert.deepEqual(checkGraphMatchesPersonas(buildJourneyGraph([], run.personas), run.personas), []);
assert.equal(normalizeJourneyPath("https://demo.invalid/demo/index.html?x=1#here"), "/demo/");
assert.equal(graph.nodes.reduce((n, node) => n + node.visits.length, 0), events.filter(e => e.type === "observation").length);
assert.deepEqual(buildJourneyGraph([{ ...events[0], type: "future_type" } as unknown as RunEvent], run.personas).nodes, []);
assert.equal(graph.nodes.find(node => node.path === "/demo/")?.label, "Home");
assert.equal(graph.nodes.find(node => node.path === "/demo/learn.html")?.x, 86 + .5 / 6 * 1028);
assert(graph.nodes.find(node => node.path === "/demo/learn.html")!.y < 210);
assert(graph.nodes.find(node => node.path === "/demo/explore.html")!.y > 210);
const extra = [{ ...findings[0], page: "/demo/confirmed.html" }, { ...findings[0], page: null }];
const friction = buildJourneyGraph(events, personas, [...findings, ...extra]);
assert.equal(friction.nodes.find(node => node.path === "/demo/confirmed.html")?.friction?.severity, "high");
assert.equal(friction.nodes.find(node => node.path === "/demo/confirmed.html")?.friction?.count, 2);
assert.equal(friction.journeyWide.length, 1);
const nullId = { ...findings[0], id: "" };
assert(!findingAnchor(nullId).includes("%"));
assert.equal(findingAnchor(nullId), findingAnchor(structuredClone(nullId)));
const nav = events.find(event => event.type === "action_result" && event.persona_id === "power-01")!;
const repeated = buildJourneyGraph([...events, { ...nav, seq: 10000 }], personas);
const repeatedEdge = repeated.edges.find(edge => edge.persona_id === "power-01" && edge.from === "/demo/")!;
assert.equal(repeatedEdge.count, 2);
assert.deepEqual(repeatedEdge.seqs, [nav.seq, 10000]);
const lastTitle = observationsForTitle();
assert.equal(lastTitle.nodes.find(node => node.path === "/demo/plans.html")?.label, "Latest title");
function observationsForTitle() {
  const observation = events.find(event => event.type === "observation" && event.payload.path === "/demo/plans.html")!;
  assert.equal(observation.type, "observation");
  return buildJourneyGraph([...events, { ...observation, seq: 10001, payload: { ...observation.payload, title: "Latest title | SurakshaSetu" } }], personas);
}
const bad = structuredClone(personas);
bad[0].visited_paths.push("/invented");
assert.equal(checkGraphMatchesPersonas(graph, bad).length, 1);
const removed = events.filter(event => !(event.type === "action_result" && event.persona_id === "power-01" && event.step === 2));
assert(checkGraphMatchesPersonas(buildJourneyGraph(removed, personas), personas).some(message => message.includes("missing transition")));
const observations = events.filter(e => e.type === "observation").slice(0, 2).map((event, i) => ({
  ...event, payload: { ...event.payload, path: `/other/${i}`, title: `Page ${i} | Example` },
} as RunEvent));
const other = buildJourneyGraph(observations, []);
assert.equal(other.nodes[0].label, "Page 0");
assert(other.nodes[0].x < other.nodes[1].x);
assert(other.nodes.every(node => node.y === 210));
console.log(`PASS: mock graph — ${graph.nodes.length} nodes, ${graph.edges.length} edges, ${graph.ends.length} end markers, ${events.length} events.`);
for (const persona of personas) console.log(`PASS: ${persona.persona_id}: ${personaNodeSequence(graph, persona.persona_id).join(" → ")}`);
console.log("PASS: all 6 paths match collapsed visited_paths; back edges, friction, side layout, unknown-site layout, empty/zero-step/unknown events, sorting, deduplication and mismatch detection.");

// Optional saved API journeys let the exact same gate inspect real runs without changing backend files.
if (process.argv[2]) {
  const journeys = JSON.parse(readFileSync(process.argv[2], "utf8")) as Journey[];
  const realPersonas = journeys.map(journey => journey.persona);
  const realGraph = buildJourneyGraph(journeys.flatMap(journey => journey.events), realPersonas);
  const mismatches = checkGraphMatchesPersonas(realGraph, realPersonas);
  console.log(`REAL: ${realGraph.nodes.length} nodes, ${realGraph.edges.length} edges, ${realGraph.ends.length} ends; ${mismatches.length} truthfulness mismatches.`);
  for (const mismatch of mismatches) console.log(`MISMATCH: ${mismatch}`);
  if (mismatches.length) process.exitCode = 1;
}
