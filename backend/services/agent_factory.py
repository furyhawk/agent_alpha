"""Agent factory — builds the merged research-capable agent.

Merges the original agent_alpha agent with deepresearch's research agent:
- Retains: Logfire, model config, RAG tools
- Adds: MCP servers, research prompt, subagents, hooks, middleware, teams,
  execute, checkpoints, agent-factory toolset, remember toolset
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import logfire
import pytz
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import MCP, ToolSearch, WebSearch
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai_harness import CodeMode
from pydantic_ai_shields import InputGuard, SecretRedaction, ToolGuard
from pydantic_deep import BASE_PROMPT, DeepAgentDeps, Hook, HookEvent, HookInput, HookResult, Skill
from pydantic_deep import create_deep_agent
from pydantic_deep.toolsets.plan import create_plan_toolset
from pydantic_deep.types import SubAgentConfig
from subagents_pydantic_ai import (
    DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
    DynamicAgentRegistry,
    create_agent_factory_toolset,
)

from backend.core.config import Settings
from backend.core.system_prompts import (
    CODE_REVIEWER_INSTRUCTIONS,
    QUICK_REFERENCE_SKILL,
    RESEARCH_PLANNER_INSTRUCTIONS,
    RESEARCH_PROMPT,
    RESEARCH_SUBAGENT_INSTRUCTIONS,
)
from backend.services.capabilities import (
    AuditCapability,
    ForgiveWriteTodosCapability,
    PermissionCapability,
    RateLimitRetryCapability,
)

logger = logging.getLogger(__name__)


# ── Hooks ──────────────────────────────────────────────────────────────

async def audit_logger_handler(hook_input: HookInput) -> HookResult:
    """Background POST_TOOL_USE hook: logs all tool calls."""
    args_preview = str(hook_input.tool_input)[:200]
    logger.info(f"HOOK AUDIT: {hook_input.tool_name}({args_preview})")
    return HookResult(allow=True)


async def safety_gate_handler(hook_input: HookInput) -> HookResult:
    """PRE_TOOL_USE hook: blocks dangerous commands in execute tool."""
    import re
    command = hook_input.tool_input.get("command", "")
    dangerous_patterns = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+\*",
        r"mkfs\.",
        r"dd\s+if=.*of=/dev/",
        r"chmod\s+-R\s+777\s+/",
        r":\(\)\{",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            return HookResult(
                allow=False,
                reason=f"BLOCKED: Command matches dangerous pattern. "
                f"The command '{command}' was blocked for safety.",
            )
    return HookResult(allow=True)


HOOKS = [
    Hook(event=HookEvent.POST_TOOL_USE, handler=audit_logger_handler, background=True),
    Hook(event=HookEvent.PRE_TOOL_USE, handler=safety_gate_handler, matcher="execute", timeout=5),
]


# ── Subagent Configs ───────────────────────────────────────────────────

_subagent_plan_toolset = create_plan_toolset(plans_dir="/plans")

SUBAGENT_CONFIGS: list[SubAgentConfig] = [
    {
        "name": "general-purpose",
        "description": DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
        "instructions": RESEARCH_SUBAGENT_INSTRUCTIONS,
        "can_ask_questions": True,
        "agent_kwargs": {"retries": 3},
    },
    {
        "name": "planner",
        "description": (
            "Plans research strategy for complex topics. Asks clarifying questions "
            "and creates structured research plans with sub-topics. Use for any "
            "research task that needs multiple sources or comparative analysis."
        ),
        "instructions": RESEARCH_PLANNER_INSTRUCTIONS,
        "toolsets": [_subagent_plan_toolset],
    },
    {
        "name": "code-reviewer",
        "description": (
            "Reviews Python code for quality, security, and best practices. "
            "Delegate code review tasks to this subagent."
        ),
        "instructions": CODE_REVIEWER_INSTRUCTIONS,
    },
]


# ── Programmatic Skills ───────────────────────────────────────────────

PROGRAMMATIC_SKILLS = [
    Skill(
        name="quick-reference",
        description="Quick reference card for workspace commands and shortcuts",
        content=QUICK_REFERENCE_SKILL,
    ),
]


# ── Remember Toolset ───────────────────────────────────────────────────

def _create_remember_toolset() -> FunctionToolset[Any]:
    """Create a memory toolset that persists facts to /workspace/MEMORY.md."""
    toolset: FunctionToolset[Any] = FunctionToolset(id="remember-tool")

    @toolset.tool
    async def remember(ctx: RunContext[Any], fact: str) -> str:
        """Save a fact to persistent memory.

        Call this IMMEDIATELY when the user shares ANY personal information
        (name, preferences, project details, etc.) or asks you to remember something.

        Your memory resets every session — this tool is the ONLY way to persist
        information. If you don't call this, you will forget everything.

        Args:
            fact: The fact to save (short, clear statement).

        Returns:
            Confirmation message.
        """
        backend = ctx.deps.backend
        try:
            if backend and backend.exists("/workspace/MEMORY.md"):
                content = backend.read_bytes("/workspace/MEMORY.md").decode("utf-8")
            else:
                content = ""
        except Exception:
            content = ""

        if not content.strip():
            content = "# Agent Memory\n\n"

        content = content.rstrip("\n") + "\n- " + fact + "\n"
        if backend:
            backend.write("/workspace/MEMORY.md", content.encode("utf-8"))
        return f"Saved to memory: {fact}"

    return toolset


# ── Main Instructions ──────────────────────────────────────────────────

MAIN_INSTRUCTIONS = f"""{BASE_PROMPT}

{RESEARCH_PROMPT}

## Available Tools

- **Memory**: `remember(fact)` — save personal info, preferences, project details to persistent memory
- **Internal Knowledge Base (RAG)**: `rag_search(query)`, `rag_search_by_document(query, filename)`, \
`rag_list_collections()` — search uploaded documents
- **Web Search**: Tavily, Brave Search, Jina URL reader, Firecrawl
- **Browser Automation**: Playwright MCP (navigate, screenshot, click, fill)
- **File Operations**: read_file, write_file, edit_file, glob, grep, ls
- **Code Execution**: `execute(command)` — Docker sandbox with Python 3.12
- **Diagrams**: Excalidraw MCP — see quick-reference skill for details
- **Subagents**: `task(description, subagent_type)` — for complex research only
- **Teams**: `spawn_team()`, `assign_task()` — for parallel multi-agent coordination
- **TODO**: `write_todos()`, `read_todos()`, `add_todo()`, `update_todo_status()`
- **Checkpoints**: `save_checkpoint()`, `list_checkpoints()`, `rewind_to()`
- **Skills**: `list_skills()`, `load_skill(name)` — domain knowledge
- **Plan Mode**: `task(description, subagent_type="planner")` for complex multi-step planning

## Shell Commands

You have `execute` for shell commands. It may need user approval — just call it.

## Error Handling

Fix errors yourself: install missing modules, fix paths, retry. Don't ask permission.

## File Locations

- Uploads: /uploads/
- Workspace: /workspace/
- Memory: /workspace/MEMORY.md (use `remember()` tool to write)
"""


# ── Factory ────────────────────────────────────────────────────────────

def build_agent(
    settings: Settings,
    memory_repository=None,
    rag_service=None,
) -> Agent:
    """Build the merged research-capable agent.

    Args:
        settings: Application settings.
        memory_repository: Optional memory repository for persistent memory.
        rag_service: Optional RAG service providing RAG search tools.

    Returns:
        Configured pydantic-deep Agent.
    """
    # ── Logfire ─────────────────────────────────────────────────────────
    if settings.logfire_token:
        try:
            logfire.configure(token=settings.logfire_token)
            logfire.instrument_pydantic_ai()
        except Exception:
            pass  # Logfire is optional

    # ── Model ───────────────────────────────────────────────────────────
    model = OpenAIModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "no-key-required",
        ),
    )

    # ── MCP Servers ─────────────────────────────────────────────────────
    mcp_servers = settings.create_mcp_servers()

    # ── Agent Factory (Dynamic Subagents) ───────────────────────────────
    agent_registry = DynamicAgentRegistry()
    factory_toolset = create_agent_factory_toolset(
        registry=agent_registry,
        default_model=model,
        max_agents=5,
        id="agent-factory",
    )

    # ── Remember Toolset ────────────────────────────────────────────────
    remember_toolset = _create_remember_toolset()

    # ── RAG Tools ───────────────────────────────────────────────────────
    rag_tools = rag_service.get_rag_tools() if rag_service else []

    # ── Middleware ───────────────────────────────────────────────────────
    use_rate_limiter = bool(settings.llm_api_key)
    middleware = [
        ForgiveWriteTodosCapability(),
        AuditCapability(),
        PermissionCapability(),
    ]
    if use_rate_limiter:
        middleware.append(RateLimitRetryCapability())

    # ── Build Agent ─────────────────────────────────────────────────────
    agent = create_deep_agent(
        model=model,
        instructions=MAIN_INSTRUCTIONS,
        backend=None,
        toolsets=[*mcp_servers, factory_toolset, remember_toolset],
        tools=rag_tools,
        include_todo=True,
        include_filesystem=True,
        include_execute=True,
        include_subagents=True,
        include_teams=True,
        include_skills=True,
        include_plan=False,
        include_checkpoints=True,
        subagents=SUBAGENT_CONFIGS,
        include_builtin_subagents=False,
        max_nesting_depth=2,
        subagent_registry=agent_registry,
        subagent_extra_toolsets=mcp_servers,
        skills=PROGRAMMATIC_SKILLS,
        skill_directories=["./skills"],
        hooks=HOOKS,
        middleware=middleware,
        context_manager=True,
        context_manager_max_tokens=200_000,
        patch_tool_calls=True,
        context_files=["/workspace/DEEP.md", "/workspace/MEMORY.md"],
        checkpoint_frequency="every_turn",
        max_checkpoints=50,
        interrupt_on={"execute": True, "write_file": False},
    )

    # ── System Prompt: Current Date/Time ────────────────────────────────

    @agent.system_prompt
    def add_current_date_time(ctx: RunContext[DeepAgentDeps]) -> str:
        """Add current date and time as system context."""
        sg_tz = pytz.timezone("Asia/Singapore")
        now = datetime.now(sg_tz)
        return (
            f"Today is {now.strftime('%A, %B %d, %Y')}. "
            f"The current local time is {now.strftime('%I:%M %p %Z')}."
        )

    return agent
