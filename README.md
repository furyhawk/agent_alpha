# Agent Alpha 🤖

An agentic AI application built with **pydantic-ai**, featuring a FastAPI backend and a React + Vite frontend.

---

## Project Structure

```
agent_alpha/
├── agent_a.py              # Standalone agent runner (CLI)
├── pyproject.toml           # Python deps & metadata
├── backend/
│   ├── app.py               # FastAPI application factory
│   ├── main.py              # Uvicorn entry point
│   ├── core/
│   │   └── agent.py         # Agent lifecycle & inference
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

### 1. Python environment

```bash
uv sync                     # Create .venv & install deps
```

### 2. Backend (FastAPI)

```bash
uv run python -m backend.main
# → http://localhost:8000
# → API docs at http://localhost:8000/docs
```

### 3. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to the FastAPI backend.

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
- **Memory persistence** (`./MEMORY.md`)
- **Sub-agents** (e.g., `researcher`)
- **Task tracking** with subtask support
- **Safety shields**: cost caps, input guards, tool approval, secret redaction, stuck-loop detection

---

## Skills

Skills are loaded from the `./skills/` directory. See each skill's `SKILL.md` for details.

- `analyzing-financial-statements/`
- `applying-brand-guidelines/`
- `creating-financial-models/`
