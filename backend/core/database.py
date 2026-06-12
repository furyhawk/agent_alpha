"""Async SQLAlchemy engine & session factory for PostgreSQL, plus a Valkey client.

Usage::

    from backend.core.database import get_session, get_valkey

    async with get_session() as session:
        result = await session.execute(text("SELECT 1"))

    valkey = await get_valkey()
    await valkey.set("key", "value")
"""

from __future__ import annotations

from typing import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings

# ── PostgreSQL (SQLAlchemy async) ──────────────────────────────────────────

_engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session (for FastAPI dependency injection)."""
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def open_session() -> AsyncSession:
    """Return a standalone async session (for health checks, scripts, etc.).

    The caller uses ``async with`` to enter/exit::

        async with open_session() as session:
            await session.execute(...)

    The session is automatically closed on exit of the ``async with`` block.
    """
    return _session_factory()


# ── Valkey (Redis-compatible) ─────────────────────────────────────────────

_valkey: Redis | None = None


async def get_valkey() -> Redis:
    """Return a shared Valkey (Redis) async client connection."""
    global _valkey
    if _valkey is None:
        _valkey = Redis.from_url(settings.valkey_url, decode_responses=True)
    return _valkey


async def close_valkey() -> None:
    """Close the Valkey connection pool (call on shutdown)."""
    global _valkey
    if _valkey is not None:
        await _valkey.aclose()
        _valkey = None


async def close_engine() -> None:
    """Dispose the SQLAlchemy engine (call on shutdown)."""
    await _engine.dispose()
