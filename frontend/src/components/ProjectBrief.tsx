// Server-rendered summary shown under the wake-up screen. It is in the initial HTML,
// so link previews, crawlers and LLMs that don't run JavaScript can read what MIMIC is.
const REPO = "https://github.com/ripunjay-kashyap/MIMIC";
const API = "https://ripun-j-kashyap--mimic-backend-web.modal.run";
const REPORT = "/runs/327ebf9a-51ef-485f-b8f6-44d083a27d81/report";
const TRACE = "https://smith.langchain.com/public/2542d900-ca97-4bee-9373-2d65a8eaaa8d/r";

export function ProjectBrief() {
  return <section className="brief" aria-labelledby="brief-title">
    <h2 id="brief-title">About MIMIC × Ghost</h2>
    <p><strong>Your first users shouldn’t be your testers.</strong> MIMIC is a multi-agent synthetic usability testing tool. It sends six AI personas (Impatient, Low digital literacy, Power user, Cautious, Explorer, Chaos) through your site in parallel, each in its own isolated Playwright browser with the same goal, such as “buy a policy”. It records every step, groups the friction they hit into evidence-backed findings, and lets you replay any persona’s journey screen by screen.</p>
    <h3>How it works</h3>
    <ul>
      <li>Each persona is a LangGraph loop: observe the page as compact text, pick one action from a numbered element menu (LLM, JSON), apply code-enforced persona behaviour, act with Playwright, update state with deterministic rules.</li>
      <li>Code owns state, the LLM owns choices: frustration, budgets and termination are plain Python, and success is checked against the user’s criteria, not claimed by the model.</li>
      <li>Findings come from 13 deterministic friction detectors over stored events, each linked to the events and screenshots behind it. Every finding is shown as Observed → Evidence → Interpretation → Suggested investigation.</li>
      <li>Models: Groq (qwen3.8-27b, gpt-oss-120b) and Gemini 3.5 Flash-Lite for decisions; Gemini Flash reads screenshots only when the text view isn’t enough. Stack: Next.js, FastAPI, LangGraph, Playwright, Supabase, Modal, Vercel, LangSmith.</li>
    </ul>
    <h3>Results from the recorded demo run</h3>
    <p>Tested against SurakshaSetu, a seeded health-insurance onboarding site with 13 documented usability defects (12 detectable from text and behaviour), so results are measured, not claimed. In 2 min 54 s: 2 personas reached the goal, 3 gave up, 1 ran out of actions; 5 different routes; 11 findings; 6 of 12 seeded defects found; 0 errors. Three of six personas gave up on the same mobile OTP page, which has two seeded defects. Across six scored runs, MIMIC found 42–83% of seeded defects.</p>
    <h3>Links</h3>
    <ul>
      <li><a href={REPO}>Source code and README (GitHub)</a></li>
      <li><a href="/case-study">Case study: one recorded run, told as a story</a></li>
      <li><a href={REPORT}>Full report of the recorded run</a></li>
      <li><a href={`${API}/docs`}>API documentation</a> · <a href={`${API}/demo/`}>Seeded demo site</a></li>
      <li><a href={TRACE}>Public LangSmith trace of one persona</a> · <a href="/llms.txt">llms.txt</a></li>
    </ul>
    <p className="muted">Authorized testing only. MIMIC does not predict real human behaviour; it simulates controlled behavioural assumptions to surface usability problems worth investigating with real users.</p>
  </section>;
}
