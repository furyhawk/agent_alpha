"""Authentication API routes — login, register, and token management.

Users authenticate with username + password and receive a bearer token
(stored in Valkey with a 7-day TTL) for subsequent requests.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import (
    authenticate_user,
    create_auth_token,
    create_user_with_password,
    get_user_by_username,
    resolve_auth_token,
    revoke_auth_token,
)
from backend.core.dependencies import get_db_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "user"
    team: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    username: str
    display_name: str
    role: str
    team: str | None = None


class MeResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    team: str | None = None


async def _get_token_from_header(
    authorization: str | None = Header(None),
) -> str:
    """Extract the bearer token from the Authorization header."""
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Use: Bearer <token>",
        )
    return token


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register_endpoint(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Register a new user with a password."""
    # Check for duplicate username.
    existing = await get_user_by_username(body.username, session=session)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"User '{body.username}' already exists",
        )

    user = await create_user_with_password(
        username=body.username,
        display_name=body.display_name,
        password=body.password,
        role=body.role,
        team=body.team,
        session=session,
    )

    token = await create_auth_token(str(user.id))
    return AuthResponse(
        token=token,
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        team=user.team,
    )


@router.post("/login", response_model=AuthResponse)
async def login_endpoint(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Authenticate with username + password. Returns a bearer token."""
    user = await authenticate_user(body.username, body.password, session=session)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = await create_auth_token(str(user.id))
    return AuthResponse(
        token=token,
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        team=user.team,
    )


@router.get("/me", response_model=MeResponse)
async def me_endpoint(
    token: str = Depends(_get_token_from_header),
) -> MeResponse:
    """Return the current authenticated user's profile.

    Requires ``Authorization: Bearer <token>`` header.
    """
    from backend.core.database import get_user
    from backend.core.database import open_session as _open_db

    user_id = await resolve_auth_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    async with _open_db() as session:
        user = await get_user(uuid_obj(user_id), session=session)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
        )

    return MeResponse(
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        team=user.team,
    )


@router.post("/logout", status_code=204)
async def logout_endpoint(
    token: str = Depends(_get_token_from_header),
) -> None:
    """Revoke the current auth token (logout).

    Requires ``Authorization: Bearer <token>`` header.
    """
    await revoke_auth_token(token)


# ── Helpers ────────────────────────────────────────────────────────────────


def uuid_obj(value: str) -> object:
    """Convert a string UUID to a UUID object for DB queries."""
    import uuid as _uuid

    return _uuid.UUID(value)
