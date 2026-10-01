"""Run ONE persona against a target and print its journey.

    .venv/bin/python scripts/run_one.py --persona power                       # real Groq, local demo site
    .venv/bin/python scripts/run_one.py --persona impatient --fake            # scripted, zero quota
    .venv/bin/python scripts/run_one.py --persona cautious --target https://.../demo/
"""

import argparse
import asyncio
import functools
import http.server
import os
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def serve_demo() -> str:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    root = BACKEND / "_serve"
    root.mkdir(exist_ok=True)
    link = root / "demo"
    if not link.exists():
        link.symlink_to(BACKEND / "demo_site")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/demo/"


async def main(args) -> None:
    if args.fake:
        os.environ["LLM_MODE"] = "fake"
    from app.agent.graph import PersonaRunContext, run_persona
    from app.agent.sinks import MemorySink
    from app.browser.pool import BrowserPool
    from app.models.schemas import SuccessCriteria
    from app.personas.cohort import generate_cohort, milestones_for

    target = args.target or serve_demo()
    persona = next(p for p in generate_cohort(args.goal) if p.persona_type == args.persona)
    if args.model:
        persona = persona.model_copy(update={"llm_model": args.model})
    sink = MemorySink(f"local-{int(time.time())}", screenshot_dir=BACKEND / "screenshots", echo=True)
    pool = BrowserPool()
    await pool.start()
    t0 = time.monotonic()
    async with pool.session(persona.persona_id, target, device=persona.device) as session:
        final = await run_persona(PersonaRunContext(
            run_id=sink.run_id, persona=persona, session=session, sink=sink,
            success_criteria=SuccessCriteria(url_contains=args.success), milestones=milestones_for(target)))
    await pool.stop()
    toks = [e.payload.get("tokens", {}) for e in sink.events if e.type == "decision"]
    total = sum(t.get("prompt", 0) + t.get("completion", 0) for t in toks)
    print(f"\nRESULT {final.task_status} in {final.action_count} actions, {time.monotonic() - t0:.1f}s, "
          f"{len(toks)} decisions, {total} tokens (~{total // max(1, len(toks))}/call), model {persona.llm_model}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="power")
    ap.add_argument("--target")
    ap.add_argument("--goal", default="Choose a health insurance plan, complete onboarding, and reach the policy confirmation page.")
    ap.add_argument("--success", default="confirmed")
    ap.add_argument("--model")
    ap.add_argument("--fake", action="store_true")
    asyncio.run(main(ap.parse_args()))
