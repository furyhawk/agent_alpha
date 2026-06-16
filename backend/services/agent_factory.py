from typing import List
import logfire
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import Agent
from pydantic_deep import create_deep_agent
from subagents_pydantic_ai import SubAgentConfig
from pydantic_ai_shields import InputGuard, SecretRedaction, ToolGuard

from backend.core.config import Settings
from backend.repositories.memory_repository import MemoryRepository
from backend.services.rag_service import RagService

def build_agent(settings: Settings, memory_repository: MemoryRepository, rag_service: RagService) -> Agent:
    """
    Factory method to create the PydanticDeep agent.
    Moves initialization logic from AgentService into this factory.
    """
    if settings.logfire_token:
        try:
            logfire.configure(token=settings.logfire_token)
            logfire.instrument_pydantic_ai()
        except Exception:
            pass  # Logfire is optional — don't crash if it fails

    model = OpenAIResponsesModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "no-key-required",
        ),
    )

    return create_deep_agent(
        model=model,
        include_todo=True,
        include_filesystem=True,
        include_subagents=True,
        include_skills=True,
        include_plan=True,
        include_execute=False,
        include_memory=True,
        memory_dir=memory_repository.memory_dir,
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
        tools=rag_service.get_rag_tools(),
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
