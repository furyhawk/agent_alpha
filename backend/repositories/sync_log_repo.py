"""Repository for SyncLog CRUD operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.sync_log import SyncLog


async def get_all(
    session: AsyncSession,
    collection_name: str | None = None,
    limit: int = 20,
) -> list[SyncLog]:
    """List sync logs, optionally filtered by collection."""
    stmt = (
        select(SyncLog)
        .order_by(SyncLog.started_at.desc().nulls_last())
        .limit(limit)
    )
    if collection_name:
        stmt = stmt.where(SyncLog.collection_name == collection_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, log_id: UUID) -> SyncLog | None:
    """Get a sync log by ID."""
    return await session.get(SyncLog, log_id)


async def create(
    session: AsyncSession,
    *,
    source: str,
    collection_name: str,
    mode: str,
    sync_source_id: UUID | None = None,
) -> SyncLog:
    """Create a new sync log entry."""
    log = SyncLog(
        source=source,
        collection_name=collection_name,
        mode=mode,
        sync_source_id=sync_source_id,
        status="running",
    )
    session.add(log)
    await session.flush()
    return log


async def update_status(
    session: AsyncSession,
    log_id: UUID,
    **kwargs,
) -> SyncLog | None:
    """Update sync log status and counters."""
    stmt = (
        update(SyncLog)
        .where(SyncLog.id == log_id)
        .values(**kwargs)
        .returning(SyncLog)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one_or_none()
