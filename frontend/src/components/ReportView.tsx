"use client";

import { useCallback, useEffect } from "react";
import Link from "next/link";
import { ApiError, getJourney, getReport, getRun } from "@/lib/api";
import { buildJourneyGraph, checkGraphMatchesPersonas } from "@/lib/journeyGraph";
import type { Finding } from "@/lib/types";
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

export function ReportView({ id }: { id: string }) {
  const load = useCallback(() => getReport(id), [id]);
  const { data, error, loading, retry } = useResource(load);
  if (loading) return <Loading label="Loading report…" />;
  if (error instanceof ApiError && error.status === 409) {
    return (
      <section className="panel">
        <h1>Run still in progress</h1>
        <p>The report will be available once the run is complete.</p>
        <Link href={`/runs/${id}`}>Back to live run →</Link>
        <button className="button secondary report-retry" onClick={retry}>Check again</button>
      </section>
    );
  }
  if (error || !data) return <ErrorState error={error} retry={retry} />;

  return (
    <>
      <Link className="back-link" href={`/runs/${id}`}>← Back to run</Link>
      <div className="page-heading">
        <p className="eyebrow">04 / Results & evidence</p>
        <h1>Run report</h1>
        <p className="lead">What happened, where it happened, and what to investigate next.</p>
      </div>
      <ReportJourneyMap key={id} id={id} findings={data.findings} />
      <MetricTiles metrics={data.metrics} />
      <div className="section-heading findings-title">
        <h2>Findings</h2>
        <span className="muted">{data.findings.length} findings · highest severity first</span>
      </div>
      {!data.findings.length ? (
        <p className="panel">No findings were recorded for this run.</p>
      ) : (
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
      )}
    </>
  );
}
