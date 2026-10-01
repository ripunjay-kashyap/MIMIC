import logging

from supabase import AsyncClient, acreate_client

from app.config import get_settings

log = logging.getLogger(__name__)

_client: AsyncClient | None = None


async def get_db() -> AsyncClient | None:
    """Shared async Supabase client, or None when Supabase isn't configured."""
    global _client
    settings = get_settings()
    if not settings.supabase_enabled:
        return None
    if _client is None:
        _client = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


async def db_ready() -> bool:
    db = await get_db()
    if db is None:
        return False
    try:
        await db.table("runs").select("id").limit(1).execute()
        return True
    except Exception as e:  # noqa: BLE001 - health check must never raise
        log.warning("db health check failed: %s", e)
        return False
