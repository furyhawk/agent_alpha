"""Connector registry for RAG sync sources.

Connectors provide a pluggable way to ingest documents from various sources
(local folders, GDrive, S3, OneDrive, etc.). The registry is populated at
import time by each connector module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Abstract base class for sync source connectors."""

    CONNECTOR_TYPE: str = ""
    DISPLAY_NAME: str = ""
    CONFIG_SCHEMA: dict[str, dict[str, Any]] = {}

    @abstractmethod
    async def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate connector configuration. Returns (is_valid, error_message)."""
        ...

    @abstractmethod
    async def list_files(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """List files available from the source. Returns list of file info dicts."""
        ...

    @abstractmethod
    async def download_file(self, config: dict[str, Any], file_path: str) -> bytes:
        """Download a file from the source as bytes."""
        ...


# Registry populated by connector modules at import time
CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}
