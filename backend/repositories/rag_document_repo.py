"""Repository for RAGDocument CRUD operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.rag_document import RAGDocument


async def get_all(
    session: AsyncSession,
    collection_name: str | None = None,
) -> list[RAGDocument]:
    """List all RAG documents, optionally filtered by collection."""
    stmt = select(RAGDocument).order_by(RAGDocument.created_at.desc())
    if collection_name:
        stmt = stmt.where(RAGDocument.collection_name == collection_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, doc_id: UUID) -> RAGDocument | None:
    """Get a RAG document by ID."""
    return await session.get(RAGDocument, doc_id)


async def create(
    session: AsyncSession,
    *,
    collection_name: str,
    filename: str,
    filesize: int,
    filetype: str,
    storage_path: str = "",
) -> RAGDocument:
    """Create a new RAG document record."""
    doc = RAGDocument(
        collection_name=collection_name,
        filename=filename,
        filesize=filesize,
        filetype=filetype,
        storage_path=storage_path,
    )
    session.add(doc)
    await session.flush()
    return doc


async def update_status(
    session: AsyncSession,
    doc_id: UUID,
    **kwargs,
) -> RAGDocument | None:
    """Update document status and optional fields."""
    stmt = (
        update(RAGDocument)
        .where(RAGDocument.id == doc_id)
        .values(**kwargs)
        .returning(RAGDocument)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one_or_none()


async def delete(session: AsyncSession, doc_id: UUID) -> None:
    """Delete a RAG document record."""
    stmt = delete(RAGDocument).where(RAGDocument.id == doc_id)
    await session.execute(stmt)
    await session.flush()


async def delete_by_collection(session: AsyncSession, collection_name: str) -> int:
    """Delete all RAG documents for a collection. Returns count."""
    stmt = (
        delete(RAGDocument)
        .where(RAGDocument.collection_name == collection_name)
        .returning(RAGDocument.id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return len(result.fetchall())
