"""Async SQLAlchemy engine & session factory for PostgreSQL, plus a Valkey client.

Usage::

    from backend.core.database import get_session, get_valkey

    async with get_session() as session:
        result = await session.execute(text("SELECT 1"))

    valkey = await get_valkey()
    await valkey.set("key", "value")


User / auth / chat operations now live in ``backend/repositories/``:

* ``user_repo`` — ``get_by_id``, ``create``, ``list_active``, etc.
* ``auth_token_repo`` — ``create_token``, ``resolve_token``, ``revoke_token``
* ``chat_repo`` — ``save_message``, ``get_session_messages``, ``list_sessions``, etc.

Business logic lives in ``backend/services/``.
"""

from __future__ import annotations

from typing import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings
from backend.core.models import Base
# Import RAG models so they are registered with Base.metadata for create_all
from backend.db.models import RAGDocument, SyncLog, SyncSource, ChatFile  # noqa: F401

# ── PostgreSQL (SQLAlchemy async) ──────────────────────────────────────────

_engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    echo=settings.debug,
)

_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables if they don't exist, then apply missing-column migrations.

    Safe to call repeatedly — uses ``IF NOT EXISTS`` for columns and tables.
    """
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ── Migrations: add columns that may be missing on existing tables ──
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(128)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS team VARCHAR(100)",
        ]
        for stmt in migrations:
            await conn.execute(text(stmt))


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
            await session.commit()  # required — no auto-commit

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
