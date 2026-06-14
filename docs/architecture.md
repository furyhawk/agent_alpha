# Architecture Guide

This project follows a **Repository + Service** layered architecture.
Every feature — users, conversations, files, RAG documents, sync sources — uses
the same pattern: **Models → Schemas → Repositories → Services → Endpoints**.

## Request Flows

### RAG features (layered pattern)

```
HTTP Request → Route → Service → Repository → Database (PostgreSQL)
                  ↓
              Response ← Service ← Repository ←
```

Routes delegate to **services** (business logic), which delegate to
**repositories** (data access). Repositories operate on **ORM models**
and return domain objects. Responses are serialized through **schemas**.

```
backend/
├── db/models/          # SQLAlchemy ORM models
├── schemas/            # Pydantic request/response schemas
├── repositories/       # Async CRUD helpers (no business logic)
├── services/           # Business logic layer
└── routes/             # FastAPI endpoints (thin — delegate to services)
```

### Core features (flat pattern — users, auth, chat)

```
HTTP Request → Route → Service → Repository → Database (PostgreSQL / Valkey)
                  ↓
              Response ← Service ← Repository ←
```

Routes never contain direct database calls. All data access goes through
services, which in turn delegate to repositories.

```
backend/
├── core/
│   ├── database.py     # All DB + Valkey access functions
│   ├── models.py       # User ORM model only
│   └── config.py       # pydantic-settings
└── routes/
    ├── auth.py         # Auth endpoints (login, register, logout)
    ├── users.py        # User CRUD + session listing
    ├── chat.py         # Chat send + history
    ├── admin.py        # Admin dashboard (stats, users, sessions)
    └── health.py       # Health check
```

### API Routes (`api/routes/v1/`)
- HTTP request/response handling
- Input validation via Pydantic schemas
- Authentication and authorization checks
- **Never** contains direct DB calls — always delegates to a service

### Services (`services/`)
- Business logic and validation
- Orchestrates one or more repository calls
- Raises domain exceptions (`NotFoundError`, `AlreadyExistsError`, etc.)
- Manages transaction boundaries

### Repositories (`repositories/`)
- Database operations only
- No business logic
- Uses `db.flush()` not `commit()` (the dependency-injected session manages transactions)
- Returns domain models

### Schemas (`schemas/`)
- Separate `Create`, `Update`, and `Response` models per entity
- `Response` schemas use `model_config = ConfigDict(from_attributes=True)` for ORM conversion

## Data Stores

| Data | Store | Access |
|------|-------|--------|
| Users (auth, profile) | PostgreSQL | `core/database.py` functions + ORM |
| Auth tokens | Valkey (key-value) | `core/database.py` functions |
| Chat messages & sessions | Valkey (lists, sets) | `core/database.py` functions |
| RAG documents, sync logs, chat files | PostgreSQL | Repository → Service → Route |
| RAG vector embeddings | Milvus | `services/rag/vectorstore.py` |

## Session Lifecycle (Valkey)

Chat sessions are stored entirely in Valkey:

```
chat:{session_id}:messages    → List of JSON messages [{role, content, timestamp}]
chat:{session_id}:user_id     → Owner user ID string
chat:{session_id}:title       → Short human-readable title
chat:{session_id}:created_at  → ISO-8601 creation timestamp (SETNX on first msg)
chat:sessions                 → Set of all known session IDs
user:{user_id}:sessions       → Set of session IDs owned by a user
```

## Key Conventions

- **`db.flush()`** in repositories, never `commit()` — the outer service/route
  owns the transaction commit.
- **Settings** use `pydantic-settings` (`Settings` class in `config.py`).
  Field names are snake_case, env vars are UPPER_SNAKE_CASE.
- **Async-first** — all I/O uses `async`/`await` (routes, DB, Valkey).
- **Error handling** — `HTTPException` in routes; `try/except` with graceful
  fallback for optional components (e.g., Logfire).
