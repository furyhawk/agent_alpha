# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Install with PDF/HTML export support
uv sync --extra export

# Run the server (opens on http://localhost:8080)
uv run deepresearch

# Start Excalidraw canvas (separate terminal)
docker compose up -d excalidraw-canvas

# Run without Excalidraw
EXCALIDRAW_ENABLED=0 uv run deepresearch
```

No tests, linters, or formatters are configured in this project.

## Environment

Copy `.env.example` to `.env` and configure:
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — LLM provider
- At least one search API key: `TAVILY_API_KEY`, `BRAVE_API_KEY`, or `JINA_API_KEY`
- Default model is `openai-responses:o4-mini` (override via `MODEL_NAME`)
- When `LLM_BASE_URL` is set, uses a local OpenAI-compatible endpoint instead

## Architecture

**Stack:** Python 3.12+ / FastAPI / WebSocket / pydantic-ai + pydantic-deep

### Source Layout

```
src/deepresearch/
  app.py          # FastAPI server, WebSocket /ws/chat, REST endpoints
  agent.py        # Agent factory — assembles the research agent with all toolsets
  config.py       # MCP server creation, model config, path constants
  prompts.py      # System prompt for the research agent (~300 lines of instructions)
  middleware.py    # Three capabilities: AuditCapability, PermissionCapability, RateLimitRetryCapability
  todo_toolset.py # ForgiveWriteTodosCapability — handles malformed tool calls from local LLMs
  types.py        # Pydantic models: Source, Finding, ReportSection, ResearchReport
static/
  index.html      # Single-page frontend
  app.js          # WebSocket client, tool rendering, file preview, Excalidraw iframe
  styles.css      # Dark theme UI
skills/
  research-methodology/SKILL.md   # Loaded agent skill: source evaluation, search strategy
  report-writing/SKILL.md         # Loaded agent skill: report structure, citation format
  diagram-design/SKILL.md         # Loaded agent skill: Excalidraw diagram best practices
workspace/
  DEEP.md         # Context file injected into every session (file organization conventions)
  MEMORY.md       # Persistent agent memory (written via `remember()` tool)
workspaces/       # Per-session data: history.json, meta.json, events.jsonl, canvas.json
```

### Runtime Flow

1. **Lifespan startup** (`app.py:lifespan`): Creates MCP servers (Tavily, Brave, Jina, Excalidraw, Playwright, Firecrawl per API keys in env) and the research agent. Retry loop drops failing MCP servers and restarts.

2. **WebSocket session** (`/ws/chat`): Each browser tab connects with a session UUID. A per-user Docker sandbox container is created (python-datascience runtime). Message history persists to `workspaces/<uuid>/history.json`.

3. **Agent execution** (`run_agent_with_streaming`): Uses `agent.iter()` for streaming — processes nodes (ModelRequest → stream text deltas, CallTools → stream tool calls/results) and sends WebSocket JSON events to the frontend.

4. **Approval flow**: Tools like `execute` trigger `DeferredToolRequests` — the frontend shows an approval dialog, and the agent resumes with `DeferredToolResults`.

5. **Checkpointing**: Auto-saves after every turn to `InMemoryCheckpointStore`. Supports `rewind` and `fork` via REST endpoints.

### Agent Architecture

The agent (`create_research_agent` in `agent.py`) uses **pydantic-deep**'s `create_deep_agent` with:

- **Toolsets**: MCP servers (search/browser/diagrams) + filesystem + execute + subagents + teams + TODO + skills + checkpoints + agent-factory + remember
- **Subagents**: `general-purpose` (research executor), `planner` (plan mode), `code-reviewer`, plus dynamic agents via factory
- **Hooks**: `audit_logger` (POST_TOOL_USE, background) + `safety_gate` (PRE_TOOL_USE on `execute`, blocks rm -rf /, mkfs, dd, etc.)
- **Middleware stack**: `ForgiveWriteTodosCapability` → `AuditCapability` → `PermissionCapability` → optionally `RateLimitRetryCapability`
- **Context management**: Sliding window (50 msg trigger, keep 30), token eviction (20k limit), context files from `/workspace/DEEP.md` and `/workspace/MEMORY.md`

### MCP Servers (config.py)

All optional, enabled by API key presence:
- **Tavily** — AI search (`npx tavily-mcp`)
- **Brave Search** — web search (`npx @anthropic-ai/brave-search-mcp`)
- **Jina** — URL→markdown reader (HTTP MCP at `https://mcp.jina.ai/v1`)
- **Excalidraw** — live diagrams (Podman container, requires `podman` binary)
- **Playwright** — browser automation (requires `PLAYWRIGHT_MCP=1`)
- **Firecrawl** — web scraping/crawling (`npx firecrawl-mcp`)

### Research Workflow (prompts.py)

The system prompt encodes a detailed 7-step research workflow:
1. **Plan** — dispatch planner subagent for complex topics
2. **Todo** — create progress tracking with `write_todos`
3. **Parallel subagents** — dispatch all research tasks async
4. **Wait** — `wait_tasks` for results
5. **Handle failures** — never stop, use own knowledge as fallback
6. **Write iteratively** — chapter by chapter via `edit_file`
7. **Present** — summarize and offer deeper analysis

### REST Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Serves `static/index.html` |
| `GET /health` | Health check with agent/session status |
| `GET /config` | Full feature configuration |
| `POST /upload` | File upload to sandbox |
| `GET /files?session_id=` | List files in sandbox |
| `GET /files/content/...` | Read file content |
| `GET /files/binary/...` | Read binary files (images) |
| `GET /todos?session_id=` | Get current TODOs |
| `GET /checkpoints?session_id=` | List checkpoints |
| `POST /checkpoints/:id/rewind` | Rewind to checkpoint |
| `POST /checkpoints/:id/fork` | Fork new session from checkpoint |
| `GET /history?session_id=` | Get conversation history |
| `GET /sessions` | List all sessions |
| `DELETE /sessions/:id` | Delete session |
| `GET /export/:fmt` | Export report (md/html/pdf) |
| `GET /preview/:session_id/...` | Serve raw files from container |
