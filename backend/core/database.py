"""Async SQLAlchemy engine & session factory for PostgreSQL, plus a Valkey client.

Usage::

    from backend.core.database import get_session, get_valkey

    async with get_session() as session:
        result = await session.execute(text("SELECT 1"))

    valkey = await get_valkey()
    await valkey.set("key", "value")


Chat persistence (Valkey)::

    from backend.core.database import save_message, get_session_messages

    await save_message("session-1", "user", "Hello!")
    messages = await get_session_messages("session-1")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
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


# ── Chat persistence (Valkey) ─────────────────────────────────────────────

_MESSAGES_KEY = "chat:{session_id}:messages"
_SESSIONS_SET = "chat:sessions"


async def save_message(
    session_id: str,
    role: str,
    content: str,
    valkey: Redis | None = None,
) -> None:
    """Append a chat message to the session history in Valkey."""
    if valkey is None:
        valkey = await get_valkey()

    msg = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    key = _MESSAGES_KEY.format(session_id=session_id)
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.rpush(key, json.dumps(msg))
        pipe.sadd(_SESSIONS_SET, session_id)
        await pipe.execute()


async def get_session_messages(
    session_id: str,
    valkey: Redis | None = None,
) -> list[dict[str, str]]:
    """Return all messages for a session as a list of dicts.

    Each message has keys ``role``, ``content``, ``timestamp``.
    Returns an empty list if the session does not exist.
    """
    if valkey is None:
        valkey = await get_valkey()

    key = _MESSAGES_KEY.format(session_id=session_id)
    raw = await valkey.lrange(key, 0, -1)
    return [json.loads(item) for item in raw]


async def list_sessions(
    valkey: Redis | None = None,
) -> list[str]:
    """Return all known session IDs."""
    if valkey is None:
        valkey = await get_valkey()

    return sorted(await valkey.smembers(_SESSIONS_SET))


async def delete_session(
    session_id: str,
    valkey: Redis | None = None,
) -> None:
    """Delete a session and its messages from Valkey."""
    if valkey is None:
        valkey = await get_valkey()

    key = _MESSAGES_KEY.format(session_id=session_id)
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.srem(_SESSIONS_SET, session_id)
        await pipe.execute()
