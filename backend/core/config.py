"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from .env / environment.

    Usage::

        settings = Settings()               # load from .env / env vars
        settings = Settings(_env_file=".env.test")  # alternate file
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = False

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama"
    llm_api_key: str = ""
    logfire_token: str = ""

    database_url: str = "postgresql+asyncpg://agent_alpha:agent_alpha@localhost:5432/agent_alpha"
    valkey_url: str = "redis://localhost:6379/0"

    # ── Milvus (Vector Database) ───────────────────────────────────────────

    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""

    # ── Media & File Storage ───────────────────────────────────────────────

    media_dir: str = "media"
    max_upload_size_mb: int = 50

    # ── RAG Parsing ────────────────────────────────────────────────────────

    pdf_parser: str = "pymupdf"

    # ── Cross-Encoder Reranker ─────────────────────────────────────────────

    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    hf_token: str = ""
    models_cache_dir: Path = Path.home() / ".cache" / "agent-alpha" / "models"

    # ── Embeddings ─────────────────────────────────────────────────────────

    embedding_base_url: str = ""
    """Base URL for the embedding API. If empty, uses the LLM base URL."""

    embedding_api_key: str = ""
    """API key for the embedding API. If empty, uses the LLM API key."""

    # ── AI Configuration ───────────────────────────────────────────────────

    ai_model: str = "gpt-4o"
    rag_image_description_model: str = ""

    # ── MCP Web Search (Deep Research) ─────────────────────────────────────

    tavily_api_key: str = Field(default="", description="Tavily AI search API key")
    brave_api_key: str = Field(default="", description="Brave Search API key")
    jina_api_key: str = Field(default="", description="Jina AI reader API key")
    firecrawl_api_key: str = Field(default="", description="Firecrawl web scraping API key")
    playwright_mcp: bool = Field(default=False, description="Enable Playwright browser automation MCP")
    excalidraw_enabled: bool = Field(default=False, description="Enable Excalidraw diagram canvas")
    excalidraw_server_url: str = Field(default="http://localhost:3000", description="Excalidraw server URL")
    excalidraw_canvas_url: str = Field(default="http://localhost:3000", description="Excalidraw canvas frontend URL")

    # ── Docker Sandbox (Deep Research) ─────────────────────────────────────

    pydantic_deep_backend_type: str = Field(
        default="state",
        description="Backend type: 'state' (in-memory) or 'docker' (sandbox containers)",
    )
    session_idle_timeout: int = Field(default=3600, description="Session idle timeout in seconds")
    session_cleanup_interval: int = Field(default=300, description="Session cleanup check interval in seconds")

    # ── RAG Settings (derived) ────────────────────────────────────────────

    @property
    def rag(self) -> object:
        """Return a ``RAGSettings`` instance configured from application settings.

        Lazy import to avoid circular dependencies at module level.
        """
        from backend.services.rag.config import RAGSettings

        return RAGSettings(
            collection_name="documents",
            chunk_size=512,
            chunk_overlap=50,
            chunking_strategy="recursive",
            enable_hybrid_search=False,
            enable_ocr=False,
            enable_image_description=True,
            image_description_model=self.rag_image_description_model,
        )

    # ── MCP Servers (Deep Research) ────────────────────────────────────────

    @staticmethod
    def _docker_available() -> bool:
        """Check if Podman/Docker daemon is running (for Excalidraw container)."""
        binary = shutil.which("podman") or shutil.which("docker")
        if not binary:
            return False
        try:
            result = subprocess.run([binary, "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def create_mcp_servers(self) -> list:
        """Create MCP server toolsets based on configured API keys.

        Returns a list of MCP servers that can be passed as toolsets to the agent.
        Servers are started/stopped automatically by pydantic-ai when the agent
        enters/exits its async context manager.
        """
        from pydantic_ai.mcp import MCPToolset
        from pydantic_ai.toolsets import PrefixedToolset
        from fastmcp.client.transports import StdioTransport

        servers: list = []

        # Tavily — AI-optimized web search
        if self.tavily_api_key:
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        StdioTransport(
                            command="npx",
                            args=["-y", "tavily-mcp@latest"],
                            env={"TAVILY_API_KEY": self.tavily_api_key},
                        ),
                        max_retries=3,
                    ),
                    prefix="tavily",
                )
            )

        # Brave Search — web search
        if self.brave_api_key:
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        StdioTransport(
                            command="npx",
                            args=["-y", "@anthropic-ai/brave-search-mcp@latest"],
                            env={"BRAVE_API_KEY": self.brave_api_key},
                        ),
                        max_retries=3,
                    ),
                    prefix="brave",
                )
            )

        # Jina AI Reader — URL to readable markdown
        if self.jina_api_key:
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        "https://mcp.jina.ai/v1",
                        headers={"Authorization": f"Bearer {self.jina_api_key}"},
                        max_retries=3,
                    ),
                    prefix="jina",
                )
            )

        # Excalidraw — live diagram canvas
        if self.excalidraw_enabled and self._docker_available():
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        StdioTransport(
                            command="podman",
                            args=[
                                "run",
                                "-i",
                                "--rm",
                                "-e",
                                f"EXPRESS_SERVER_URL={self.excalidraw_server_url}",
                                "-e",
                                "ENABLE_CANVAS_SYNC=true",
                                "ghcr.io/yctimlin/mcp_excalidraw:latest",
                            ],
                        ),
                    ),
                    prefix="excalidraw",
                )
            )
        elif self.excalidraw_enabled:
            logger.warning("Excalidraw enabled but Podman/Docker is not available — skipping")

        # Playwright — browser automation for JS-heavy pages
        if self.playwright_mcp:
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        StdioTransport(
                            command="npx",
                            args=["-y", "@playwright/mcp@latest", "--headless"],
                        ),
                    ),
                    prefix="playwright",
                )
            )

        # Firecrawl — advanced web scraping/crawling
        if self.firecrawl_api_key:
            servers.append(
                PrefixedToolset(
                    MCPToolset(
                        StdioTransport(
                            command="npx",
                            args=["-y", "firecrawl-mcp@latest"],
                            env={"FIRECRAWL_API_KEY": self.firecrawl_api_key},
                        ),
                        max_retries=3,
                    ),
                    prefix="firecrawl",
                )
            )

        return servers

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def create(cls, **overrides: str) -> Settings:
        """Return a Settings instance with selective overrides (useful in tests).

        Example::

            settings = Settings.create(llm_model="test-model")
        """
        return cls(**overrides)


settings = Settings()
