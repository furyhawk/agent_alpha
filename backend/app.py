"""FastAPI application factory — encapsulated in an AppBuilder class."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.logging import DefaultFormatter

from backend.core.config import Settings
from backend.core.database import close_engine, close_valkey, init_db
from backend.core.agent import AgentService, set_service
from backend.repositories.memory_repository import MemoryRepository
from backend.services.agent_factory import build_agent
from backend.services.rag_service import RagService
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.chat import router as chat_router
from backend.routes.health import router as health_router
from backend.routes.rag import router as rag_router
from backend.routes.users import router as users_router

logger = logging.getLogger("agent_alpha")


def _configure_logging(*, debug: bool = False) -> None:
    """Configure standard logging to match FastAPI/uvicorn's log format."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    # Configure the agent_alpha logger
    logger = logging.getLogger("agent_alpha")
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    # Ensure all backend.* loggers output to stderr at the right level
    logging.getLogger("backend").addHandler(handler)
    logging.getLogger("backend").setLevel(level)
    logging.getLogger("backend").propagate = False


_configure_logging()


def _reconfigure_logging(*, debug: bool) -> None:
    """Adjust all agent_alpha loggers to the requested level.

    Called at startup so the ``debug`` setting from ``.env`` is reflected
    even though the module-level logger was configured at import time.
    """
    level = logging.DEBUG if debug else logging.INFO
    for name in ("agent_alpha", "backend", "backend.core", "backend.routes"):
        logging.getLogger(name).setLevel(level)
    # Also enable debug for uvicorn when debug mode is on.
    if debug:
        logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)
        logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)


class AppBuilder:
    """Builds and configures the FastAPI application with DI wiring.

    Accepts a ``Settings`` instance so tests can supply custom config.
    The ``AgentService`` is built inside the lifespan hook, which wires
    ``MemoryRepository``, ``RagService``, and the agent factory together
    and registers the result as a module-level singleton.
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

        app.include_router(admin_router)
        app.include_router(auth_router)
        app.include_router(health_router)
        app.include_router(chat_router)
        app.include_router(users_router)
        app.include_router(rag_router)

        return app

    # ── Lifecycle ──────────────────────────────────────────────────────────

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI):
        """Startup / shutdown lifecycle."""
        # Apply debug log level from settings (may override module-level default).
        _reconfigure_logging(debug=self._settings.debug)

        logger.info("Agent Alpha backend starting")

        # Create database tables if they don't exist.
        await init_db()

        # Build agent with full dependency injection via the factory.
        memory_repo = MemoryRepository()
        rag_service = RagService()
        agent = build_agent(self._settings, memory_repo, rag_service)
        agent_service = AgentService(agent=agent, memory_repo=memory_repo)
        set_service(agent_service)

        yield

        # Graceful teardown on shutdown.
        await agent_service.shutdown()
        await close_valkey()
        await close_engine()
        logger.info("Agent Alpha backend shutting down")


# ---------------------------------------------------------------------------
# Module-level factory function (backward-compatible).
# ---------------------------------------------------------------------------

_app_builder: AppBuilder | None = None


def create_app() -> FastAPI:
    """Return a new FastAPI application instance."""
    global _app_builder
    _app_builder = AppBuilder()
    return _app_builder.build()
