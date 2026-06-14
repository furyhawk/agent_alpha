"""Chat API endpoint — sends prompts to the agent and returns replies.

Messages are persisted in Valkey so chat history survives server restarts.
Sessions can optionally be linked to a user for session/role management.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from redis.asyncio import Redis

from backend.core.agent import AgentService
from backend.core.dependencies import get_agent_service, get_valkey
from backend.services.auth_service import AuthService
from backend.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0.0


class MessageOut(BaseModel):
    role: str
    content: str
    timestamp: str


class SessionOut(BaseModel):
    session_id: str
    title: str | None = None
    message_count: int
    user_id: str | None = None


async def _resolve_user_id(
    valkey: Redis = Depends(get_valkey),
    user_id: str | None = None,
    authorization: str | None = Header(None),
) -> str | None:
    """Resolve the effective user_id from explicit param or auth token."""
    if user_id is not None:
        return user_id
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            # We need the auth service but don't have a DB session here.
            # Delegate to a minimal token lookup via Valkey directly.
            from backend.repositories import auth_token_repo

            return await auth_token_repo.resolve_token(valkey, token)
    return None


# ── POST /api/chat ────────────────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    agent: AgentService = Depends(get_agent_service),
    valkey: Redis = Depends(get_valkey),
    user_id: str | None = Depends(_resolve_user_id),
) -> ChatResponse:
    """Send a user message to the agent and return its reply.

    Saves both the user message and the assistant reply to Valkey.
    Assigns a new UUID ``session_id`` if none was provided.
    The chat session is automatically assigned to the authenticated user
    (via ``Authorization: Bearer <token>`` header) or to the explicit
    ``user_id`` field in the request body.
    """
    chat_service = ChatService(valkey)
    session_id = body.session_id or uuid.uuid4().hex

    try:
        # Persist the user message (linked to authenticated user).
        await chat_service.save_message(
            session_id,
            "user",
            body.message,
            user_id=user_id,
        )

        # Generate a short title from the first user message if not yet set.
        existing_title = await chat_service.get_title(session_id)
        if existing_title is None:
            title = await chat_service.generate_title(body.message)
            await chat_service.set_title(session_id, title or "New chat")

        # Ask the agent — returns output + token usage.
        result = await agent.ask(body.message, session_id=session_id)

        # Persist the assistant reply.
        await chat_service.save_message(session_id, "assistant", result.output)

        return ChatResponse(
            reply=result.output,
            session_id=session_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /api/chat/history ─────────────────────────────────────────────────


@router.get("/history", response_model=list[MessageOut])
async def get_history(
    session_id: str,
    valkey: Redis = Depends(get_valkey),
) -> list[MessageOut]:
    """Return all messages for a given session."""
    chat_service = ChatService(valkey)
    messages = await chat_service.get_messages(session_id)
    return [MessageOut(**msg) for msg in messages]


# ── GET /api/chat/sessions ────────────────────────────────────────────────


@router.get("/sessions", response_model=list[SessionOut])
async def sessions_list(
    valkey: Redis = Depends(get_valkey),
    user_id: str | None = Query(None, description="Filter by user ID"),
) -> list[SessionOut]:
    """Return all known session IDs with their message counts.

    If ``user_id`` is provided, only sessions belonging to that user
    are returned.
    """
    chat_service = ChatService(valkey)

    if user_id is not None:
        ids = await chat_service.list_user_sessions(user_id)
    else:
        ids = await chat_service.list_sessions()

    result: list[SessionOut] = []
    for sid in ids:
        msgs = await chat_service.get_messages(sid)
        uid = await chat_service.get_session_user_id(sid)
        title = await chat_service.get_title(sid)
        result.append(
            SessionOut(
                session_id=sid,
                title=title,
                message_count=len(msgs),
                user_id=uid,
            )
        )
    return result
