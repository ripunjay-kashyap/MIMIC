import Link from "next/link";
import type { Finding } from "@/lib/types";
import { findingAnchor } from "@/lib/journeyGraph";

const sourceLabels: Record<Finding["source"], string> = {
  template: "rule-based interpretation",
  llm_synthesized: "AI-written interpretation (verify)",
  deterministic: "Deterministic finding",
};

export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className="panel finding" id={findingAnchor(finding)}>
      <div className="finding-heading">
        <div>
          <span className={`severity severity-${finding.severity}`}>{finding.severity} severity</span>
          <h3>{finding.category.replaceAll("_", " ")}</h3>
          <p className="url-path">{finding.page || "Across the journey"}</p>
        </div>
        <span className="source-tag">{sourceLabels[finding.source]}</span>
      </div>
      <div className="finding-sections">
        <section>
          <h4>Observed</h4>
          <p>{finding.observed}</p>
        </section>
        <section>
          <h4>Evidence</h4>
          <div className="persona-chips">
            {finding.personas.map(persona => (
              <span key={persona}>{persona.replace(/-01$/, "").replaceAll("_", " ")}</span>
            ))}
          </div>
          <ul className="evidence-links">
            {finding.evidence.map((evidence, index) => (
              <li key={`${evidence.persona_id}-${evidence.seq}-${index}`}>
                <Link href={`/runs/${finding.run_id}/personas/${evidence.persona_id}?step=${evidence.seq}`}>
                  {evidence.screenshot_url && (
                    // Signed URLs are used directly, just as in replay.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      className="evidence-thumbnail"
                      src={evidence.screenshot_url}
                      alt={`Screenshot for ${evidence.persona_id}, event ${evidence.seq}`}
                      width={64}
                      height={64}
                    />
                  )}
                  <span>{evidence.persona_id} · Event {evidence.seq} ↗</span>
                </Link>
              </li>
            ))}
          </ul>
          {!finding.evidence.length && <p>No evidence references supplied.</p>}
        </section>
        <section>
          <h4>Interpretation</h4>
          <p>{finding.interpretation || "No interpretation supplied."}</p>
        </section>
        <section>
          <h4>Suggested investigation</h4>
          <p>{finding.suggested_investigation || "No investigation supplied."}</p>
        </section>
      </div>
    </article>
  );
}
