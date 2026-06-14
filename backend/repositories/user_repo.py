"""Repository for User CRUD operations (PostgreSQL).

Usage::

    from backend.repositories.user_repo import create_user, get_user

    user = await create_user(session, username="alice", display_name="Alice")
    user = await get_user(session, user.id)
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Get a user by UUID. Returns ``None`` if not found."""
    return await session.get(User, user_id)


async def get_by_username(
    session: AsyncSession,
    username: str,
) -> User | None:
    """Get a user by username. Returns ``None`` if not found."""
    result = await session.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    role: str = "user",
    team: str | None = None,
) -> User:
    """Create a new user."""
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


async def create_with_password(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
    team: str | None = None,
) -> User:
    """Create a new user with a hashed password."""
    user = User(
        username=username,
        display_name=display_name,
        role=role,
        team=team,
    )
    user.set_password(password)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def list_active(
    session: AsyncSession,
) -> list[User]:
    """Return all active users ordered by username."""
    result = await session.execute(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.username)
    )
    return list(result.scalars().all())


async def list_all(
    session: AsyncSession,
) -> list[User]:
    """Return **all** users ordered by created_at descending."""
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


async def count_all(
    session: AsyncSession,
) -> int:
    """Return the total number of users (including inactive)."""
    from sqlalchemy import func as sa_func

    result = await session.execute(sa_func.count(User.id))
    return result.scalar() or 0


async def update(
    session: AsyncSession,
    user_id: uuid.UUID,
    **kwargs: str | bool | None,
) -> User | None:
    """Update user fields. Pass ``display_name``, ``role``, ``is_active``, etc.

    Returns the updated user, or ``None`` if not found.
    """
    user = await session.get(User, user_id)
    if user is None:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)
    await session.flush()
    await session.refresh(user)
    return user


async def delete(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    """Delete a user by UUID. Returns ``True`` if deleted, ``False`` if not found."""
    user = await session.get(User, user_id)
    if user is None:
        return False
    await session.delete(user)
    await session.flush()
    return True
