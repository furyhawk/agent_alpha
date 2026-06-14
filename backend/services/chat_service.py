"""Chat service — message and session management (Valkey).

Usage::

    service = ChatService(valkey)
    await service.save_message("session-1", "user", "Hello!")
    msgs = await service.get_messages("session-1")
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from backend.repositories import chat_repo


class ChatService:
    """Service for chat message and session management."""

    def __init__(self, valkey: Redis):
        self.valkey = valkey

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
    ) -> None:
        """Append a message to a session's history."""
        await chat_repo.save_message(
            self.valkey,
            session_id,
            role,
            content,
            user_id=user_id,
        )

    async def get_messages(
        self,
        session_id: str,
    ) -> list[dict[str, str]]:
        """Return all messages for a session."""
        return await chat_repo.get_session_messages(self.valkey, session_id)

    async def get_session_user_id(self, session_id: str) -> str | None:
        """Return the user_id linked to a session, or ``None``."""
        return await chat_repo.get_session_user_id(self.valkey, session_id)

    async def set_title(self, session_id: str, title: str) -> None:
        """Set a session title."""
        await chat_repo.set_session_title(self.valkey, session_id, title)

    async def get_title(self, session_id: str) -> str | None:
        """Return a session title, or ``None``."""
        return await chat_repo.get_session_title(self.valkey, session_id)

    async def get_created_at(self, session_id: str) -> str | None:
        """Return a session creation timestamp, or ``None``."""
        return await chat_repo.get_session_created_at(self.valkey, session_id)

    async def list_sessions(self) -> list[str]:
        """Return all known session IDs."""
        return await chat_repo.list_sessions(self.valkey)

    async def list_user_sessions(self, user_id: str) -> list[str]:
        """Return all session IDs for a given user."""
        return await chat_repo.list_user_sessions(self.valkey, user_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages."""
        await chat_repo.delete_session(self.valkey, session_id)

    async def generate_title(self, message: str) -> str:
        """Generate a short title from a user message."""
        title = message.strip()[:60]
        if len(message.strip()) > 60:
            title += "…"
        return title or "New chat"
