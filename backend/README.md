# MIMIC backend

FastAPI + LangGraph + Playwright, deployed on Modal (`modal_app.py`). See the root `README.md` for an overview.

```
app/
  api/            HTTP: /health, /runs (+ SSE events, report, journey), rate limits
  orchestrator/   run lifecycle + per-run event bus (SSE fan-out, batched Supabase writes)
  agent/          LangGraph persona loop, prompts, visual escalation, event sinks
  personas/       templates, cohort, deterministic state engine, behaviour policies
  browser/        Chromium pool, isolated sessions, observation, actions, safety guards
  llm/            model router, Groq client, Gemini pool, fake LLM, rate limiter
  analysis/       metrics, friction detectors, clustering, LLM synthesis
  db/             Supabase/in-memory repository, SQL migration
demo_site/        seeded target (SurakshaSetu) + SEEDED_ISSUES.json
scripts/          check_models.py, run_one.py, evaluate_run.py, prewarm.sh
```

Useful commands:

```bash
.venv/bin/pytest -q                                   # all tests (~3–4 min)
.venv/bin/python scripts/run_one.py --persona power --fake   # one persona, local demo site
.venv/bin/modal deploy modal_app.py                   # deploy
.venv/bin/modal run modal_app.py                      # remote browser smoke check
bash scripts/prewarm.sh                               # demo-day readiness + quota
```

`Dockerfile` is kept for portability (any container host); production uses `modal_app.py`.
