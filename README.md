# Agent Alpha 🤖

An agentic AI application built with **pydantic-ai**, featuring a FastAPI backend and a React + Vite frontend.

---

## Project Structure

```
agent_alpha/
├── .env.example             # Environment variable template
├── .gitignore
├── Makefile                 # Common dev commands
├── pyproject.toml           # Python deps & metadata
├── backend/
│   ├── app.py               # FastAPI application factory
│   ├── main.py              # Uvicorn entry point
│   ├── core/
│   │   ├── agent.py         # Agent lifecycle & inference
│   │   └── config.py        # pydantic-settings config
│   └── routes/
│       ├── chat.py          # POST /api/chat
│       └── health.py        # GET  /api/health
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── src/
│       ├── main.tsx         # React entry
│       ├── App.tsx          # Chat UI
│       ├── api.ts           # API client
│       └── index.css        # Tailwind base
└── skills/                  # Agent skill definitions
```

---

## Quick Start

### 1. Configuration

```bash
cp .env.example .env   # then edit .env with your LLM endpoint & model
```

### 2. Backend (FastAPI)

```bash
make install            # uv sync — create .venv & install deps
make run                # → http://localhost:8000
                        # → API docs at http://localhost:8000/docs
```

### 3. Frontend (React + Vite)

```bash
make frontend-install   # bun install
make frontend-dev       # → http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to the FastAPI backend.

---

## Makefile Commands

| Command                  | Description                          |
| ------------------------ | ------------------------------------ |
| `make install`           | Install Python deps via `uv sync`    |
| `make run` / `make dev`  | Start the FastAPI backend (reload)   |
| `make frontend-install`  | Install frontend deps via `bun`      |
| `make frontend-dev`      | Start the Vite dev server            |
| `make frontend-build`    | Build frontend for production        |
| `make clean`             | Remove caches and build artifacts    |

---

## Configuration

Environment variables are loaded from `.env` via **pydantic-settings** (see `backend/core/config.py`).

| Variable       | Default                       | Description           |
| -------------- | ----------------------------- | --------------------- |
| `LLM_BASE_URL` | `http://localhost:11434/v1`   | OpenAI-compatible API |
| `LLM_MODEL`    | `llama`                       | Model name to use     |

---

## API Endpoints

| Method | Path          | Description                  |
| ------ | ------------- | ---------------------------- |
| GET    | `/api/health` | Health check                 |
| POST   | `/api/chat`   | Send a message to the agent  |

### POST /api/chat

```json
{ "message": "What are your skills?", "session_id": null }
```

```json
{ "reply": "I can help you with...", "session_id": null }
```

---

## Key Capabilities

- **Code execution** via sandboxed `CodeMode`
- **Web search** (DuckDuckGo / provider-adaptive)
- **MCP tool integration** (Hacker News, etc.)
- **Context management** (sliding window + LLM compaction)
- **Memory persistence**
- **Sub-agents** (e.g., `researcher`)
- **Task tracking** with subtask support
- **Safety shields**: cost caps, input guards, tool approval, secret redaction, stuck-loop detection

---

## Skills

Skills are loaded from the `./skills/` directory. See each skill's `SKILL.md` for details.

- `analyzing-financial-statements/`
- `applying-brand-guidelines/`
- `creating-financial-models/`
