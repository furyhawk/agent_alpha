"""Repository for chat session/message operations (Valkey).

Usage::

    from backend.repositories.chat_repo import save_message, get_session_messages

    await save_message(valkey, "session-1", "user", "Hello!")
    msgs = await get_session_messages(valkey, "session-1")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from redis.asyncio import Redis

_MESSAGES_KEY = "chat:{session_id}:messages"
_SESSIONS_SET = "chat:sessions"
_SESSION_USER_KEY = "chat:{session_id}:user_id"
_SESSION_TITLE_KEY = "chat:{session_id}:title"
_SESSION_CREATED_KEY = "chat:{session_id}:created_at"
_USER_SESSIONS_KEY = "user:{user_id}:sessions"


async def save_message(
    valkey: Redis,
    session_id: str,
    role: str,
    content: str,
    user_id: str | None = None,
) -> None:
    """Append a chat message to the session history in Valkey.

    If ``user_id`` is provided, the session is linked to that user.
    """
    now = datetime.now(timezone.utc)
    msg = {
        "role": role,
        "content": content,
        "timestamp": now.isoformat(),
    }
    key = _MESSAGES_KEY.format(session_id=session_id)
    created_key = _SESSION_CREATED_KEY.format(session_id=session_id)
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.rpush(key, json.dumps(msg))
        pipe.sadd(_SESSIONS_SET, session_id)
        # Set created_at only for the first message (NX = set if not exists)
        pipe.setnx(created_key, now.isoformat())
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
    valkey: Redis,
    session_id: str,
) -> list[dict[str, str]]:
    """Return all messages for a session as a list of dicts.

    Each message has keys ``role``, ``content``, ``timestamp``.
    Returns an empty list if the session does not exist.
    """
    key = _MESSAGES_KEY.format(session_id=session_id)
    raw = await valkey.lrange(key, 0, -1)
    return [json.loads(item) for item in raw]


async def get_session_user_id(
    valkey: Redis,
    session_id: str,
) -> str | None:
    """Return the user_id associated with a session, or ``None``."""
    key = _SESSION_USER_KEY.format(session_id=session_id)
    return await valkey.get(key)


async def set_session_title(
    valkey: Redis,
    session_id: str,
    title: str,
) -> None:
    """Store a short human-readable title for a session."""
    key = _SESSION_TITLE_KEY.format(session_id=session_id)
    await valkey.set(key, title)


async def get_session_title(
    valkey: Redis,
    session_id: str,
) -> str | None:
    """Return the title for a session, or ``None`` if not set."""
    key = _SESSION_TITLE_KEY.format(session_id=session_id)
    return await valkey.get(key)


async def get_session_created_at(
    valkey: Redis,
    session_id: str,
) -> str | None:
    """Return the ISO-8601 creation timestamp for a session, or ``None``."""
    key = _SESSION_CREATED_KEY.format(session_id=session_id)
    return await valkey.get(key)


async def list_sessions(
    valkey: Redis,
) -> list[str]:
    """Return all known session IDs."""
    return sorted(await valkey.smembers(_SESSIONS_SET))


async def list_user_sessions(
    valkey: Redis,
    user_id: str,
) -> list[str]:
    """Return all session IDs for a given user."""
    key = _USER_SESSIONS_KEY.format(user_id=user_id)
    return sorted(await valkey.smembers(key))


async def delete_session(
    valkey: Redis,
    session_id: str,
) -> None:
    """Delete a session and its messages from Valkey."""
    # Remove from user's session set if linked.
    user_id = await get_session_user_id(valkey, session_id)
    user_sessions_key = (
        _USER_SESSIONS_KEY.format(user_id=user_id) if user_id else None
    )

    key = _MESSAGES_KEY.format(session_id=session_id)
    session_user_key = _SESSION_USER_KEY.format(session_id=session_id)
    session_title_key = _SESSION_TITLE_KEY.format(session_id=session_id)
    session_created_key = _SESSION_CREATED_KEY.format(session_id=session_id)
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.delete(session_user_key)
        pipe.delete(session_title_key)
        pipe.delete(session_created_key)
        pipe.srem(_SESSIONS_SET, session_id)
        if user_sessions_key is not None:
            pipe.srem(user_sessions_key, session_id)
        await pipe.execute()
