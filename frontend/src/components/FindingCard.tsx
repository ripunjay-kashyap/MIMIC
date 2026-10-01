import Link from "next/link";
import type { Finding } from "@/lib/types";
import { findingAnchor } from "@/lib/journeyGraph";
import { capitalize, personaName } from "./JourneyMap";
import { PersonaSprite, personaTypeFromId } from "./PersonaSprite";

const sourceLabels: Record<Finding["source"], string> = {
  template: "rule-based interpretation",
  llm_synthesized: "AI-written · check against the evidence",
  deterministic: "Deterministic finding",
};

export const categoryTitle = (category: string) => capitalize(category.replaceAll("_", " "));

export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className={`finding finding-${finding.severity}`} id={findingAnchor(finding)}>
      <header className="finding-heading">
        <span className={`severity severity-${finding.severity}`}>{capitalize(finding.severity)} severity</span>
        <h3>{categoryTitle(finding.category)}</h3>
        <p className="finding-page">{finding.page ? <>On <span className="url-path">{finding.page}</span></> : "Across the journey"}</p>
      </header>
      <div className="finding-sections">
        <div className="finding-facts">
          <section>
            <h4>Observed</h4>
            <p>{finding.observed}</p>
          </section>
          <section>
            <h4>Evidence</h4>
            <ul className="persona-chips" aria-label="Personas involved">
              {finding.personas.map(persona => (
                <li key={persona}><PersonaSprite type={personaTypeFromId(persona)} size={24} />{personaName(persona)}</li>
              ))}
            </ul>
            <ul className="evidence-links">
              {finding.evidence.map((evidence, index) => (
                <li key={`${evidence.persona_id}-${evidence.seq}-${index}`} className={evidence.screenshot_url ? undefined : "no-shot"}>
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
                    <span>{personaName(evidence.persona_id)} · Event {evidence.seq}</span>
                  </Link>
                </li>
              ))}
            </ul>
            {!finding.evidence.length && <p>No evidence references supplied.</p>}
          </section>
        </div>
        <div className={`finding-ai source-${finding.source}`}>
          <p className="source-tag">{sourceLabels[finding.source]}</p>
          <section>
            <h4>Interpretation</h4>
            <p>{finding.interpretation || "No interpretation supplied."}</p>
          </section>
          <section>
            <h4>Suggested investigation</h4>
            <p>{finding.suggested_investigation || "No investigation supplied."}</p>
          </section>
        </div>
      </div>
    </article>
  );
}
