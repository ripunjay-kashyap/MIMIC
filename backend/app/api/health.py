import asyncio

from fastapi import APIRouter

from app.browser.pool import pool
from app.config import get_settings
from app.db.client import db_ready
from app.models.schemas import HealthResponse

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    try:
        db_ok = await asyncio.wait_for(db_ready(), timeout=3)
    except asyncio.TimeoutError:
        db_ok = False
    return HealthResponse(
        status="ok",
        version=settings.version,
        browser_ready=pool.ready,
        db_ready=db_ok,
        llm_mode=settings.llm_mode,
    )


@router.get("/health/quota")
async def quota() -> dict:
    """Remaining Gemini requests today per model (for demo-day checks). Counts only, no keys."""
    from app.llm.gemini_pool import gemini_pool

    pool = gemini_pool()
    await pool._load_counts()
    return {"gemini_remaining": pool.remaining(), "llm_mode": get_settings().llm_mode,
            "gemini_mode": get_settings().gemini_mode}
