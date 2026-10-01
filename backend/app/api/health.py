import asyncio

from fastapi import APIRouter

from app.browser.pool import pool
from app.config import get_settings
from app.db.client import db_ready
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
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
