"""Chat API endpoint — sends prompts to the agent and returns replies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.agent import AgentService
from backend.core.dependencies import get_agent_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    agent: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    """Send a user message to the agent and return its reply."""
    try:
        output = await agent.ask(body.message, session_id=body.session_id)
        return ChatResponse(reply=output, session_id=body.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
