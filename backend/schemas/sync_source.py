"""Sync source API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConnectorConfigField(BaseModel):
    """Schema for a single connector configuration field."""

    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None


class ConnectorInfo(BaseModel):
    """Information about an available connector."""

    type: str
    name: str
    config_schema: dict[str, ConnectorConfigField]
    enabled: bool = True


class ConnectorList(BaseModel):
    """List of available connectors."""

    items: list[ConnectorInfo]


class SyncSourceCreate(BaseModel):
    """Request to create a sync source."""

    name: str = Field(..., description="Human-readable name")
    connector_type: str = Field(..., description="Connector type identifier")
    collection_name: str = Field("documents", description="Target RAG collection")
    config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: str = Field("full", description="Sync mode: full, new_only, update_only")
    schedule_minutes: int | None = Field(None, description="Auto-sync interval in minutes")


class SyncSourceUpdate(BaseModel):
    """Request to update a sync source."""

    name: str | None = Field(None, description="Human-readable name")
    collection_name: str | None = Field(None, description="Target RAG collection")
    config: dict[str, Any] | None = Field(None)
    sync_mode: str | None = Field(None, description="Sync mode")
    schedule_minutes: int | None = Field(None, description="Auto-sync interval")
    is_active: bool | None = Field(None, description="Whether the source is active")


class SyncSourceRead(BaseModel):
    """Sync source read model returned by the API."""

    id: str
    name: str
    connector_type: str
    collection_name: str
    config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: str = "full"
    schedule_minutes: int | None = None
    is_active: bool = True
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    last_error: str | None = None
    created_at: str | None = None


class SyncSourceList(BaseModel):
    """List of sync sources."""

    items: list[SyncSourceRead]
    total: int
