"""PydanticDeep assistant — deep agentic coding assistant.

PydanticDeep is built on PydanticAI and provides:
- Filesystem tools: ls, read_file, write_file, edit_file, glob, grep
- Task management: write_todos, planning subagent
- Subagent delegation
- Skills system (SKILL.md files)
- Memory persistence (MEMORY.md across sessions)
- Context file discovery (AGENTS.md, SOUL.md from workspace root)
- Built-in web search and web fetch

Backend types (set via PYDANTIC_DEEP_BACKEND_TYPE):
  "state"   — In-memory (default, no persistence)
  "daytona" — Daytona cloud workspace (isolated, cloud-native)

Configuration via settings:
  PYDANTIC_DEEP_BACKEND_TYPE  : "state" | "daytona" (default: "state")
  PYDANTIC_DEEP_INCLUDE_SUBAGENTS : enable subagent delegation (default: True)
  PYDANTIC_DEEP_INCLUDE_SKILLS    : enable skills system (default: True)
  PYDANTIC_DEEP_INCLUDE_PLAN      : enable planner subagent (default: True)
  PYDANTIC_DEEP_INCLUDE_MEMORY    : enable persistent MEMORY.md (default: True)
  PYDANTIC_DEEP_INCLUDE_EXECUTE   : enable shell execution (default: False)
  PYDANTIC_DEEP_WEB_SEARCH        : enable built-in web search (default: True)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import logfire
from pydantic_ai import Agent
from pydantic_ai.capabilities import MCP, ToolSearch, WebSearch
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.tools import Tool
from pydantic_ai_harness import CodeMode

# Community packages, alphabetical:
from pydantic_ai_backends import LocalBackend
from pydantic_ai_shields import InputGuard, SecretRedaction, ToolGuard
from pydantic_deep import create_deep_agent
from pydantic_deep.deps import DeepAgentDeps
from subagents_pydantic_ai import SubAgentConfig

from backend.core.config import Settings


class AgentService:
    """Encapsulates agent construction, execution, and teardown.

    Uses lazy initialization so the agent is not built at import time.
    Accepts a ``Settings`` instance for testability (dependency injection).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._agent: Agent[DeepAgentDeps, str] | None = None
        self._model: OpenAIResponsesModel | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Build the agent. Idempotent — safe to call multiple times."""
        if self._agent is not None:
            return

        if self._settings.logfire_token:
            try:
                logfire.configure(token=self._settings.logfire_token)
                logfire.instrument_pydantic_ai()
            except Exception:
                pass  # Logfire is optional — don't crash if it fails

        self._model = OpenAIResponsesModel(
            self._settings.llm_model,
            provider=OpenAIProvider(
                base_url=self._settings.llm_base_url,
                api_key=self._settings.llm_api_key or "no-key-required",
            ),
        )

        self._agent = create_deep_agent(
            model=self._model,
            include_todo=True,
            include_filesystem=True,
            include_subagents=True,
            include_skills=True,
            include_plan=True,
            include_execute=False,
            include_memory=True,
            memory_dir=_MEMORY_DIR,
            web_search=False,
            web_fetch=True,
            thinking="xhigh",
            context_manager=True,
            context_manager_max_tokens=100_000,
            cost_tracking=True,
            cost_budget_usd=5.0,
            stuck_loop_detection=True,
            subagents=[
                SubAgentConfig(
                    name="researcher",
                    description="Deep research on a topic",
                    instructions="You are a thorough research assistant.",
                ),
            ],
            skill_directories=["./skills"],
            tools=self._build_rag_tools(),
            capabilities=[
                CodeMode(),
                ToolSearch(),
                MCP("https://hn.caseyjhand.com/mcp", native=True),
                WebSearch(local="duckduckgo"),
                InputGuard(guard=lambda p: "ignore previous instructions" not in p.lower()),
                ToolGuard(blocked=["rm"], require_approval=["write_file"]),
                SecretRedaction(),
            ],
        )

    async def shutdown(self) -> None:
        """Release agent resources."""
        self._agent = None

    # ── Execution ──────────────────────────────────────────────────────────

    async def ask(self, prompt: str, session_id: str | None = None) -> AskResult:
        """Send a prompt to the agent and return the text output with usage stats."""
        self.initialize()
        assert self._agent is not None
        deps = DeepAgentDeps(backend=_backend)
        t0 = time.monotonic()
        result = await self._agent.run(prompt, deps=deps)
        elapsed = time.monotonic() - t0
        usage = result.usage
        return AskResult(
            output=result.output,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            elapsed_seconds=round(elapsed, 2),
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_rag_tools() -> list[Tool]:
        """Build RAG search tools for document retrieval."""
        from skills.rag_search.search import rag_search, rag_search_by_document, rag_list_collections

        return [
            Tool(rag_search, name="rag_search"),
            Tool(rag_search_by_document, name="rag_search_by_document"),
            Tool(rag_list_collections, name="rag_list_collections"),
        ]


# ---------------------------------------------------------------------------
# AskResult — returned by AgentService.ask() with output + token usage stats.
# ---------------------------------------------------------------------------


@dataclass
class AskResult:
    """Result of a single agent ``ask()`` call with token usage information."""

    output: str
    """The agent's text reply."""

    input_tokens: int = 0
    """Number of prompt tokens sent to the model."""

    output_tokens: int = 0
    """Number of completion tokens generated by the model."""

    total_tokens: int = 0
    """Sum of input + output tokens."""

    elapsed_seconds: float = 0.0
    """Wall-clock time in seconds the agent took to respond."""


# ---------------------------------------------------------------------------
# Persistent backend — uses local filesystem so agent memory survives restarts.
# ---------------------------------------------------------------------------

import os as _os

_AGENT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_MEMORY_DIR = _os.path.join(_AGENT_ROOT, ".agent_memory")

_backend = LocalBackend(root_dir=_AGENT_ROOT)

# ---------------------------------------------------------------------------
# Singleton — lazy-initialised on the first call to ``ask()``.
# Keeps the existing module-level ``ask`` facade so downstream imports in
# ``chat.py`` continue to work unchanged.
# ---------------------------------------------------------------------------

from backend.core.config import settings as _settings  # noqa: E402

_service = AgentService(_settings)


def get_service() -> AgentService:
    """Return the singleton AgentService instance."""
    return _service


async def ask(prompt: str, session_id: str | None = None) -> AskResult:
    """Send a prompt to the agent and return the text output with usage stats."""
    return await _service.ask(prompt, session_id=session_id)
