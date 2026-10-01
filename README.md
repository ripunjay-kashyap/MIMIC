# MIMIC × Ghost

**Your first users shouldn't be your testers.**

MIMIC sends six AI personas with different behaviours through your site and shows you where they got stuck, with the evidence.

MIMIC deploys a cohort of six behaviourally distinct AI users onto a live website. Each one gets its own isolated browser, its own state, and the same goal ("buy a policy", "book an appointment"). They work in parallel, and MIMIC records every step, groups the friction they hit into evidence-backed findings, and lets you replay any persona's journey screen by screen.

It is built for **authorized exploratory usability testing**: staging sites, your own apps, explicitly permitted targets.

> MIMIC does not predict real human behaviour. It simulates controlled behavioural assumptions to surface usability problems worth investigating with real users.

---

## What it does

1. **Configure.** Enter a target URL and a goal (plus optional success criteria, such as "URL contains `confirmed`").
2. **Review the cohort.** Six personas, each with explicit traits, budgets and abandonment thresholds:

   | Persona | Behaviour enforced in code |
   |---|---|
   | Impatient | Small budget, low patience, never waits, quits early when blocked |
   | Low digital literacy | Only sees controls with visible text labels; error messages frustrate it more |
   | Power user | Shortest path, no browsing; its path length shows wasted steps |
   | Cautious | Must check fees and terms before committing on payment, OTP or consent pages |
   | Explorer | Opens secondary paths and backtracks without frustration |
   | Chaos | Edge-case inputs (`12345`, Devanagari digits, emoji…), double-clicks, going back mid-flow |

3. **Deploy the swarm.** Six parallel Playwright browser contexts with no shared cookies or storage. Every step streams live to the UI over SSE.
4. **Observe.** Live cards show each persona's page, action, in-character thought, frustration and progress.
5. **Report.** Deterministic metrics (completion rate, abandonment, average and median actions, unique paths) and findings split into **Observed → Evidence → Interpretation → Suggested investigation**.
6. **Replay.** Step by step: what the persona saw (the exact text it was given), what it decided and why, what happened, how its state changed, and screenshots.

## The agentic loop (Understand → Reason → Plan → Use Tools → Act → Deliver)

```
observe page ──► compact text: headings, messages, numbered element menu
     │
reason as persona ──► LLM picks ONE action from the menu (JSON); it cannot invent selectors
     │
persona policy ──► code-enforced behaviour (chaos inputs, cautious checks, …)
     │
act ──► Playwright: click / type / select / scroll / back / wait
     │
update state ──► deterministic rules: frustration, progress, failed attempts, budget
     │
continue │ success │ abandoned │ failed │ budget exhausted │ blocked by verification
```

**Code owns state, the LLM owns choices.** Counters, frustration, budgets and termination are pure Python. The model can't end its own journey early by claiming "done": success is checked against the criteria.

## Architecture

```
Next.js UI (Vercel) ──HTTPS + SSE──► FastAPI on Modal (one always-on container)
                                      ├─ Run orchestrator ── 6 × LangGraph persona loops
                                      ├─ Playwright: 1 Chromium, 6 isolated contexts
                                      ├─ Model router
                                      │    Groq (qwen3.8-27b, gpt-oss-120b) ─► routine decisions
                                      │    Gemini 3.5 Flash-Lite ──────────────► decisions + fallback
                                      │    Gemini 3.8 / 3.7 Flash ─────────────► screenshot reading, report wording
                                      ├─ Event bus ─► Supabase (runs, personas, events, findings, screenshots)
                                      └─ Analysis: metrics + 13 friction detectors + clustering
```

- **Visual escalation.** Screenshots go to Gemini only when the text view isn't enough (a persona is stuck, or the page has almost no controls). Each page is read once per run, at most 4 times per run, and the result is shared across personas.
- **Quota discipline.** Token-bucket rate limiting per model, spillover across models, and Gemini usage tracked per key and model (every request counts, including 503s).
- **Evidence first.** Findings come from deterministic detectors over stored events. The LLM only rewrites the interpretation text for findings that already exist; it cannot add findings or change evidence.

## Seeded demo target: SurakshaSetu

A fictional Indian health-insurance onboarding site (`backend/demo_site/`, served at `/demo/`) with **13 documented usability defects** (`SEEDED_ISSUES.json`): similarly worded call-to-action buttons, a dead-end article, unexplained insurance jargon, a form that accepts a 5-digit mobile number, generic "Invalid input" errors, an OTP that arrives silently after 3 s with the code hidden in footer text, an unnecessary confirmation step, unexplained "applicable charges*", a pre-ticked data-sharing consent box, a double-click that charges twice, and a mobile layout that hides the call-to-action below the fold.

`scripts/evaluate_run.py` scores a run's findings against this ground truth. In our first four real runs (during tuning) MIMIC found **6, 6, 8 and 10 of the 12** text- or behaviour-detectable defects; results vary run to run because the agents are LLM-driven.

## Safety

- An authorization checkbox is required for every run. Private, loopback and link-local targets are rejected (SSRF guard).
- Navigation is fenced to the target host. Irreversible actions ("Pay now", "Delete") are blocked on any target except our own demo site.
- CAPTCHA and Cloudflare challenges end the persona as `blocked_by_verification`. **There is no bypass.**
- Per-IP and global rate limits on starting runs. API keys live only in server-side environment variables.

## Run locally

```bash
# backend (Python 3.12)
cd backend
uv venv --python 3.12 .venv && uv pip install -r requirements-dev.txt --python .venv/bin/python
.venv/bin/playwright install chromium
cp .env.example .env            # add Groq / Gemini / Supabase keys
LLM_MODE=fake .venv/bin/uvicorn app.main:app --port 8000   # fake = scripted decisions, zero quota

# frontend
cd ../frontend && npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build && npx next start
```

Apply `backend/app/db/migrations/001_init.sql` in Supabase. Tests: `cd backend && .venv/bin/pytest -q`.

## Deploy

- Backend: `cd backend && .venv/bin/modal deploy modal_app.py` (secrets are read from `backend/.env` at deploy time).
- Frontend: Vercel, with `NEXT_PUBLIC_API_URL` set to the Modal URL.
- Before a demo: `bash backend/scripts/prewarm.sh`.

## What we claim, and what we don't

✅ Autonomous synthetic users can explore live product journeys. Different controlled behavioural policies produce different trajectories. Repeated friction can be detected across independent sessions. Every finding is replayable evidence.

❌ It does not predict exact human behaviour, does not replace user research, does not simulate demographics representatively, does not guarantee every issue is found, and must not be used on sites you aren't authorized to test.
