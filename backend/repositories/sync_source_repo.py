"""Repository for SyncSource CRUD operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.sync_source import SyncSource


async def get_all(
    session: AsyncSession,
    is_active: bool | None = None,
) -> list[SyncSource]:
    """List all sync sources, optionally filtered by active status."""
    stmt = select(SyncSource).order_by(SyncSource.created_at.desc())
    if is_active is not None:
        stmt = stmt.where(SyncSource.is_active == is_active)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, source_id: UUID) -> SyncSource | None:
    """Get a sync source by ID."""
    return await session.get(SyncSource, source_id)


async def create(
    session: AsyncSession,
    *,
    name: str,
    connector_type: str,
    collection_name: str,
    config: dict | None = None,
    sync_mode: str = "full",
    schedule_minutes: int | None = None,
) -> SyncSource:
    """Create a new sync source."""
    source = SyncSource(
        name=name,
        connector_type=connector_type,
        collection_name=collection_name,
        config=config or {},
        sync_mode=sync_mode,
        schedule_minutes=schedule_minutes,
    )
    session.add(source)
    await session.flush()
    return source


async def update(
    session: AsyncSession,
    source_id: UUID,
    **kwargs,
) -> SyncSource | None:
    """Update a sync source."""
    stmt = (
        update(SyncSource)
        .where(SyncSource.id == source_id)
        .values(**kwargs)
        .returning(SyncSource)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one_or_none()


async def delete(session: AsyncSession, source_id: UUID) -> None:
    """Delete a sync source."""
    stmt = sa_delete(SyncSource).where(SyncSource.id == source_id)
    await session.execute(stmt)
    await session.flush()


async def update_sync_status(
    session: AsyncSession,
    source_id: UUID,
    *,
    last_sync_at: datetime | None = None,
    last_sync_status: str | None = None,
    last_error: str | None = None,
) -> SyncSource | None:
    """Update sync source status after a sync operation."""
    stmt = (
        update(SyncSource)
        .where(SyncSource.id == source_id)
        .values(
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            last_error=last_error,
        )
        .returning(SyncSource)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one_or_none()
