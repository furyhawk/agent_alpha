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

# See https://ai.pydantic.dev/logfire/ for setup details.
logfire.configure()
logfire.instrument_pydantic_ai()

model = OpenAIResponsesModel(
    "llama",
    provider=OpenAIProvider(base_url="http://localhost:8011/v1"),
)

agent = Agent(
    model,
    capabilities=[
        # --- Tool execution & discovery ---
        # Wraps every tool into a single run_code, sandboxed by Monty.
        CodeMode(),
        # Progressive tool discovery for large tool sets; discovered tools fold into run_code.
        ToolSearch(),
        # --- Reasoning ---
        # Provider-adaptive thinking; uses native extended thinking on supporting models.
        Thinking(effort="xhigh"),
        # --- Context management ---
        # Sliding window + LLM compaction. By @vstorm-co:
        # https://github.com/vstorm-co/summarization-pydantic-ai
        # Pydantic AI also ships `AnthropicCompaction` and `OpenAICompaction` for
        # provider-native compaction.
        ContextManagerCapability(max_tokens=100_000),
        # --- Tools ---
        # Connect to any MCP server -- here, the open-source Hacker News server
        # (https://github.com/cyanheads/hn-mcp-server).
        MCP("https://hn.caseyjhand.com/mcp"),
        # Provider-adaptive web search; falls back to a local DuckDuckGo implementation.
        WebSearch(),
        # Filesystem + shell. By @vstorm-co: https://github.com/vstorm-co/pydantic-ai-backend
        ConsoleCapability(),
        # --- Memory & persistence ---
        # Persistent ./MEMORY.md per agent name. By @vstorm-co:
        # https://github.com/vstorm-co/pydantic-deepagents
        MemoryCapability(agent_name="harness-example"),
        # --- Orchestration ---
        # Agent skills (Anthropic's spec) by @DougTrajano:
        # https://github.com/DougTrajano/pydantic-ai-skills
        # @vstorm-co's pydantic-deep also offers skills loading; the two have different
        # spec footprints (Doug's is closer to programmatic skills).
        SkillsCapability(directories=["./skills"]),
        # Spawn sub-agents with their own toolsets and instructions. By @vstorm-co:
        # https://github.com/vstorm-co/subagents-pydantic-ai
        SubAgentCapability(
            subagents=[
                SubAgentConfig(
                    name="researcher",
                    description="Deep research on a topic",
                    instructions="You are a thorough research assistant.",
                ),
            ]
        ),
        # Track tasks and subtasks; in-memory by default, AsyncPostgresStorage available.
        # By @vstorm-co: https://github.com/vstorm-co/pydantic-ai-todo
        TodoCapability(enable_subtasks=True),
        # --- Safety & reliability ---
        # The next four are by @vstorm-co: https://github.com/vstorm-co/pydantic-ai-shields
        # Per-run cost cap with a callback hook.
        CostTracking(budget_usd=5.0),
        # Reject prompts that look like prompt-injection attempts.
        InputGuard(guard=lambda p: "ignore previous instructions" not in p.lower()),
        # Block or require approval per tool name.
        ToolGuard(blocked=["rm"], require_approval=["write_file"]),
        # Detect API keys/tokens in tool I/O and redact before they reach the model.
        SecretRedaction(),
        # Bail out if the agent gets stuck calling the same tools in a loop.
        # By @vstorm-co: https://github.com/vstorm-co/pydantic-deepagents
        StuckLoopDetection(),
    ],
)


async def main() -> None:
    deps = DeepAgentDeps()
    result = await agent.run(
        "What are your skills.",
        # "Find the latest HN stories about AI, pull their comment threads, and summarize the discussions.",
        deps=deps,
    )
    print(result.output)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
