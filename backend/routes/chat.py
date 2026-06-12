"""Chat API endpoint — sends prompts to the agent and returns replies.

Messages are persisted in Valkey so chat history survives server restarts.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.agent import AgentService
from backend.core.database import (
    get_session_messages,
    list_sessions,
    save_message,
)
from backend.core.dependencies import get_agent_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class MessageOut(BaseModel):
    role: str
    content: str
    timestamp: str


class SessionOut(BaseModel):
    session_id: str
    message_count: int


# ── POST /api/chat ────────────────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    agent: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    """Send a user message to the agent and return its reply.

    Saves both the user message and the assistant reply to Valkey.
    Assigns a new UUID ``session_id`` if none was provided.
    """
    session_id = body.session_id or uuid.uuid4().hex

    try:
        # Persist the user message.
        await save_message(session_id, "user", body.message)

        # Ask the agent.
        output = await agent.ask(body.message, session_id=session_id)

        # Persist the assistant reply.
        await save_message(session_id, "assistant", output)

        return ChatResponse(reply=output, session_id=session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /api/chat/history ─────────────────────────────────────────────────


class HistoryParams(BaseModel):
    session_id: str


@router.get("/history", response_model=list[MessageOut])
async def get_history(session_id: str) -> list[MessageOut]:
    """Return all messages for a given session."""
    messages = await get_session_messages(session_id)
    return [MessageOut(**msg) for msg in messages]


# ── GET /api/chat/sessions ────────────────────────────────────────────────


@router.get("/sessions", response_model=list[SessionOut])
async def sessions_list() -> list[SessionOut]:
    """Return all known session IDs with their message counts."""
    ids = await list_sessions()
    result: list[SessionOut] = []
    for sid in ids:
        msgs = await get_session_messages(sid)
        result.append(SessionOut(session_id=sid, message_count=len(msgs)))
    return result
