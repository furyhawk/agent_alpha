"""FastAPI application factory — encapsulated in an AppBuilder class."""

from __future__ import annotations

from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import Settings
from backend.core.dependencies import get_agent_service
from backend.routes.chat import router as chat_router
from backend.routes.health import router as health_router


class AppBuilder:
    """Builds and configures the FastAPI application with DI wiring.

    Accepts a ``Settings`` instance so tests can supply custom config.
    The ``AgentService`` is lazily initialised inside the lifespan.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        from backend.core.config import settings as _default_settings

        self._settings = settings or _default_settings

    # ── Factory ────────────────────────────────────────────────────────────

    def build(self) -> FastAPI:
        """Construct the fully-configured FastAPI application."""
        app = FastAPI(
            title="Agent Alpha",
            description="Agentic AI backend powered by pydantic-ai",
            version="0.1.0",
            lifespan=self._lifespan,
        )

        # Allow the frontend dev-server to call the API.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        app.include_router(health_router)
        app.include_router(chat_router)

        return app

    # ── Lifecycle ──────────────────────────────────────────────────────────

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI):
        """Startup / shutdown lifecycle."""
        logfire.info("Agent Alpha backend starting")

        # Initialise the agent service on startup.
        agent_service = await get_agent_service()
        agent_service.initialize()

        yield

        # Graceful teardown on shutdown.
        await agent_service.shutdown()
        logfire.info("Agent Alpha backend shuttingdown")


# ---------------------------------------------------------------------------
# Module-level factory function (backward-compatible).
# ---------------------------------------------------------------------------

_app_builder: AppBuilder | None = None


def create_app() -> FastAPI:
    """Return a new FastAPI application instance."""
    global _app_builder
    _app_builder = AppBuilder()
    return _app_builder.build()
