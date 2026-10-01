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


@app.function(
    image=image,
    secrets=[modal.Secret.from_dotenv(BACKEND_DIR)],
    # Production overrides of local-dev defaults in .env.
    env={
        "IN_CONTAINER": "1",  # Chromium runs as root in the container -> --no-sandbox
        "ALLOW_LOCAL_TARGETS": "false",
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
