"""DeepResearch configuration — MCP servers, model, paths."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.toolsets import AbstractToolset, PrefixedToolset
from fastmcp.client.transports import StdioTransport

logger = logging.getLogger(__name__)


APP_DIR = Path(__file__).resolve().parent.parent.parent  # deepresearch/
SKILLS_DIR = APP_DIR / "skills"
WORKSPACE_DIR = APP_DIR / "workspace"
WORKSPACES_DIR = APP_DIR / "workspaces"
STATIC_DIR = APP_DIR / "static"

# Default model and LLM endpoint configuration (can be overridden by .env)
MODEL_NAME: str = os.getenv("MODEL_NAME", "openai-responses:o4-mini")
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:8011/v1")
LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")
USE_RATE_LIMITER: bool = (LLM_API_KEY or "no-key-required") != "no-key-required"


def get_model() -> str | OpenAIModel:
    """Get the configured model, using a local OpenAI-compatible endpoint if
    ``LLM_BASE_URL`` is set (default: ``http://localhost:8011/v1``).

    Returns a model **instance** (with a custom provider) when
    ``LLM_BASE_URL`` is non-empty, otherwise returns the plain model name
    string for pydantic-ai's default resolution.
    """
    if LLM_BASE_URL:
        return OpenAIModel(
            MODEL_NAME,
            provider=OpenAIProvider(
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY or "no-key-required",
            ),
        )
    return MODEL_NAME


EXCALIDRAW_CANVAS_URL: str = os.getenv("EXCALIDRAW_CANVAS_URL", "http://localhost:3000")


def _docker_available() -> bool:
    """Check if Docker daemon is running."""
    if not shutil.which("podman"):
        return False
    try:
        result = subprocess.run(
            ["podman", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def create_mcp_servers() -> list[AbstractToolset]:
    """Create MCP server toolsets based on available API keys.

    Returns a list of MCP servers that can be passed as toolsets to the agent.
    Servers are started/stopped automatically by pydantic-ai when the agent
    enters/exits its async context manager.
    """
    servers: list[AbstractToolset] = []

    # Tavily — AI-optimized web search (requires TAVILY_API_KEY)
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        servers.append(
            PrefixedToolset(
                MCPToolset(
                    StdioTransport(
                        command="npx",
                        args=["-y", "tavily-mcp@latest"],
                        env={"TAVILY_API_KEY": tavily_key},
                    ),
                    max_retries=3,
                ),
                prefix="tavily",
            )
        )

    # Brave Search — web search (requires BRAVE_API_KEY)
    brave_key = os.getenv("BRAVE_API_KEY")
    if brave_key:
        servers.append(
            PrefixedToolset(
                MCPToolset(
                    StdioTransport(
                        command="npx",
                        args=["-y", "@anthropic-ai/brave-search-mcp@latest"],
                        env={"BRAVE_API_KEY": brave_key},
                    ),
                    max_retries=3,
                ),
                prefix="brave",
            )
        )

    # Jina AI Reader — converts any URL to readable markdown
    # Requires JINA_API_KEY (free tier available at https://jina.ai/)
    # MCP endpoint: https://mcp.jina.ai/v1
    jina_key = os.getenv("JINA_API_KEY")
    if jina_key:
        servers.append(
            PrefixedToolset(
                MCPToolset(
                    "https://mcp.jina.ai/v1",
                    headers={"Authorization": f"Bearer {jina_key}"},
                    max_retries=3,
                ),
                prefix="jina",
            )
        )

    # Excalidraw — live canvas with real-time sync via mcp-excalidraw-server
    excalidraw_server_url = os.getenv("EXCALIDRAW_SERVER_URL", "http://host.docker.internal:3000")
    if os.getenv("EXCALIDRAW_ENABLED", "1") == "1" and _docker_available():
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
                            f"EXPRESS_SERVER_URL={excalidraw_server_url}",
                            "-e",
                            "ENABLE_CANVAS_SYNC=true",
                            "ghcr.io/yctimlin/mcp_excalidraw:latest",
                        ],
                    ),
                ),
                prefix="excalidraw",
            )
        )
    elif os.getenv("EXCALIDRAW_ENABLED", "1") == "1":
        logger.warning("Excalidraw enabled but Podman is not available — skipping")

    # Playwright — browser automation for JS-heavy pages (requires PLAYWRIGHT_MCP=1)
    if os.getenv("PLAYWRIGHT_MCP"):
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

    # Firecrawl — advanced web scraping/crawling (requires FIRECRAWL_API_KEY)
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    if firecrawl_key:
        servers.append(
            PrefixedToolset(
                MCPToolset(
                    StdioTransport(
                        command="npx",
                        args=["-y", "firecrawl-mcp@latest"],
                        env={"FIRECRAWL_API_KEY": firecrawl_key},
                    ),
                    max_retries=3,
                ),
                prefix="firecrawl",
            )
        )

    return servers
