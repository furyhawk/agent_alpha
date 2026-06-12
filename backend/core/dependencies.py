"""FastAPI dependency injection providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.agent import AgentService

if TYPE_CHECKING:
    from backend.core.config import Settings


async def get_settings() -> Settings:
    """Provide the application Settings singleton."""
    from backend.core.config import Settings as _Settings
    from backend.core.config import settings as _settings

    return _settings


async def get_agent_service() -> AgentService:
    """Provide the lazily-initialised AgentService singleton."""
    from backend.core.agent import get_service

    return get_service()
