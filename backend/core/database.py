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


User management::

    from backend.core.database import create_user, get_user, list_users

    user = await create_user("alice", "Alice", role="admin")
    user = await get_user(user.id)
    users = await list_users()
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings
from backend.core.models import Base, User

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


async def init_db() -> None:
    """Create all tables if they don't exist (call on startup)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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


# ── User CRUD (PostgreSQL via SQLAlchemy) ─────────────────────────────────


async def create_user(
    username: str,
    display_name: str,
    role: str = "user",
    team: str | None = None,
    session: AsyncSession | None = None,
) -> User:
    """Create a new user. Default role is ``user``.

    Roles: ``admin``, ``user``, ``viewer``
    """
    if session is None:
        async with _session_factory() as session:
            user = User(
                username=username,
                display_name=display_name,
                role=role,
                team=team,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    else:
        user = User(
            username=username,
            display_name=display_name,
            role=role,
            team=team,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession | None = None,
) -> User | None:
    """Return a user by their UUID, or ``None`` if not found."""
    if session is None:
        async with _session_factory() as session:
            return await session.get(User, user_id)
    return await session.get(User, user_id)


async def get_user_by_username(
    username: str,
    session: AsyncSession | None = None,
) -> User | None:
    """Return a user by their username, or ``None`` if not found."""
    if session is None:
        async with _session_factory() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            return result.scalar_one_or_none()
    result = await session.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def list_users(
    session: AsyncSession | None = None,
) -> list[User]:
    """Return all active users ordered by username."""
    if session is None:
        async with _session_factory() as session:
            result = await session.execute(
                select(User)
                .where(User.is_active.is_(True))
                .order_by(User.username)
            )
            return list(result.scalars().all())
    result = await session.execute(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.username)
    )
    return list(result.scalars().all())


async def update_user(
    user_id: uuid.UUID,
    session: AsyncSession,
    **kwargs: str | bool | None,
) -> User | None:
    """Update user fields. Pass ``display_name``, ``role``, ``is_active``, etc."""
    user = await session.get(User, user_id)
    if user is None:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)
    await session.flush()
    await session.refresh(user)
    return user


# ── Chat persistence (Valkey) ─────────────────────────────────────────────

_MESSAGES_KEY = "chat:{session_id}:messages"
_SESSIONS_SET = "chat:sessions"
_SESSION_USER_KEY = "chat:{session_id}:user_id"
_USER_SESSIONS_KEY = "user:{user_id}:sessions"


async def save_message(
    session_id: str,
    role: str,
    content: str,
    valkey: Redis | None = None,
    user_id: str | None = None,
) -> None:
    """Append a chat message to the session history in Valkey.

    If ``user_id`` is provided, the session is linked to that user.
    """
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
        if user_id is not None:
            pipe.set(
                _SESSION_USER_KEY.format(session_id=session_id),
                user_id,
            )
            pipe.sadd(
                _USER_SESSIONS_KEY.format(user_id=user_id),
                session_id,
            )
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


async def get_session_user_id(
    session_id: str,
    valkey: Redis | None = None,
) -> str | None:
    """Return the user_id associated with a session, or ``None``."""
    if valkey is None:
        valkey = await get_valkey()

    key = _SESSION_USER_KEY.format(session_id=session_id)
    return await valkey.get(key)


async def list_sessions(
    valkey: Redis | None = None,
) -> list[str]:
    """Return all known session IDs."""
    if valkey is None:
        valkey = await get_valkey()

    return sorted(await valkey.smembers(_SESSIONS_SET))


async def list_user_sessions(
    user_id: str,
    valkey: Redis | None = None,
) -> list[str]:
    """Return all session IDs for a given user."""
    if valkey is None:
        valkey = await get_valkey()

    key = _USER_SESSIONS_KEY.format(user_id=user_id)
    return sorted(await valkey.smembers(key))


async def delete_session(
    session_id: str,
    valkey: Redis | None = None,
) -> None:
    """Delete a session and its messages from Valkey."""
    if valkey is None:
        valkey = await get_valkey()

    # Remove from user's session set if linked.
    user_id = await get_session_user_id(session_id, valkey=valkey)
    user_sessions_key = (
        _USER_SESSIONS_KEY.format(user_id=user_id) if user_id else None
    )

    key = _MESSAGES_KEY.format(session_id=session_id)
    session_user_key = _SESSION_USER_KEY.format(session_id=session_id)
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.delete(session_user_key)
        pipe.srem(_SESSIONS_SET, session_id)
        if user_sessions_key is not None:
            pipe.srem(user_sessions_key, session_id)
        await pipe.execute()
