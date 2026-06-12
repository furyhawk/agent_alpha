"""User management API routes — CRUD for application users.

Each user has a ``role``: ``admin``, ``user``, or ``viewer``.
Sessions are associated with users for role-based access.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import (
    create_user,
    get_user,
    get_user_by_username,
    list_user_sessions,
    list_users,
    update_user,
)
from backend.core.dependencies import get_db_session

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Schemas ────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str
    display_name: str
    role: str = "user"
    team: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    team: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    team: str | None = None
    is_active: bool
    created_at: str
    updated_at: str


class UserSessionOut(BaseModel):
    session_id: str


# ── Helpers ────────────────────────────────────────────────────────────────


def _user_to_out(user: object) -> UserOut:
    """Convert a User ORM instance to a UserOut schema."""
    return UserOut(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        team=user.team,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("", response_model=UserOut, status_code=201)
async def create_user_endpoint(
    body: UserCreate,
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    """Create a new user."""
    # Check for duplicate username.
    existing = await get_user_by_username(body.username, session=session)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"User '{body.username}' already exists",
        )

    user = await create_user(
        username=body.username,
        display_name=body.display_name,
        role=body.role,
        team=body.team,
        session=session,
    )
    return _user_to_out(user)


@router.get("", response_model=list[UserOut])
async def list_users_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> list[UserOut]:
    """List all active users."""
    users = await list_users(session=session)
    return [_user_to_out(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
async def get_user_endpoint(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    """Get a user by their UUID."""
    user = await get_user(user_id, session=session)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user_endpoint(
    user_id: uuid.UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    """Update a user's display_name, role, or is_active."""
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    user = await update_user(user_id, session=session, **kwargs)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_out(user)


@router.get("/{user_id}/sessions", response_model=list[UserSessionOut])
async def user_sessions_endpoint(
    user_id: uuid.UUID,
) -> list[UserSessionOut]:
    """List all session IDs associated with a user."""
    session_ids = await list_user_sessions(str(user_id))
    return [UserSessionOut(session_id=sid) for sid in session_ids]
