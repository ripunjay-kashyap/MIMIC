"use client";
import Link from "next/link";
import type { CSSProperties } from "react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { PersonaSprite, personaNames, personaStyle, personaTypes, type PersonaType } from "@/components/PersonaSprite";
import { API_URL, createRun } from "@/lib/api";
import { DEMO_GOAL, MOCK } from "@/lib/config";
import { errorMessage } from "@/lib/errors";

// Product copy describing each behavior template (not run data).
const intros: Record<PersonaType, string> = {
  impatient: "Wants it done fast. Clicks the most obvious button and leaves when blocked.",
  low_literacy: "New to web apps. Needs plain labels and a clear next step.",
  power: "Takes the shortest path and skips anything optional.",
  cautious: "Reads the fine print on fees, consent and payment.",
  explorer: "Compares options, opens side paths and often backtracks.",
  chaos: "Odd inputs, repeated clicks and strange ordering.",
};

export default function Setup() {
  const router = useRouter();
  const [target, setTarget] = useState(""); const [goal, setGoal] = useState("");
  const [urlContains, setUrlContains] = useState(""); const [textVisible, setTextVisible] = useState("");
  const [authorized, setAuthorized] = useState(false); const [pending, setPending] = useState(false); const [error, setError] = useState<string | null>(null);
  function prefill() { setTarget(`${API_URL}/demo/`); setGoal(DEMO_GOAL); setUrlContains("confirmed"); setTextVisible(""); setError(null); }
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault(); if (pending) return;
    setPending(true); setError(null);
    try {
      const parsed = new URL(target);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("Use an http:// or https:// target URL.");
      if (!authorized) throw new Error("Please confirm you are authorized to test this target.");
      if (!goal.trim()) throw new Error("Enter a goal for the synthetic users.");
      const criteria = { ...(urlContains.trim() ? { url_contains: urlContains.trim() } : {}), ...(textVisible.trim() ? { text_visible: textVisible.trim() } : {}) };
      const run = await createRun({ target_url: target.trim(), goal: goal.trim(), authorized: true, ...(Object.keys(criteria).length ? { success_criteria: criteria } : {}) });
      router.push(`/runs/${run.run_id}`);
    } catch (error) { setError(errorMessage(error)); setPending(false); }
  }
  return <>
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-copy">
        <p className="kicker">Synthetic usability testing</p>
        <h1 id="hero-title" className="display">Your first users <em>shouldn’t be your testers.</em></h1>
        <p className="lead">Give six AI personas the same goal on your website, each in its own browser. See where they go and where they get stuck, then replay the steps behind every finding.</p>
        <ul className="cast" aria-label="The six personas">
          {personaTypes.map((type, index) => (
            <li key={type} style={{ "--i": index } as CSSProperties}>
              <PersonaSprite type={type} size={64} />
              <span>{personaNames[type]}</span>
            </li>
          ))}
        </ul>
        <p className="hero-link">
          <Link className="button secondary" href="/case-study" prefetch={false}>{MOCK ? "Watch a mock run" : "See a real recorded run"} <span aria-hidden="true">→</span></Link>
        </p>
      </div>
      <section className="setup-card" aria-labelledby="setup-title">
        <div className="setup-card-head">
          <h2 id="setup-title">Set up a run</h2>
          <button type="button" className="button secondary small" onClick={prefill} disabled={pending}>Prefill demo</button>
        </div>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="target">Target URL</label>
            <input id="target" type="url" placeholder="https://your-site.example" value={target} onChange={e => setTarget(e.target.value)} required disabled={pending} />
          </div>
          <div className="field">
            <label htmlFor="goal">Goal</label>
            <textarea id="goal" rows={3} placeholder="What should each persona try to complete?" value={goal} onChange={e => setGoal(e.target.value)} required disabled={pending} />
          </div>
          <fieldset disabled={pending}>
            <legend>Success criteria <span>optional</span></legend>
            <div className="criteria">
              <div className="field">
                <label htmlFor="url-contains">Success when URL contains</label>
                <input id="url-contains" value={urlContains} onChange={e => setUrlContains(e.target.value)} placeholder="e.g. confirmed" />
              </div>
              <div className="field">
                <label htmlFor="text-visible">Success when text visible</label>
                <input id="text-visible" value={textVisible} onChange={e => setTextVisible(e.target.value)} placeholder="e.g. Policy issued" />
              </div>
            </div>
          </fieldset>
          <label className="checkbox-label" htmlFor="authorized">
            <input id="authorized" type="checkbox" checked={authorized} onChange={e => setAuthorized(e.target.checked)} required disabled={pending} />
            I am authorized to test this target
          </label>
          {error && <p className="error-panel" role="alert">{error}</p>}
          <button className="button wide" type="submit" disabled={pending}>{pending ? "Creating run…" : "Create run"}</button>
        </form>
      </section>
    </section>

    <section className="meet" aria-labelledby="meet-title">
      <div className="section-head">
        <h2 id="meet-title">Meet the six</h2>
        <p>Each has its own patience, reading tolerance and appetite for risk. They are controlled behavioral simulations, not predictions about demographic groups.</p>
      </div>
      <ul className="meet-grid">
        {personaTypes.map(type => (
          <li key={type} style={personaStyle(type)}>
            <PersonaSprite type={type} size={56} />
            <h3>{personaNames[type]}</h3>
            <p>{intros[type]}</p>
          </li>
        ))}
      </ul>
    </section>

    <section className="how" aria-labelledby="how-title">
      <div className="section-head">
        <h2 id="how-title">How a run works</h2>
      </div>
      <ol className="steps">
        <li><h3>Set a goal</h3><p>Point the cohort at a site you are allowed to test, and say what success looks like.</p></li>
        <li><h3>Watch them try</h3><p>Six isolated browsers work in parallel. The journey map shows every page they reach, as it happens.</p></li>
        <li><h3>Follow the evidence</h3><p>Findings keep what was observed apart from what it might mean, and each links to the recorded step.</p></li>
      </ol>
    </section>
  </>;
}
