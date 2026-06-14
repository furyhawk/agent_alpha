"""Authentication service — login, register, token management.

Usage::

    service = AuthService(db, valkey)
    token = await service.login("alice", "secret123")
    user_id = await service.resolve_token(token)
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.repositories import auth_token_repo, user_repo
from backend.services.user_service import UserService


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession, valkey: Redis):
        self.db = db
        self.valkey = valkey
        self._user_service = UserService(db)

    async def register(
        self,
        *,
        username: str,
        display_name: str,
        password: str,
        role: str = "user",
        team: str | None = None,
    ) -> tuple[object, str]:
        """Register a new user and return (user, token).

        The first user to register is automatically assigned the ``admin`` role.
        """
        total = await user_repo.count_all(self.db)
        effective_role = "admin" if total == 0 else role

        user = await user_repo.create_with_password(
            self.db,
            username=username,
            display_name=display_name,
            password=password,
            role=effective_role,
            team=team,
        )

        token = await auth_token_repo.create_token(self.valkey, str(user.id))
        return user, token

    async def login(self, username: str, password: str) -> tuple[object, str] | None:
        """Authenticate a user and return (user, token), or ``None`` on failure."""
        user = await self._user_service.authenticate(username, password)
        if user is None:
            return None
        token = await auth_token_repo.create_token(self.valkey, str(user.id))
        return user, token

    async def resolve_token(self, token: str) -> str | None:
        """Resolve a token to a user_id string, or ``None`` if invalid/expired."""
        return await auth_token_repo.resolve_token(self.valkey, token)

    async def logout(self, token: str) -> None:
        """Revoke an auth token."""
        await auth_token_repo.revoke_token(self.valkey, token)
