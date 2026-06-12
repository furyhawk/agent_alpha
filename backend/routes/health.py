"""Health-check endpoint — reports status of the API, database, and cache."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.core.database import get_valkey, open_session

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check() -> dict[str, str]:
    """Return API, database, and Valkey health status."""
    result: dict[str, str] = {"status": "ok"}

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    try:
        async with open_session() as session:
            await session.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception as exc:
        result["database"] = f"error: {exc}"
        result["status"] = "degraded"

    # ── Valkey / Redis ────────────────────────────────────────────────────
    try:
        valkey = await get_valkey()
        await valkey.ping()
        result["cache"] = "ok"
    except Exception as exc:
        result["cache"] = f"error: {exc}"
        result["status"] = "degraded"

    return result
