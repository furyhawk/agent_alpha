"""RAG document ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.models import Base


class RAGDocument(Base):
    """Tracks a document ingested into the RAG pipeline."""

    __tablename__ = "rag_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="documents"
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    filesize: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filetype: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    vector_document_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(
        String(1024), nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<RAGDocument {self.filename!r} status={self.status!r}>"
