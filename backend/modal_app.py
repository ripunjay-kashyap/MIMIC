"""Modal deployment for the MIMIC backend.

Deploy (from backend/):   .venv/bin/modal deploy modal_app.py
Stop after judging:       .venv/bin/modal app stop mimic-backend

One always-on container (min=max=1) so in-memory run state, the event bus and SSE streams
all live in a single process. Secrets are read from the local backend/.env at deploy time.
"""

from pathlib import Path

import modal

BACKEND_DIR = Path(__file__).resolve().parent

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(BACKEND_DIR / "requirements.txt"))
    .run_commands("playwright install --with-deps chromium")
    .add_local_dir(BACKEND_DIR / "demo_site", remote_path="/root/demo_site")
    .add_local_python_source("app")
)

app = modal.App("mimic-backend")

PUBLIC_URL = "https://ripun-j-kashyap--mimic-backend-web.modal.run"
DEMO_HOST = "ripun-j-kashyap--mimic-backend-web.modal.run"


@app.function(
    image=image,
    secrets=[modal.Secret.from_dotenv(BACKEND_DIR)],
    # Production overrides of local-dev defaults in .env.
    env={
        "IN_CONTAINER": "1",  # Chromium runs as root in the container -> --no-sandbox
        "ALLOW_LOCAL_TARGETS": "false",
        "DEMO_TARGET_HOSTS": DEMO_HOST,
    },
    cpu=1.0,  # 1 physical core = 2 vCPU
    memory=4096,
    min_containers=1,
    max_containers=1,
    timeout=3600,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    from app.main import app as fastapi_app

    return fastapi_app


@app.function(image=image, env={"IN_CONTAINER": "1", "DEMO_TARGET_HOSTS": DEMO_HOST}, cpu=1.0, memory=4096, timeout=300)
async def smoke(target: str = PUBLIC_URL + "/demo/") -> dict:
    """One-off check that Chromium can browse inside Modal: `modal run modal_app.py::smoke`."""
    import time

    from app.browser.actions import execute
    from app.browser.pool import BrowserPool
    from app.models.schemas import AgentAction

    pool = BrowserPool()
    t0 = time.monotonic()
    await pool.start()
    out = {"launch_s": round(time.monotonic() - t0, 2)}
    async with pool.session("smoke", target, device="mobile") as s:
        await s.goto_start()
        obs = await s.observe()
        quote = next(e.id for e in obs.elements if e.label == "Get a Quote")
        r = await execute(s, AgentAction(action="click", element_id=quote))
        obs2 = await s.observe()
        shot = await s.screenshot()
        out |= {"start_path": obs.path, "elements": len(obs.elements), "click_ok": r.ok,
                "after_path": obs2.path, "screenshot_kb": len(shot) // 1024, "demo_target": s.demo_target}
    await pool.stop()
    return out


@app.local_entrypoint()
def main():
    print(smoke.remote())
