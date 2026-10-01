import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent.escalation import make_escalator
from app.analysis.synthesis import synthesize
from app.api import health, runs
from app.browser.guards import TargetRejected
from app.orchestrator.run_manager import RunConflict, RunNotFound, manager
from app.browser.pool import pool
from app.config import BACKEND_DIR, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mimic")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch Chromium in the background so /health answers immediately during cold start
    # (frontend shows "Initializing…" until browser_ready flips).
    browser_task = asyncio.create_task(pool.start())
    manager.escalator_factory = lambda run_id: make_escalator(run_id, manager.buses[run_id])
    manager.synthesizer = synthesize
    await manager.recover_orphans()
    yield
    browser_task.cancel()
    await pool.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MIMIC × GhostQA", version=settings.version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(runs.router)

    @app.exception_handler(RunNotFound)
    async def _not_found(_: Request, exc: RunNotFound):
        return JSONResponse({"detail": f"Run {exc} not found."}, status_code=404)

    @app.exception_handler(RunConflict)
    async def _conflict(_: Request, exc: RunConflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(TargetRejected)
    async def _bad_target(_: Request, exc: TargetRejected):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ValueError)
    async def _bad_value(_: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)
    app.mount("/demo", StaticFiles(directory=BACKEND_DIR / "demo_site", html=True), name="demo")
    return app


app = create_app()
