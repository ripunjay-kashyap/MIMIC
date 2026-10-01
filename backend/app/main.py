import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health
from app.browser.pool import pool
from app.config import BACKEND_DIR, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mimic")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch Chromium in the background so /health answers immediately during cold start
    # (frontend shows "Initializing…" until browser_ready flips).
    browser_task = asyncio.create_task(pool.start())
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
    app.mount("/demo", StaticFiles(directory=BACKEND_DIR / "demo_site", html=True), name="demo")
    return app


app = create_app()
