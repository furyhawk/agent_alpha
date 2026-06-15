# Agent Alpha — AI Agent Instructions

## Project Overview

**Agent Alpha** is an agentic AI backend (FastAPI + pydantic-ai) with a React + Vite + Tailwind frontend. Users chat with an AI agent powered by a llama.cpp server (OpenAI-compatible endpoint).

```
agent_alpha/
├── backend/           # FastAPI application
│   ├── app.py         # AppBuilder factory (DI, lifespan, CORS)
│   ├── main.py        # Uvicorn entry point
│   ├── core/
│   │   ├── agent.py   # AgentService (lazy init, capabilities)
│   │   ├── config.py  # pydantic-settings from .env
│   │   ├── database.py# SQLAlchemy async engine + Valkey client + migrations; session created_at tracking
│   │   ├── dependencies.py  # FastAPI DI providers
│   │   └── models.py  # SQLAlchemy ORM models (User)
│   └── routes/
│       ├── admin.py   # GET /api/admin/* (admin dashboard — stats, users, sessions)
│       ├── auth.py    # POST /api/auth/{login,register,logout}, GET /api/auth/me
│       ├── chat.py    # POST /api/chat, GET /api/chat/{history,sessions}
│       ├── health.py  # GET /api/health
│       └── users.py   # CRUD /api/users
├── frontend/          # React + Vite SPA
│   ├── src/
│   │   ├── Admin.tsx  # Admin dashboard (overview, users, sessions tabs)
│   │   ├── App.tsx    # Auth + Chat UI + admin routing
│   │   └── api.ts     # Fetch client (chat, auth, users, admin)
│   └── nginx.conf     # Production SPA + API proxy
├── skills/            # pydantic-ai skill definitions
└── docker-compose.yml # Full stack orchestration (docker compose / podman compose)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Uvicorn |
| **AI** | pydantic-ai-slim, pydantic-ai-harness, pydantic-ai-shields |
| **Database** | PostgreSQL 16 (asyncpg + SQLAlchemy async) |
| **Cache** | Valkey 8 (Redis-compatible, via `redis[hiredis]`) |
| **Frontend** | React 18, TypeScript 5.6, Vite 6, Tailwind CSS 3.4 |
| **Infra** | Docker Compose / Podman Compose (backend, frontend/nginx, postgres, valkey) |
| **Pkg Mgr** | `uv` (Python), `bun` (frontend) |

## Build & Run Commands

```bash
make install            # uv sync — install Python deps
make run                # Start backend on :8000 (reload)

make frontend-install   # bun install
make frontend-dev       # Start Vite on :5173

make compose-up         # Start all containers (detached; auto-detects podman or docker)
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
- **API client** isolated in `api.ts` — exports for chat (`sendMessage`, `getHistory`), auth (`login`, `register`, `getMe`, `logout`), users (`listUsers`, `createUser`, `getUserSessions`), and admin (`getAdminStats`, `adminListUsers`, `adminUpdateUser`, `adminListSessions`, `adminDeleteSession`). Auth token managed via `localStorage` + `Authorization: Bearer` header helpers.
- **Session metadata**: Session creation timestamps (`chat:{session_id}:created_at`) are stored in Valkey via `SETNX` on the first message. The `GET /api/users/{user_id}/sessions` endpoint returns `session_id`, `title`, `created_at` (ISO-8601), and `message_count`, sorted newest-first. The frontend displays relative time via `formatSessionTime()` in the sessions sidebar.

## Key Architecture Decisions

### Dependency Injection
`dependencies.py` provides `get_settings()`, `get_agent_service()`, and `get_db_session()` as FastAPI `Depends()` callables. `AgentService` is lazily initialized (not built at import time). `AppBuilder` accepts optional `Settings` for test overrides.

### Capabilities Stack
Agent capabilities are assembled in `AgentService._build_capabilities()` — a list that includes code execution, web search, MCP, sub-agents, cost tracking, input/tool guards, secret redaction, and stuck-loop detection.

### Lifecycle
FastAPI's `lifespan` context manager handles startup (initialize agent, DB engine, Valkey) and shutdown (close agent, DB pool, Valkey connection). See `AppBuilder._lifespan()` in `app.py`.

### Configuration
Environment variables loaded from `.env` via `pydantic-settings` (`backend/core/config.py`). Key vars: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LOGFIRE_TOKEN`, `DATABASE_URL`, `VALKEY_URL`.

## Common Pitfalls

1. **Container DNS caching**: nginx caches DNS at startup. Podman does not use Docker's `127.0.0.11` resolver, so the `resolver` + variable trick doesn't work. If the backend restarts, also restart the frontend container (`podman compose restart frontend` or `docker compose restart frontend`).
2. **Slow LLM responses**: The LLM may take minutes to respond. Nginx `proxy_read_timeout` is set to 600s. Backend timeouts should match.
3. **Logfire is optional**: `logfire.configure()` is wrapped in `try/except` — omit `LOGFIRE_TOKEN` to disable.
4. **API key for local LLMs**: Set `LLM_API_KEY=no-key-required` (or leave empty) for llama.cpp / local endpoints; the OpenAI client requires a non-None value.
5. **uv vs pip**: Always use `uv sync` / `uv add`, never `pip install`. The lock file is `uv.lock`.
6. **bun for frontend**: Use `bun install` / `bun run dev` for frontend, not `npm`.
7. **Container orchestration**: Backend depends on postgres + valkey being healthy. Use `depends_on` with `condition: service_healthy`. Run with `docker compose up -d` or `podman compose up -d`. The Makefile auto-detects the available runtime.
8. **Schema migrations**: `init_db()` in `database.py` runs `Base.metadata.create_all` followed by `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns. Existing tables are never rebuilt — new columns are added in-place.
9. **bcrypt on container restart**: `bcrypt` is a native dependency. If the container fails to start with an import error, ensure `bcrypt` is in `pyproject.toml` and `uv sync` was run during the container build.

## Key Conventions

- `db.flush()` in repositories, not `commit()`

## More Info

- `docs/architecture.md` - Architecture details
- `docs/patterns.md` - Code patterns
- `docs/adding_features.md` - How to add features