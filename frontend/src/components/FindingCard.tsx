import Link from "next/link";
import type { Finding } from "@/lib/types";
export function FindingCard({ finding: f }: { finding: Finding }) {
  const source = f.source === "llm_synthesized" ? "AI-written interpretation" : f.source === "template" ? "Template interpretation" : "Deterministic finding";
  return <article className="panel finding"><div className="finding-heading"><div><span className={`severity severity-${f.severity}`}>{f.severity} severity</span><h3>{f.category.replaceAll("_", " ")}</h3><p className="url-path">{f.page || "Across the journey"}</p></div><span className="source-tag">{source}</span></div>
    <div className="finding-sections"><section><h4>Observed</h4><p>{f.observed}</p></section>
      <section><h4>Evidence</h4><div className="persona-chips">{f.personas.map(persona => <span key={persona}>{persona.replace(/-01$/, "").replaceAll("_", " ")}</span>)}</div>
        <ul className="evidence-links">{f.evidence.map((e, i) => <li key={`${e.persona_id}-${e.seq}-${i}`}><Link href={`/runs/${f.run_id}/personas/${e.persona_id}?step=${e.seq}`}>{e.persona_id} · Event {e.seq} ↗</Link></li>)}</ul>
        {!f.evidence.length && <p>No evidence references supplied.</p>}
      </section><section><h4>Interpretation</h4><p>{f.interpretation || "No interpretation supplied."}</p></section>
      <section><h4>Suggested investigation</h4><p>{f.suggested_investigation || "No investigation supplied."}</p></section></div>
  </article>;
}
