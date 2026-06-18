# Agent Alpha 🤖α

An agentic AI application built with **pydantic-ai**, featuring a FastAPI backend and a React + Vite frontend.

---

## Project Structure

```
agent_alpha/
├── .env.example             # Environment variable template
├── .gitignore
├── Makefile                 # Common dev commands
├── docker-compose.yml       # Full-stack orchestration
├── pyproject.toml           # Python deps & metadata
├── backend/
│   ├── app.py               # FastAPI application factory
│   ├── main.py              # Uvicorn entry point
│   ├── core/
│   │   ├── agent.py         # Agent lifecycle & inference
│   │   ├── config.py        # pydantic-settings config
│   │   ├── database.py      # SQLAlchemy engine, Valkey client, migrations
│   │   ├── exceptions.py    # NotFoundError, BadRequestError
│   │   └── models.py        # SQLAlchemy ORM models (User)
│   ├── db/models/           # RAG ORM models (RAGDocument, SyncLog, SyncSource, ChatFile)
│   ├── repositories/        # Async CRUD helpers for DB models
│   ├── routes/
│   │   ├── admin.py         # Admin dashboard (stats, users, sessions)
│   │   ├── auth.py          # Auth (login, register, logout, me)
│   │   ├── chat.py          # POST /api/chat
│   │   ├── health.py        # GET  /api/health
│   │   ├── rag.py           # RAG endpoints (collections, search, upload, sync)
│   │   └── users.py         # User CRUD
│   ├── schemas/             # Pydantic API schemas
│   ├── services/
│   │   ├── file_storage.py  # Local filesystem storage
│   │   ├── file_upload.py   # File validation & parsing
│   │   ├── rag_document.py  # RAG document tracking & lifecycle
│   │   ├── rag_status.py    # Redis pub/sub SSE streaming
│   │   ├── rag_sync.py      # RAG sync operations
│   │   ├── sync_source.py   # Sync source management
│   │   └── rag/             # Core RAG pipeline
│   │       ├── config.py    # RAG settings, embedding dimensions
│   │       ├── documents.py # Document parsing (PDF, DOCX, TXT, MD)
│   │       ├── embeddings.py# OpenAI-compatible embedding provider
│   │       ├── image_describer.py  # LLM vision for document images
│   │       ├── ingestion.py # Parse → chunk → embed → store pipeline
│   │       ├── models.py    # RAG data models
│   │       ├── reranker.py  # Cross-encoder reranking
│   │       ├── retrieval.py # Multi-stage vector search
│   │       └── vectorstore.py# Milvus vector store client
│   ├── rag/connectors.py    # Sync source connector registry
│   └── worker/
│       ├── dispatcher.py    # In-process async task dispatcher
│       ├── arq_settings.py  # ARQ config (for future Redis-backed worker)
│       └── tasks/rag_tasks.py  # Ingestion & sync task functions
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── nginx.conf           # Production SPA + API proxy
│   └── src/
│       ├── main.tsx         # React entry
│       ├── App.tsx          # Chat UI + admin/RAG routing
│       ├── Admin.tsx        # Admin dashboard
│       ├── RagDashboard.tsx # RAG dashboard (overview, documents, collections)
│       ├── api.ts           # API client
│       └── index.css        # Tailwind base
├── skills/                  # Agent skill definitions
└── docs/
    ├── architecture.md
    └── patterns.md
```

---

## Prerequisites

- **Python 3.12+** with `uv`
- **Bun** (for the frontend)
- **Podman** or **Docker** (for containers)
- **llama.cpp** server (or any OpenAI-compatible LLM endpoint)

---

## Quick Start

### 1. LLM Server (llama.cpp)

Start the llama.cpp server with embeddings support for both chat and RAG:

```bash
nohup llama-server \
  -hf unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL \
  --temp 1.0 --top-p 0.95 --top-k 64 \
  --presence-penalty 1.5 \
  --host 0.0.0.0 --port 8011 \
  --reasoning off \
  --embeddings --pooling mean \
  --no-ui \
  > server.log 2>&1 &
```

> **Note**: The `--embeddings --pooling mean` flags are required for RAG. Without them, the `/v1/embeddings` endpoint returns a 501 error.

### 2. Configuration

```bash
cp .env.example .env   # then edit .env with your LLM endpoint & model
```

### 3. Backend (FastAPI)

```bash
make install            # uv sync — create .venv & install deps
make run                # → http://localhost:8000
                        # → API docs at http://localhost:8000/docs
```

### 4. Frontend (React + Vite)

```bash
make frontend-install   # bun install
make frontend-dev       # → http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to the FastAPI backend.

### 5. Full Stack (Docker Compose)

Starts all services — backend, frontend, PostgreSQL, Valkey, Milvus (vector DB), etcd, and MinIO:

```bash
make compose-up         # start all containers
make compose-logs       # follow logs
make compose-down       # stop everything
```

> **Podman (rootless)** — the Makefile auto-detects Podman, but if you need the Docker socket path, use:
> ```bash
> DOCKER_SOCK=/run/user/1000/podman/podman.sock podman compose up -d
> ```

> Containers are rebuilt automatically when source changes via the compose build cache. Use `make compose-rebuild` to force a full rebuild.

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

| Variable              | Default                                        | Description                              |
| --------------------- | ---------------------------------------------- | ---------------------------------------- |
| `LLM_BASE_URL`        | `http://localhost:11434/v1`                    | OpenAI-compatible LLM endpoint           |
| `LLM_MODEL`           | `llama`                                        | LLM model name                           |
| `LLM_API_KEY`         | `no-key-required`                              | API key (set for OpenAI / cloud LLMs)    |
| `DATABASE_URL`        | `postgresql+asyncpg://...@localhost:5432/...`  | PostgreSQL connection                    |
| `VALKEY_URL`          | `redis://localhost:6379/0`                     | Valkey / Redis connection                |
| `MILVUS_URI`          | `http://localhost:19530`                       | Milvus vector database endpoint          |
| `EMBEDDING_BASE_URL`  | *(defaults to `LLM_BASE_URL`)*                 | Server for `/v1/embeddings` (RAG)        |
| `EMBEDDING_API_KEY`   | *(defaults to `LLM_API_KEY`)*                  | API key for embedding endpoint           |

---

## API Endpoints

| Method | Path                                    | Description                          |
| ------ | --------------------------------------- | ------------------------------------ |
| GET    | `/api/health`                           | Health check                         |
| POST   | `/api/auth/{login,register,logout}`     | Authentication                       |
| GET    | `/api/auth/me`                          | Current user profile                 |
| POST   | `/api/chat`                             | Send a message to the agent          |
| GET    | `/api/chat/history`                     | Chat history for a session           |
| GET    | `/api/chat/sessions`                    | List user's chat sessions            |
| CRUD   | `/api/users`                            | User management                      |
| GET    | `/api/admin/{stats,users,sessions}`     | Admin dashboard (admin role)         |

### RAG Endpoints

| Method | Path                                            | Description                          |
| ------ | ----------------------------------------------- | ------------------------------------ |
| GET    | `/api/rag/collections`                          | List Milvus collections              |
| POST   | `/api/rag/collections`                          | Create a collection                  |
| GET    | `/api/rag/collections/{name}`                   | Collection info (vectors, dim, etc.) |
| DELETE | `/api/rag/collections/{name}`                   | Delete a collection                  |
| POST   | `/api/rag/search`                               | Vector search across collections     |
| GET    | `/api/rag/documents`                            | List tracked documents               |
| POST   | `/api/rag/upload`                               | Upload & ingest a document           |
| DELETE | `/api/rag/documents/{id}`                       | Delete document (cascade)            |
| POST   | `/api/rag/documents/{id}/retry`                 | Retry failed ingestion               |
| GET    | `/api/rag/documents/{id}/download`              | Download original file               |
| GET    | `/api/rag/sync-logs`                            | List sync operation logs             |
| POST   | `/api/rag/sync`                                 | Trigger local sync                   |
| GET    | `/api/rag/status`                               | SSE stream for ingestion events      |
| CRUD   | `/api/rag/sources`                              | Sync source configuration            |

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

## RAG (Retrieval-Augmented Generation)

The RAG pipeline ingests documents (PDF, DOCX, TXT, MD) and makes them searchable via vector embeddings.

### Pipeline

```
Upload → Validate → Store file → DB record → Parse → Chunk → Embed → Milvus → Searchable
```

### Storage Architecture

| Component   | Technology       | Persistence                    |
| ----------- | ---------------- | ------------------------------ |
| Vector DB   | Milvus 2.4       | MinIO (object store) + etcd    |
| Metadata    | PostgreSQL 16    | Docker volume                  |
| File store  | Local filesystem | `media/` directory in backend  |
| Task queue  | In-process       | (ARQ-ready for production)     |

### Requires

The embedding server must support the OpenAI-compatible `/v1/embeddings` endpoint. For llama.cpp, start the server with:

```bash
nohup llama-server \
  -hf unsloth/gemma-4-12B-it-qat-GGUF:UD-Q4_K_XL \
  --temp 1.0 --top-p 0.95 --top-k 64 \
  --presence-penalty 1.5 \
  --host 0.0.0.0 --port 8011 \
  --reasoning off \
  --embeddings --pooling mean \
  --no-ui \
  > server.log 2>&1 &
```

Then set in `.env`:

```ini
EMBEDDING_BASE_URL=http://host.containers.internal:8011/v1
```

### Frontend

The **RAG Dashboard** is accessible to admin users via the **RAG** button in the chat header. It provides:

- **Overview** — collection stats, document status breakdown, sync history
- **Documents** — file upload widget, tracked document table with status/retry/delete
- **Collections** — Milvus collection management with vector counts and dimensions

---

## Skills

Skills are loaded from the `./skills/` directory. See each skill's `SKILL.md` for details.

- `analyzing-financial-statements/`
- `applying-brand-guidelines/`
- `creating-financial-models/`
