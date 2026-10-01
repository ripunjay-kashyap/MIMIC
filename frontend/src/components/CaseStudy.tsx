"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import { getGoldenRun, getJourney, getReport, getRun, MOCK } from "@/lib/api";
import { buildJourneyGraph, checkGraphMatchesPersonas, personaNodeSequence } from "@/lib/journeyGraph";
import { useResource } from "@/lib/use-resource";
import { ErrorState, Loading } from "./ResourceState";
import { JourneyMap } from "./JourneyMap";
import { FindingCard } from "./FindingCard";
import { PersonaSprite, personaColors } from "./PersonaSprite";

const CaseScene = dynamic(() => import("./CaseScene"), {
  ssr: false,
  loading: () => <div className="case-canvas"><Loading label="Preparing recorded trajectories…" /></div>,
});
const motionQuery = "(prefers-reduced-motion: reduce)";
function subscribeMotion(callback: () => void) {
  const media = window.matchMedia(motionQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
const getMotion = () => window.matchMedia(motionQuery).matches;
const serverMotion = () => true;

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

function LoadedCaseStudy({ data }: { data: CaseData }) {
  const [chapter, setChapter] = useState(1);
  const [playing, setPlaying] = useState(true);
  const [replay, setReplay] = useState(0);
  const [flat, setFlat] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const reduced = useSyncExternalStore(subscribeMotion, getMotion, serverMotion);
  const onUnavailable = useCallback(() => setUnavailable(true), []);
  const onComplete = useCallback(() => setPlaying(false), []);
  const graph = useMemo(() => buildJourneyGraph(data.events, data.personas, data.report.findings), [data]);
  const mismatches = useMemo(() => checkGraphMatchesPersonas(graph, data.personas), [graph, data.personas]);
  const hottest = [...graph.nodes].filter(node => node.friction).sort((a, b) =>
    (b.friction?.personas.length || 0) - (a.friction?.personas.length || 0))[0];
  const successCount = data.personas.filter(persona => persona.task_status === "success").length;
  const fallback = reduced || unavailable || flat;
  const chapters = [
    { title: `${data.personas.length} agents. One goal.`, description: `Each persona receives the same task in an isolated browser. This completed run records ${graph.nodes.length} pages and ${graph.transitions.length} page transitions. Start at the first page each agent actually observed.` },
    { title: `${successCount} of ${data.personas.length} reached success.`, description: `Follow each recorded navigation, including returns to earlier pages. Movement follows event order, with time compressed for playback. ${hottest ? `${hottest.label} has findings involving ${hottest.friction!.personas.length} personas.` : "No page-level friction findings were recorded."}` },
    { title: `${data.report.findings.length} ${data.report.findings.length === 1 ? "finding" : "findings"}. Open the evidence.`, description: "Rings identify pages with findings: coral for high severity, amber for medium, slate for low. End markers sit on each persona’s last observed page; a final navigation may go farther. Every finding below links to the recorded step." },
  ];
  function selectChapter(index: number) {
    setChapter(index);
    setReplay(value => value + 1);
    setPlaying(index === 1);
  }

  return (
    <>
      <div className="case-heading">
        <div className="page-heading">
          <p className="eyebrow">Case study / {MOCK ? "Synthetic fixture" : "Recorded golden run"}</p>
          <h1>One goal. Different instincts.</h1>
          <p className="lead">{data.run.goal}</p>
          <p className="target-line">Recorded target: {data.run.target_url}</p>
        </div>
        <Link className="button secondary" href={`/runs/${data.run.run_id}/report`}>Full report ↗</Link>
      </div>
      {mismatches.length > 0 && <p className="notice">The recorded events and saved path summaries differ for {new Set(mismatches.map(message => message.split(":")[0])).size} personas. This view follows the recorded events; inspect the text journeys below.</p>}
      <nav className="case-chapters" aria-label="Case study chapters">
        {chapters.map((item, index) => (
          <button key={item.title} aria-pressed={chapter === index} onClick={() => selectChapter(index)}>
            <small>0{index + 1} / {index === 0 ? "DEPLOY" : index === 1 ? "DIVERGE" : "INVESTIGATE"}</small>
            <strong>{item.title}</strong>
          </button>
        ))}
      </nav>
      <section className="case-stage" aria-label="Recorded journey observatory">
        <div className="case-stage-top">
          <p className="eyebrow">{fallback ? "Recorded journey map" : "Journey observatory / 3D"}</p>
          <div className="case-controls">
            {!fallback && chapter === 1 && <>
              <button className="button secondary" onClick={() => setPlaying(value => !value)}>{playing ? "Pause playback" : "Resume playback"}</button>
              <button className="button secondary" onClick={() => { setReplay(value => value + 1); setPlaying(true); }}>Replay routes</button>
            </>}
            {!reduced && !unavailable && <button className="button secondary" onClick={() => setFlat(value => !value)}>{flat ? "Show 3D" : "Show 2D map"}</button>}
          </div>
        </div>
        {fallback ? <>
          <p className="case-fallback-label">{reduced ? "Reduced motion is on. Showing a static map." : unavailable ? "3D is unavailable on this device. Showing the recorded 2D map." : "2D view · all recorded routes."}</p>
          <JourneyMap events={data.events} personas={data.personas} findings={data.report.findings} runId={data.run.run_id} status="completed" />
        </> : <CaseScene graph={graph} personas={data.personas} chapter={chapter} playing={playing} replay={replay} onUnavailable={onUnavailable} onComplete={onComplete} />}
        <div className="case-legend" aria-label="Persona colors">
          {data.personas.map(persona => <span key={persona.persona_id} style={{ color: personaColors[persona.persona_type] }}><PersonaSprite type={persona.persona_type} size={22} />{persona.label}</span>)}
        </div>
        <div className="case-copy" aria-live="polite">
          <h2>{chapters[chapter].title}</h2><p>{chapters[chapter].description}</p>
        </div>
      </section>
      <details className="panel case-transcript">
        <summary>Recorded journeys as text · {data.personas.length} personas</summary>
        <ol>
          {data.personas.map(persona => <li key={persona.persona_id}>
            <Link href={`/runs/${data.run.run_id}/personas/${persona.persona_id}`}>{persona.label} ↗</Link>
            {": "}{personaNodeSequence(graph, persona.persona_id).map(path => graph.nodes.find(node => node.path === path)?.label || path).join(" → ") || "No recorded pages"}
            {" · "}{persona.task_status.replaceAll("_", " ")}
          </li>)}
        </ol>
        <p className="muted small">Run {data.run.run_id} · Space is arranged for readability; playback preserves recorded navigation order.</p>
      </details>
      <section className="case-evidence" aria-label="Case study evidence">
        <div className="section-heading"><h2>Follow the evidence.</h2><Link href={`/runs/${data.run.run_id}/report`}>All findings →</Link></div>
        <div className="findings">
          {[...data.report.findings].sort((a, b) => ({ high: 0, medium: 1, low: 2 }[a.severity] - { high: 0, medium: 1, low: 2 }[b.severity])).slice(0, 2).map((finding, index) => <FindingCard key={finding.id || index} finding={finding} />)}
          {!data.report.findings.length && <p className="panel">No findings were recorded for this run.</p>}
        </div>
      </section>
    </>
  );
}

export function CaseStudy() {
  const { data, error, loading, retry } = useResource(loadCaseStudy);
  if (loading) return <Loading label="Loading the featured run and its recorded journeys…" />;
  if (error || !data) return <>
    <div className="page-heading"><p className="eyebrow">Case study</p><h1>The evidence is not available yet.</h1><p className="lead">A completed featured run is needed for this story.</p></div>
    <ErrorState error={error} retry={retry} /><Link className="button secondary" href="/">Configure a run →</Link>
  </>;
  return <LoadedCaseStudy data={data} />;
}
