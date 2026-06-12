"""Agent lifecycle: builds the shared agent instance loaded by the API routes."""

import logfire
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import Agent
from pydantic_ai.capabilities import MCP, Thinking, ToolSearch, WebSearch
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

logfire.configure()
logfire.instrument_pydantic_ai()

model = OpenAIResponsesModel(
    "llama",
    provider=OpenAIProvider(base_url="http://localhost:8011/v1"),
)

agent = Agent(
    model,
    capabilities=[
        CodeMode(),
        ToolSearch(),
        Thinking(effort="xhigh"),
        ContextManagerCapability(max_tokens=100_000),
        MCP("https://hn.caseyjhand.com/mcp"),
        WebSearch(),
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
            ]
        ),
        TodoCapability(enable_subtasks=True),
        CostTracking(budget_usd=5.0),
        InputGuard(guard=lambda p: "ignore previous instructions" not in p.lower()),
        ToolGuard(blocked=["rm"], require_approval=["write_file"]),
        SecretRedaction(),
        StuckLoopDetection(),
    ],
)


async def ask(prompt: str, session_id: str | None = None) -> str:
    """Send a prompt to the agent and return the text output."""
    deps = DeepAgentDeps()
    result = await agent.run(prompt, deps=deps)
    return result.output
