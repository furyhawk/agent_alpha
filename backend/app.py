"""FastAPI application factory."""

from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.chat import router as chat_router
from backend.routes.health import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup / shutdown lifecycle."""
    logfire.info("Agent Alpha backend starting")
    yield
    logfire.info("Agent Alpha backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Alpha",
        description="Agentic AI backend powered by pydantic-ai",
        version="0.1.0",
        lifespan=lifespan,
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
