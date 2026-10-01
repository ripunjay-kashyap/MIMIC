"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL, createRun } from "@/lib/api";
import { DEMO_GOAL } from "@/lib/config";
import { errorMessage } from "@/lib/errors";
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
  return <><div className="page-heading"><p className="eyebrow">01 / Configure a test</p><h1>Ship to synthetic users<br className="desktop-break" /> before real users.</h1><p className="lead">Give six independent personas the same goal. See where their journeys diverge, then inspect the evidence.</p></div>
    <div className="setup-grid"><section className="panel setup-panel"><div className="section-heading"><h2>Set up a run</h2><button type="button" className="button secondary" onClick={prefill} disabled={pending}>Prefill demo</button></div>
      <form onSubmit={submit}><label htmlFor="target">Target URL</label><input id="target" type="url" placeholder="https://your-site.example" value={target} onChange={e => setTarget(e.target.value)} required disabled={pending} />
        <label htmlFor="goal">Goal</label><textarea id="goal" rows={4} placeholder="What should each persona try to complete?" value={goal} onChange={e => setGoal(e.target.value)} required disabled={pending} />
        <fieldset disabled={pending}><legend>Success criteria <span className="muted">· optional</span></legend><label htmlFor="url-contains">Success when URL contains</label><input id="url-contains" value={urlContains} onChange={e => setUrlContains(e.target.value)} placeholder="e.g. confirmed" /><label htmlFor="text-visible">Success when text visible</label><input id="text-visible" value={textVisible} onChange={e => setTextVisible(e.target.value)} placeholder="e.g. Policy issued" /></fieldset>
        <label className="checkbox-label" htmlFor="authorized"><input id="authorized" type="checkbox" checked={authorized} onChange={e => setAuthorized(e.target.checked)} required disabled={pending} />I am authorized to test this target</label>
        {error && <p className="error-panel" role="alert">{error}</p>}<button className="button" type="submit" disabled={pending}>{pending ? "Creating run…" : "Create run"}</button>
      </form></section><aside className="setup-aside"><p className="eyebrow">One goal. Six perspectives.</p><ol className="workflow"><li><strong>Review your cohort</strong><p>Understand each persona’s traits, limits and device before you deploy.</p></li><li><strong>Watch the journeys</strong><p>Follow decisions, progress and friction as each persona explores.</p></li><li><strong>Inspect the evidence</strong><p>Open findings and replay the exact steps behind them.</p></li></ol><p className="muted small">These are controlled behavioral simulations, not predictions about demographic groups.</p></aside></div></>;
}
