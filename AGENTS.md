# Agent Alpha — AI Agent Instructions

## Project Overview

**Agent Alpha** is an agentic AI backend (FastAPI + pydantic-ai) with a React + Vite + Tailwind frontend. Users chat with an AI agent powered by an OpenAI-compatible LLM (Ollama, OpenAI, etc.).

```
agent_alpha/
├── backend/           # FastAPI application
│   ├── app.py         # AppBuilder factory (DI, lifespan, CORS)
│   ├── main.py        # Uvicorn entry point
│   ├── core/
│   │   ├── agent.py   # AgentService (lazy init, capabilities)
│   │   ├── config.py  # pydantic-settings from .env
│   │   ├── database.py# SQLAlchemy async engine + Valkey client
│   │   └── dependencies.py  # FastAPI DI providers
│   └── routes/
│       ├── chat.py    # POST /api/chat
│       └── health.py  # GET /api/health
├── frontend/          # React + Vite SPA
│   ├── src/
│   │   ├── App.tsx    # Chat UI component
│   │   └── api.ts     # Fetch client
│   └── nginx.conf     # Production SPA + API proxy
├── skills/            # pydantic-ai skill definitions
└── docker-compose.yml # Full stack orchestration
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Uvicorn |
| **AI** | pydantic-ai-slim, pydantic-ai-harness, pydantic-ai-shields |
| **Database** | PostgreSQL 16 (asyncpg + SQLAlchemy async) |
| **Cache** | Valkey 8 (Redis-compatible, via `redis[hiredis]`) |
| **Frontend** | React 18, TypeScript 5.6, Vite 6, Tailwind CSS 3.4 |
| **Infra** | Docker Compose (backend, frontend/nginx, postgres, valkey) |
| **Pkg Mgr** | `uv` (Python), `bun` (frontend) |

## Build & Run Commands

```bash
make install            # uv sync — install Python deps
make run                # Start backend on :8000 (reload)

make frontend-install   # bun install
make frontend-dev       # Start Vite on :5173

make compose-up         # Start all containers (detached)
make compose-rebuild    # Rebuild images & restart
make compose-logs       # Follow logs
make compose-down       # Stop everything
```

## Coding Conventions

### Python

- **`from __future__ import annotations`** at the top of every module.
- **Type hints** required on all function signatures, including async return types.
- **Docstrings**: module-level Google-style with `::` usage examples.
- **Imports**: stdlib → third-party → local, grouped with blank lines.
- **Async-first**: all I/O uses `async`/`await` (FastAPI routes, DB sessions, Valkey).
- **Settings**: use `pydantic-settings` (`Settings` class in `config.py`); field names are snake_case, env vars are UPPER_SNAKE_CASE.
- **Error handling**: `HTTPException(status_code=500, detail=str(exc))` in routes; `try/except` with graceful fallback for optional components (e.g., Logfire).
- **DI pattern**: FastAPI `Depends()` with providers in `dependencies.py`. Provider functions use module-level singletons.
- **Factories**: use `AppBuilder` class for app construction, accept optional `Settings` for testability.

### TypeScript / React

- **Functional components** only (hooks, no classes).
- **Interfaces** at file top, exported when reused.
- **Tailwind utility classes** inline; no CSS modules or styled-components.
- **API client** isolated in `api.ts` — one `sendMessage()` export.

## Key Architecture Decisions

### Dependency Injection
`dependencies.py` provides `get_settings()` and `get_agent_service()` as FastAPI `Depends()` callables. `AgentService` is lazily initialized (not built at import time). `AppBuilder` accepts optional `Settings` for test overrides.

### Capabilities Stack
Agent capabilities are assembled in `AgentService._build_capabilities()` — a list that includes code execution, web search, MCP, sub-agents, cost tracking, input/tool guards, secret redaction, and stuck-loop detection.

### Lifecycle
FastAPI's `lifespan` context manager handles startup (initialize agent, DB engine, Valkey) and shutdown (close agent, DB pool, Valkey connection). See `AppBuilder._lifespan()` in `app.py`.

### Configuration
Environment variables loaded from `.env` via `pydantic-settings` (`backend/core/config.py`). Key vars: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LOGFIRE_TOKEN`, `DATABASE_URL`, `VALKEY_URL`.

## Common Pitfalls

1. **Container DNS caching**: nginx caches DNS at startup. Use `resolver` directive + variable in `proxy_pass` for runtime resolution (see `frontend/nginx.conf`).
2. **Slow LLM responses**: The LLM may take minutes to respond. Nginx `proxy_read_timeout` is set to 600s. Backend timeouts should match.
3. **Logfire is optional**: `logfire.configure()` is wrapped in `try/except` — omit `LOGFIRE_TOKEN` to disable.
4. **API key for local LLMs**: Set `LLM_API_KEY=no-key-required` (or leave empty) for Ollama/local endpoints; the OpenAI client requires a non-None value.
5. **uv vs pip**: Always use `uv sync` / `uv add`, never `pip install`. The lock file is `uv.lock`.
6. **bun for frontend**: Use `bun install` / `bun run dev` for frontend, not `npm`.
7. **Container orchestration**: Backend depends on postgres + valkey being healthy. Use `depends_on` with `condition: service_healthy`.
