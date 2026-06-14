"""Repository for auth token operations (Valkey).

Usage::

    from backend.repositories.auth_token_repo import create_token, resolve_token

    token = await create_token(valkey, "user-uuid")
    user_id = await resolve_token(valkey, token)
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

_AUTH_TOKEN_KEY = "auth_token:{token}"
_AUTH_TOKEN_TTL = 86400 * 7  # 7 days


async def create_token(valkey: Redis, user_id: str) -> str:
    """Create an auth token for a user, stored in Valkey with TTL.

    Returns the token string.
    """
    token = uuid.uuid4().hex
    key = _AUTH_TOKEN_KEY.format(token=token)
    await valkey.setex(key, _AUTH_TOKEN_TTL, user_id)
    return token


async def resolve_token(valkey: Redis, token: str) -> str | None:
    """Resolve an auth token to a user_id string, or ``None`` if invalid/expired."""
    key = _AUTH_TOKEN_KEY.format(token=token)
    return await valkey.get(key)


async def revoke_token(valkey: Redis, token: str) -> None:
    """Delete an auth token (logout)."""
    key = _AUTH_TOKEN_KEY.format(token=token)
    await valkey.delete(key)
