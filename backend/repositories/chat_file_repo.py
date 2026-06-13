"""Repository for ChatFile CRUD operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.chat_file import ChatFile


async def get_by_id(session: AsyncSession, file_id: UUID) -> ChatFile | None:
    """Get a chat file by ID."""
    return await session.get(ChatFile, file_id)


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    filename: str,
    mime_type: str,
    size: int,
    storage_path: str,
    file_type: str,
    parsed_content: str | None = None,
) -> ChatFile:
    """Create a new chat file record."""
    chat_file = ChatFile(
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        size=size,
        storage_path=storage_path,
        file_type=file_type,
        parsed_content=parsed_content,
    )
    session.add(chat_file)
    await session.flush()
    return chat_file
