# Merge DeepResearch into Agent Alpha

## Context

The `deepresearch/` sub-repository is a standalone autonomous research agent with MCP-based web search (Tavily, Brave, Jina, Firecrawl, Playwright), Docker sandboxing, checkpoint/rewind/fork, a 7-step research workflow, and WebSocket streaming. We merge its capabilities into the main `agent_alpha` repo by:

1. **Merging** common files (`config.py`, `agent_factory.py`) — deepresearch's agent configuration replaces the current one, retaining RAG
2. **Discarding** the deepresearch SPA frontend (static `index.html`/`app.js`/`styles.css`)
3. **Adding** research features as new UI in the existing React frontend
4. **Creating** new files only for concerns that don't fit existing files

---

## Files to Modify

| File | What changes |
|---|---|
| `pyproject.toml` | Add `subagents-pydantic-ai`, `summarization-pydantic-ai`, `markdown`, `pytz`, `[web]`/`[docker]` extras |
| `backend/core/config.py` | Add MCP API keys, Excalidraw settings, Docker sandbox settings, `create_mcp_servers()` method |
| `backend/services/agent_factory.py` | **Replace** with deepresearch agent config (MCP servers, hooks, middleware, subagents, research prompt) retaining RAG tools and Logfire |
| `backend/app.py` | Register research WebSocket/REST routes, init `DeepResearchService` in lifespan |
| `frontend/src/App.tsx` | Add "Deep Research" navigation → new research chat page |
| `frontend/src/api.ts` | Add research API calls (WebSocket client, research REST endpoints) |
| `docker-compose.yml` | Add excalidraw-canvas service, Docker socket mount, research env vars |
| `backend/Dockerfile` | Install Node.js 22 + Docker CLI |
| `frontend/nginx.conf` | Add `/research/ws` WebSocket proxy + `/research/api/*` proxy |
| `.env` / `.env.example` | Add research env vars |

## Files to Create

| File | Source | Purpose |
|---|---|---|
| `backend/core/system_prompts.py` | deepresearch/prompts.py | RESEARCH_PROMPT + planner instructions |
| `backend/services/capabilities.py` | deepresearch/middleware.py + todo_toolset.py | Research middleware: AuditCapability, PermissionCapability, RateLimitRetryCapability, ForgiveWriteTodosCapability |
| `backend/schemas/research.py` | deepresearch/types.py | Source, Finding, ReportSection, ResearchReport models |
| `backend/services/research_session.py` | deepresearch/app.py (extracted) | SessionManager wrapper, checkpointing, session persistence |
| `backend/routes/research.py` | deepresearch/app.py (extracted) | WebSocket `/research/ws` + REST `/research/api/*` endpoints |
| `skills/research-methodology/SKILL.md` | deepresearch copy | Research skill |
| `skills/report-writing/SKILL.md` | deepresearch copy | Report writing skill |
| `skills/diagram-design/SKILL.md` | deepresearch copy | Diagram design skill |
| `frontend/src/pages/Research.tsx` | **new** | Deep Research chat page (React) |
| `frontend/src/pages/ResearchSession.tsx` | **new** | Research session components |

---

## Detailed Steps

### 1. Dependencies (`pyproject.toml`)

Add/change:
- `pydantic-deep[web]` (add `[web]` extra for markdown/weasyprint)
- `pydantic-ai-backend[docker]` (add `[docker]` extra for SessionManager)
- `subagents-pydantic-ai` (new)
- `summarization-pydantic-ai` (new)
- `markdown>=3.5` (new, for HTML export)
- `pytz>=2026.2` (new, for timezone injection in agent prompt)

### 2. Config Merge (`backend/core/config.py`)

Add to `Settings` class:
```python
# MCP Web Search
tavily_api_key: str = ""
brave_api_key: str = ""
jina_api_key: str = ""
firecrawl_api_key: str = ""
playwright_mcp: bool = False
excalidraw_enabled: bool = False
excalidraw_server_url: str = "http://localhost:3000"
excalidraw_canvas_url: str = "http://localhost:3000"

# Docker Sandbox
pydantic_deep_backend_type: str = "state"
session_idle_timeout: int = 3600
session_cleanup_interval: int = 300
```

Add `create_mcp_servers()` method that reads from these settings and creates MCP toolsets (Tavily, Brave, Jina, Excalidraw, Playwright, Firecrawl) — same logic as deepresearch's `config.py` but using `Settings` instead of `os.getenv`.

### 3. Agent Factory Replace (`backend/services/agent_factory.py`)

The current `build_agent()` is **replaced** with a merged version:

**Kept from current**:
- `logfire` configuration
- `OpenAIResponsesModel` creation (using `settings.llm_base_url`, `settings.llm_model`, `settings.llm_api_key`)
- RAG tools via `rag_service.get_rag_tools()`

**Added from deepresearch**:
- MCP server toolsets via `settings.create_mcp_servers()`
- Research prompt from `backend.core.system_prompts.RESEARCH_PROMPT`
- Deep subagents: `general-purpose`, `planner` (with plan toolset), `code-reviewer`
- Dynamic agent factory (`DynamicAgentRegistry`, `create_agent_factory_toolset`)
- Hooks: `audit_logger` (POST_TOOL_USE), `safety_gate` (PRE_TOOL_USE on execute)
- Middleware: `ForgiveWriteTodosCapability`, `AuditCapability`, `PermissionCapability`, `RateLimitRetryCapability`
- New includes: `include_teams=True`, `include_execute=True`, `include_checkpoints=True`
- Checkpointing: `checkpoint_frequency="every_turn"`, `max_checkpoints=50`
- Skills: programmatic `quick-reference` skill
- Context management: `context_manager_max_tokens=200_000`, `patch_tool_calls=True`
- `interrupt_on={"execute": True, "write_file": False}`

**Signature stays**: `build_agent(settings, memory_repository, rag_service) -> Agent`

### 4. New Prompt File (`backend/core/system_prompts.py`)

Contains:
- `RESEARCH_PROMPT` (~320 lines) — the 7-step research workflow (plan → todo → parallel research → wait → handle failures → write iteratively → present), modified to include RAG usage guidance
- Planner subagent instructions
- Research subagent instructions
- Code-reviewer subagent instructions
- `QUICK_REFERENCE_SKILL` content (command cheatsheet)

### 5. New Capabilities File (`backend/services/capabilities.py`)

Contains:
- `AuditCapability` — tracks tool call count/duration/breakdown
- `PermissionCapability` — blocks sensitive file paths
- `RateLimitRetryCapability` — exponential backoff on rate limits (model + tool level)
- `ForgiveWriteTodosCapability` — handles empty `write_todos({})` from weak LLMs

All imported from deepresearch's `middleware.py` + `todo_toolset.py`.

### 6. New Schemas (`backend/schemas/research.py`)

Pydantic models:
- `Source` — id, title, url, author, date, source_type
- `Finding` — claim, evidence, source_ids, confidence
- `ReportSection` — title, content, findings
- `ReportMetadata` — total_sources, search_queries_used, pages_read, etc.
- `ResearchReport` — title, question, executive_summary, sections, conclusions, sources, metadata

### 7. Research Session Service (`backend/services/research_session.py`)

Manages per-user research sessions with Docker sandbox containers:
- `ResearchSessionService` class — wraps `SessionManager` from `pydantic-ai-backend[docker]`
- `get_or_create_session(session_id)` — creates Docker container, seeds workspace, restores history
- Checkpoint store management (`InMemoryCheckpointStore`)
- Message history persistence (`history.json`)
- Session lifecycle management (idle timeout, cleanup)

When `settings.pydantic_deep_backend_type == "state"`, uses in-memory backend instead (no Docker required).

### 8. Research Routes (`backend/routes/research.py`)

**WebSocket endpoint**: `GET /research/ws`
- Bidirectional streaming chat with the research agent
- Sends text deltas, tool calls, results, status updates as JSON events
- Supports cancellation, approval responses, question answers
- Same protocol as deepresearch's `/ws/chat`

**REST endpoints** (prefixed with `/research/api`):
| Endpoint | Purpose |
|---|---|
| `GET /api/sessions` | List all sessions |
| `POST /api/session/new` | Create new session |
| `GET /api/history` | Get session message history |
| `GET /api/checkpoints` | List checkpoints |
| `POST /api/checkpoints/{id}/rewind` | Rewind to checkpoint |
| `POST /api/checkpoints/{id}/fork` | Fork from checkpoint |
| `GET /api/export/{fmt}` | Export report (md/html/pdf) |
| `POST /api/upload` | Upload file to sandbox |
| `GET /api/files` | List sandbox files |
| `GET /api/files/content/{path}` | Read file |
| `GET /api/files/binary/{path}` | Read binary file |
| `GET /api/todos` | Get TODOs |
| `POST /api/todos` | Set TODOs |
| `GET /api/config` | Get agent config |

### 9. App Wiring (`backend/app.py`)

In `AppBuilder.build()`:
- Import and include `research_router` (prefix `/research`)

In `AppBuilder._lifespan()`:
- Create `ResearchSessionService(settings)`
- Start session service (creates MCP servers, builds agent with RAG tools)
- Register as module-level singleton for route access
- On shutdown: release all sessions

Existing `AgentService` still exists and works in parallel — no breaking changes.

### 10. Frontend Research UI (`frontend/src/`)

**`api.ts`** — new exports:
- `createResearchSession()` → POST `/research/api/session/new`
- `listResearchSessions()` → GET `/research/api/sessions`
- `getResearchHistory(sessionId)` → GET `/research/api/history`
- `listCheckpoints(sessionId)` → GET `/research/api/checkpoints`
- `rewindCheckpoint(sessionId, id)` → POST `/research/api/checkpoints/{id}/rewind`
- `exportReport(sessionId, fmt)` → GET `/research/api/export/{fmt}`
- `uploadToSandbox(sessionId, file)` → POST `/research/api/upload`
- WebSocket connect helper → `new WebSocket("/research/ws")`

**`ResearchPage.tsx`** — full research chat interface:
- Session list sidebar (create/switch/delete)
- Chat message area with streaming text display (append as deltas arrive)
- Tool call visualization (which tool, status, result preview)
- Cancel button for running agent
- Checkpoint timeline (list/rewind/fork)
- File browser for sandbox files
- Export buttons (Markdown/HTML/PDF)
- TODO progress display
- Status bar (token usage, tool calls, elapsed time)

Add navigation button in `App.tsx` alongside Admin/RAG buttons.

### 11. Skills Merge (`skills/`)

Copy from deepresearch:
- `research-methodology/SKILL.md` — search strategy, source evaluation
- `report-writing/SKILL.md` — report structure, citation format
- `diagram-design/SKILL.md` — Excalidraw diagram best practices

Both agents share the same `skills/` directory, no conflicts.

### 12. Infrastructure

**`docker-compose.yml`**:
- Add `excalidraw-canvas` service (image: `ghcr.io/yctimlin/mcp_excalidraw-canvas:latest`, port 3000)
- Mount `/var/run/docker.sock` to backend container
- Add research env vars to backend service
- Add `research_workspaces` volume

**`backend/Dockerfile`**:
- Install Node.js 22 (for npx MCP servers: tavily-mcp, brave-search-mcp, etc.)
- Install Docker CLI (for SessionManager Docker sandbox)

**`frontend/nginx.conf`**:
- Proxy `/research/ws` with WebSocket Upgrade headers
- Proxy `/research/api/*` to backend

---

## Execution Order

| Step | Dependencies |
|---|---|
| 1. Dependencies + config merge | None |
| 2. Create schemas/research.py | None |
| 3. Create core/system_prompts.py | None |
| 4. Create services/capabilities.py | None |
| 5. Create services/research_session.py | Step 1 |
| 6. Replace services/agent_factory.py | Steps 1, 2, 3, 4 |
| 7. Create routes/research.py | Steps 5, 6 |
| 8. Wire backend/app.py | Steps 6, 7 |
| 9. Create frontend research pages | None |
| 10. Skills, infrastructure, Docker | Step 8 |

---

## Verification

1. **Backend starts**: `uv run python -m backend.main` — no import errors
2. **Agent has RAG tools**: Connect via WebSocket to `/research/ws` → check `/research/api/config` shows `rag_search`, `rag_search_by_document`, `rag_list_collections`
3. **Research chat works**: Send a question via WebSocket, verify streaming text and tool call events appear
4. **Existing REST chat works**: `POST /api/chat` returns normally
5. **Session persistence**: Create session, send messages, disconnect, reconnect → history restored
6. **Checkpoint/rewind**: Save checkpoint, rewind, verify messages roll back
7. **Frontend renders**: Navigate to Research page, session list loads, chat UI works
