"""Agent lifecycle: builds the shared agent instance loaded by the API routes."""

from __future__ import annotations

import logfire
from pydantic_ai import Agent
from pydantic_ai.capabilities import MCP, Thinking, ToolSearch, WebSearch
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai_harness import CodeMode

# Community packages, alphabetical:
from pydantic_ai_backends import ConsoleCapability
from pydantic_ai_shields import CostTracking, InputGuard, SecretRedaction, ToolGuard
from pydantic_ai_skills import SkillsCapability
from pydantic_ai_summarization import ContextManagerCapability
from pydantic_ai_todo import TodoCapability
from pydantic_deep import MemoryCapability, StuckLoopDetection
from pydantic_deep.deps import DeepAgentDeps
from subagents_pydantic_ai import SubAgentCapability, SubAgentConfig

from backend.core.config import Settings


class AgentService:
    """Encapsulates agent construction, execution, and teardown.

    Uses lazy initialization so the agent is not built at import time.
    Accepts a ``Settings`` instance for testability (dependency injection).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._agent: Agent | None = None
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

        self._agent = Agent(
            self._model,
            capabilities=self._build_capabilities(),
        )

    async def shutdown(self) -> None:
        """Release agent resources."""
        self._agent = None

    # ── Execution ──────────────────────────────────────────────────────────

    async def ask(self, prompt: str, session_id: str | None = None) -> str:
        """Send a prompt to the agent and return the text output."""
        self.initialize()
        assert self._agent is not None
        deps = DeepAgentDeps()
        result = await self._agent.run(prompt, deps=deps)
        return result.output

    # ── Internal helpers ───────────────────────────────────────────────────

    def _build_capabilities(self) -> list:
        """Assemble the full list of agent capabilities."""
        return [
            CodeMode(),
            ToolSearch(),
            Thinking(effort="xhigh"),
            ContextManagerCapability(max_tokens=100_000),
            MCP("https://hn.caseyjhand.com/mcp", native=True),
            WebSearch(local="duckduckgo"),
            ConsoleCapability(),
            MemoryCapability(agent_name="harness-example"),
            SkillsCapability(directories=["./skills"]),
            SubAgentCapability(
                subagents=[
                    SubAgentConfig(
                        name="researcher",
                        description="Deep research on a topic",
                        instructions="You are a thorough research assistant.",
                    ),
                ],
                default_model=self._model,
            ),
            TodoCapability(enable_subtasks=True),
            CostTracking(budget_usd=5.0),
            InputGuard(guard=lambda p: "ignore previous instructions" not in p.lower()),
            ToolGuard(blocked=["rm"], require_approval=["write_file"]),
            SecretRedaction(),
            StuckLoopDetection(),
        ]


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


async def ask(prompt: str, session_id: str | None = None) -> str:
    """Send a prompt to the agent and return the text output."""
    return await _service.ask(prompt, session_id=session_id)
