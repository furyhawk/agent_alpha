"""Chat API endpoint — streams agent responses using SSE."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.agent import ask

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None


@router.post("", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    """Send a user message to the agent and return its reply."""
    try:
        output = await ask(body.message, session_id=body.session_id)
        return ChatResponse(reply=output, session_id=body.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
