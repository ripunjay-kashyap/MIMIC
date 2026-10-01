"use client";

import { useCallback } from "react";
import Link from "next/link";
import { ApiError, getReport } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import { FindingCard } from "./FindingCard";
import { MetricTiles } from "./MetricTiles";
import { ErrorState, Loading } from "./ResourceState";

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
