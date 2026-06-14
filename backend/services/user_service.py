"""User management service — business logic for user CRUD.

Usage::

    service = UserService(db)
    user = await service.create(username="alice", display_name="Alice")
    user = await service.get_or_raise(user_id)
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundError
from backend.core.models import User
from backend.repositories import user_repo


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        username: str,
        display_name: str,
        role: str = "user",
        team: str | None = None,
    ) -> User:
        """Create a new user."""
        return await user_repo.create(
            self.db,
            username=username,
            display_name=display_name,
            role=role,
            team=team,
        )

    async def create_with_password(
        self,
        *,
        username: str,
        display_name: str,
        password: str,
        role: str = "user",
        team: str | None = None,
    ) -> User:
        """Create a new user with a hashed password."""
        return await user_repo.create_with_password(
            self.db,
            username=username,
            display_name=display_name,
            password=password,
            role=role,
            team=team,
        )

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get a user by UUID."""
        return await user_repo.get_by_id(self.db, user_id)

    async def get_or_raise(self, user_id: uuid.UUID) -> User:
        """Get a user by UUID or raise ``NotFoundError``."""
        user = await user_repo.get_by_id(self.db, user_id)
        if user is None:
            raise NotFoundError(
                message="User not found",
                details={"user_id": str(user_id)},
            )
        return user

    async def get_by_username(self, username: str) -> User | None:
        """Get a user by username."""
        return await user_repo.get_by_username(self.db, username)

    async def list_active(self) -> list[User]:
        """List all active users."""
        return await user_repo.list_active(self.db)

    async def list_all(self) -> list[User]:
        """List all users (including inactive)."""
        return await user_repo.list_all(self.db)

    async def count_all(self) -> int:
        """Return total user count."""
        return await user_repo.count_all(self.db)

    async def update(
        self,
        user_id: uuid.UUID,
        **kwargs: str | bool | None,
    ) -> User:
        """Update user fields. Raises ``NotFoundError`` if user does not exist."""
        user = await user_repo.update(self.db, user_id, **kwargs)
        if user is None:
            raise NotFoundError(
                message="User not found",
                details={"user_id": str(user_id)},
            )
        return user

    async def delete(self, user_id: uuid.UUID) -> None:
        """Delete a user. Raises ``NotFoundError`` if user does not exist."""
        deleted = await user_repo.delete(self.db, user_id)
        if not deleted:
            raise NotFoundError(
                message="User not found",
                details={"user_id": str(user_id)},
            )

    async def authenticate(self, username: str, password: str) -> User | None:
        """Verify username/password. Returns the User on success, ``None`` on failure.

        Also checks that the user is active.
        """
        user = await user_repo.get_by_username(self.db, username)
        if user is None or not user.is_active:
            return None
        if user.check_password(password):
            return user
        return None
