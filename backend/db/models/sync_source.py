"""Sync source ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.models import Base


class SyncSource(Base):
    """Configuration for a RAG sync source (local folder, GDrive, S3, etc.)."""

    __tablename__ = "sync_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    collection_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="documents"
    )
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    sync_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="full"
    )
    schedule_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_sync_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<SyncSource {self.name!r} type={self.connector_type!r}>"
