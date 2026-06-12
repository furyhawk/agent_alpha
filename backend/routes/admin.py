"""Admin dashboard API routes — system stats, user management, session overview.

All endpoints require ``Authorization: Bearer <token>`` with an ``admin`` role.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import (
    delete_session,
    delete_user as db_delete_user,
    get_admin_stats,
    get_session_messages,
    get_session_user_id,
    get_user,
    get_user_by_username,
    list_sessions,
    list_user_sessions,
    list_users,
    resolve_auth_token,
    update_user,
)
from backend.core.dependencies import get_db_session

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Admin auth dependency ──────────────────────────────────────────────────


async def require_admin(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> str:
    """Verify the request comes from an authenticated admin user.

    Returns the ``user_id`` string on success, raises 401/403 otherwise.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    user_id = await resolve_auth_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await get_user(uuid.UUID(user_id), session=session)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin role required",
        )

    return user_id


# ── Schemas ────────────────────────────────────────────────────────────────


class AdminStatsOut(BaseModel):
    total_users: int
    users_by_role: dict[str, int]
    users_by_active: dict[str, int]
    total_sessions: int


class AdminUserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    team: str | None = None
    is_active: bool
    created_at: str
    updated_at: str
    session_count: int = 0


class AdminUserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    display_name: str | None = None
    team: str | None = None


class AdminSessionOut(BaseModel):
    session_id: str
    message_count: int
    user_id: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────


def _user_to_admin_out(user: object, session_count: int = 0) -> AdminUserOut:
    return AdminUserOut(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        team=user.team,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        session_count=session_count,
    )


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminStatsOut:
    """Return system-wide statistics (users, sessions, etc.)."""
    stats = await get_admin_stats(session=session)
    return AdminStatsOut(**stats)


@router.get("/users", response_model=list[AdminUserOut])
async def admin_list_users(
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[AdminUserOut]:
    """List **all** users (including inactive) with session counts."""
    # Fetch all users, not just active ones.
    from sqlalchemy import select as sa_select

    from backend.core.models import User as UserModel

    result = await session.execute(
        sa_select(UserModel).order_by(UserModel.created_at.desc())
    )
    users = list(result.scalars().all())

    out: list[AdminUserOut] = []
    for u in users:
        sids = await list_user_sessions(str(u.id))
        out.append(_user_to_admin_out(u, session_count=len(sids)))
    return out


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserOut:
    """Update any user's role, active status, display_name, or team."""
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    user = await update_user(user_id, session=session, **kwargs)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    sids = await list_user_sessions(str(user.id))
    return _user_to_admin_out(user, session_count=len(sids))


@router.delete("/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: uuid.UUID,
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Permanently delete a user and all their data."""
    deleted = await db_delete_user(user_id, session=session)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/sessions", response_model=list[AdminSessionOut])
async def admin_list_sessions(
    _admin_id: str = Depends(require_admin),
) -> list[AdminSessionOut]:
    """List all chat sessions with their message count and owning user."""
    ids = await list_sessions()
    result: list[AdminSessionOut] = []
    for sid in ids:
        msgs = await get_session_messages(sid)
        uid = await get_session_user_id(sid)
        result.append(
            AdminSessionOut(
                session_id=sid,
                message_count=len(msgs),
                user_id=uid,
            )
        )
    return result


@router.delete("/sessions/{session_id}", status_code=204)
async def admin_delete_session(
    session_id: str,
    _admin_id: str = Depends(require_admin),
) -> None:
    """Delete a chat session and all its messages."""
    await delete_session(session_id)
