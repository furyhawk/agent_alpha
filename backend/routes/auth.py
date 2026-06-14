"""Authentication API routes — login, register, and token management.

Users authenticate with username + password and receive a bearer token
(stored in Valkey with a 7-day TTL) for subsequent requests.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_db_session, get_valkey
from backend.services.auth_service import AuthService
from backend.services.user_service import UserService

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
    valkey: Redis = Depends(get_valkey),
) -> AuthResponse:
    """Register a new user with a password."""
    auth_service = AuthService(session, valkey)
    user_service = UserService(session)

    # Check for duplicate username.
    existing = await user_service.get_by_username(body.username)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"User '{body.username}' already exists",
        )

    user, token = await auth_service.register(
        username=body.username,
        display_name=body.display_name,
        password=body.password,
        role=body.role,
        team=body.team,
    )

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
    valkey: Redis = Depends(get_valkey),
) -> AuthResponse:
    """Authenticate with username + password. Returns a bearer token."""
    auth_service = AuthService(session, valkey)
    result = await auth_service.login(body.username, body.password)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    user, token = result
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
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> MeResponse:
    """Return the current authenticated user's profile.

    Requires ``Authorization: Bearer <token>`` header.
    """
    auth_service = AuthService(session, valkey)
    user_service = UserService(session)

    user_id = await auth_service.resolve_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    user = await user_service.get_by_id(_uuid.UUID(user_id))
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
    session: AsyncSession = Depends(get_db_session),
    valkey: Redis = Depends(get_valkey),
) -> None:
    """Revoke the current auth token (logout).

    Requires ``Authorization: Bearer <token>`` header.
    """
    auth_service = AuthService(session, valkey)
    await auth_service.logout(token)
