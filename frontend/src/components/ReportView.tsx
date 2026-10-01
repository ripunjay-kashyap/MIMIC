"use client";

import { useCallback, useEffect } from "react";
import Link from "next/link";
import { ApiError, getJourney, getReport, getRun } from "@/lib/api";
import { buildJourneyGraph, checkGraphMatchesPersonas } from "@/lib/journeyGraph";
import type { Finding, Metrics } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { FindingCard } from "./FindingCard";
import { MetricTiles } from "./MetricTiles";
import { ErrorState, Loading } from "./ResourceState";
import { JourneyMap } from "./JourneyMap";

function ReportJourneyMap({ id, findings }: { id: string; findings: Finding[] }) {
  const load = useCallback(async () => {
    const run = await getRun(id);
    const journeys = await Promise.all(run.personas.map(persona => getJourney(id, persona.persona_id)));
    return { run, personas: journeys.map(journey => journey.persona), events: journeys.flatMap(journey => journey.events) };
  }, [id]);
  const { data, error, loading, retry } = useResource(load);
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" && data?.run.status === "completed") {
      const graph = buildJourneyGraph(data.events, data.personas, findings);
      for (const mismatch of checkGraphMatchesPersonas(graph, data.personas)) console.warn(`Journey map: ${mismatch}`);
    }
  }, [data, findings]);
  if (loading) return <Loading label="Loading recorded journeys…" />;
  if (error || !data) return <ErrorState error={error} retry={retry} />;
  return <JourneyMap events={data.events} personas={data.personas} findings={findings} runId={id} status={data.run.status} />;
}

/** One sentence, straight from the metrics: who reached the goal and what happened to everyone else. */
function outcomeSentence(m: Metrics) {
  const total = m.success_count + m.failure_count + m.abandoned_count + m.budget_exhausted_count + m.blocked_count + m.error_count;
  if (!total) return "No persona finished this run.";
  const rest = ([
    [m.abandoned_count, "gave up"], [m.failure_count, "failed"], [m.budget_exhausted_count, "ran out of steps"],
    [m.blocked_count, "were blocked by verification"], [m.error_count, "hit an error"],
  ] as const).filter(([count]) => count > 0).map(([count, verb]) => `${count} ${count === 1 ? verb.replace("were", "was") : verb}`);
  const others = rest.length ? ` ${rest.join(", ").replace(/, ([^,]*)$/, " and $1")}.` : "";
  return `${m.success_count} of ${total} personas reached the goal.${others}`;
}

export function ReportView({ id }: { id: string }) {
  const load = useCallback(() => getReport(id), [id]);
  const { data, error, loading, retry } = useResource(load);
  if (loading) return <Loading label="Loading report…" />;
  if (error instanceof ApiError && error.status === 409) {
    return (
      <section className="empty-state">
        <h1>Run still in progress</h1>
        <p>The report will be available once the run is complete.</p>
        <p className="empty-actions">
          <Link className="button secondary" href={`/runs/${id}`}>Back to live run →</Link>
          <button className="button secondary report-retry" onClick={retry}>Check again</button>
        </p>
      </section>
    );
  }
  if (error || !data) return <ErrorState error={error} retry={retry} />;
  const counts = { high: 0, medium: 0, low: 0 };
  data.findings.forEach(finding => { counts[finding.severity]++; });

  return (
    <div className="report wide-page">
      <Link className="back-link" href={`/runs/${id}`}>← Back to run</Link>
      <header className="report-header">
        <p className="kicker">Results and evidence</p>
        <h1>Run report</h1>
        <p className="report-dek">{outcomeSentence(data.metrics)}</p>
      </header>
      <MetricTiles metrics={data.metrics} />
      <section className="report-section" aria-label="Recorded journeys">
        <ReportJourneyMap key={id} id={id} findings={data.findings} />
      </section>
      <section className="report-section" aria-labelledby="findings-title">
        <div className="section-head findings-title">
          <h2 id="findings-title">Findings</h2>
          <p>
            {data.findings.length} {data.findings.length === 1 ? "finding" : "findings"}, highest severity first.
            {" "}What was observed and the evidence come from recorded events; interpretations are labelled by who wrote them.
          </p>
        </div>
        {!data.findings.length ? (
          <p className="empty-note">No findings were recorded for this run.</p>
        ) : (
          <>
            <nav className="severity-jump" aria-label="Jump to severity">
              {(["high", "medium", "low"] as const).map(severity => (
                <a key={severity} href={`#severity-${severity}`} className={`severity severity-${severity}`}>{severity[0].toUpperCase() + severity.slice(1)} · {counts[severity]}</a>
              ))}
            </nav>
            <div className="finding-groups">
              {(["high", "medium", "low"] as const).map(severity => {
                const findings = data.findings.filter(finding => finding.severity === severity);
                return (
                  <section className="finding-group" key={severity} aria-labelledby={`severity-${severity}`}>
                    <h2 id={`severity-${severity}`} className="severity-heading">
                      {severity[0].toUpperCase() + severity.slice(1)} <span>({findings.length})</span>
                    </h2>
                    <div className="findings">
                      {findings.map((finding, index) => (
                        <FindingCard key={finding.id || `${finding.category}-${finding.page}-${index}`} finding={finding} />
                      ))}
                    </div>
                    {!findings.length && <p className="muted">No {severity} severity findings.</p>}
                  </section>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
