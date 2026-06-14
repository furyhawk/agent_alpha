"""Admin dashboard API routes — system stats, user management, session overview.

All endpoints require ``Authorization: Bearer <token>`` with an ``admin`` role.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func as sa_func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_db_session, get_valkey
from backend.core.exceptions import NotFoundError
from backend.core.models import User as UserModel
from backend.repositories import chat_repo, user_repo
from backend.repositories.auth_token_repo import resolve_token as _resolve_token
from backend.services.chat_service import ChatService
from backend.services.user_service import UserService

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Admin auth dependency ──────────────────────────────────────────────────


async def require_admin(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> str:
    """Verify the request comes from an authenticated admin user.

    Returns the ``user_id`` string on success, raises 401/403 otherwise.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    user_id = await _resolve_token(valkey, token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_service = UserService(session)
    user = await user_service.get_by_id(uuid.UUID(user_id))
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
    title: str | None = None
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


async def _gather_admin_stats(
    session: AsyncSession,
    valkey: Redis,
) -> dict[str, object]:
    """Gather system-wide statistics."""
    # Total users
    result = await session.execute(sa_func.count(UserModel.id))
    total_users: int = result.scalar() or 0

    # Users by role
    result = await session.execute(
        sa_select(UserModel.role, sa_func.count(UserModel.id)).group_by(UserModel.role)
    )
    users_by_role: dict[str, int] = {row[0]: row[1] for row in result}

    # Active vs inactive
    result = await session.execute(
        sa_select(UserModel.is_active, sa_func.count(UserModel.id)).group_by(UserModel.is_active)
    )
    users_by_active: dict[str, int] = {"active": 0, "inactive": 0}
    for row in result:
        key = "active" if row[0] else "inactive"
        users_by_active[key] = row[1]

    # Sessions from Valkey
    sessions_set = "chat:sessions"
    total_sessions = await valkey.scard(sessions_set)

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "users_by_active": users_by_active,
        "total_sessions": total_sessions,
    }


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> AdminStatsOut:
    """Return system-wide statistics (users, sessions, etc.)."""
    stats = await _gather_admin_stats(session, valkey)
    return AdminStatsOut(**stats)


@router.get("/users", response_model=list[AdminUserOut])
async def admin_list_users(
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> list[AdminUserOut]:
    """List **all** users (including inactive) with session counts."""
    user_service = UserService(session)
    users = await user_service.list_all()
    chat_service = ChatService(valkey)

    out: list[AdminUserOut] = []
    for u in users:
        sids = await chat_service.list_user_sessions(str(u.id))
        out.append(_user_to_admin_out(u, session_count=len(sids)))
    return out


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> AdminUserOut:
    """Update any user's role, active status, display_name, or team."""
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    user_service = UserService(session)
    chat_service = ChatService(valkey)

    try:
        user = await user_service.update(user_id, **kwargs)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    sids = await chat_service.list_user_sessions(str(user.id))
    return _user_to_admin_out(user, session_count=len(sids))


@router.delete("/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: uuid.UUID,
    _admin_id: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Permanently delete a user and all their data."""
    user_service = UserService(session)
    try:
        await user_service.delete(user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/sessions", response_model=list[AdminSessionOut])
async def admin_list_sessions(
    _admin_id: str = Depends(require_admin),
    valkey: Redis = Depends(get_valkey),
) -> list[AdminSessionOut]:
    """List all chat sessions with their message count and owning user."""
    chat_service = ChatService(valkey)
    ids = await chat_service.list_sessions()
    result: list[AdminSessionOut] = []
    for sid in ids:
        msgs = await chat_service.get_messages(sid)
        uid = await chat_service.get_session_user_id(sid)
        title = await chat_service.get_title(sid)
        result.append(
            AdminSessionOut(
                session_id=sid,
                title=title,
                message_count=len(msgs),
                user_id=uid,
            )
        )
    return result


@router.delete("/sessions/{session_id}", status_code=204)
async def admin_delete_session(
    session_id: str,
    _admin_id: str = Depends(require_admin),
    valkey: Redis = Depends(get_valkey),
) -> None:
    """Delete a chat session and all its messages."""
    chat_service = ChatService(valkey)
    await chat_service.delete_session(session_id)
