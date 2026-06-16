# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend (Python / FastAPI)
- **Install dependencies**: `make install` (runs `uv sync`)
- **Run backend (dev)**: `make run` (runs `uv run python -m backend.main` with reload)
- **Setup environment**: `make setup` (copies `.env.example` to `.env` and runs the app)

### Frontend (React / Vite / Bun)
- **Install dependencies**: `make frontend-install` (runs `bun install`)
- **Run dev server**: `make frontend-dev` (runs `bun run dev`)
- **Build production**: `make frontend-build` (runs `bun run build`)

### Orchestration & Containers
- **Start all services**: `make compose-up` (Docker/Podman compose)
- **Follow logs**: `make compose-logs`
- **Stop all services**: `make compose-down`
- **Force rebuild images**: `make compose-rebuild`

### Maintenance
- **Clean artifacts**: `make clean`

## Architecture & Structure

### Big Picture Overview
Agent Alpha is a full-stack agentic AI application consisting of a FastAPI backend, a React frontend, and a RAG (Retrieval-Augmented Generation) pipeline. It utilizes **pydantic-ai** for agent logic and **uv** for Python dependency management.

### Backend Architecture (`/backend`)
The backend follows a layered architecture:
- **Core (`/backend/core`)**: The heart of the application. Contains configuration (`config.py`), database engine initialization (`database.py`), ORM models (`models.py`), and the primary agent lifecycle/inference logic (`agent.py`).
- **Database & Repositories**: 
    - **Models**: SQL Alchemy ORM models are split between general domain models (in `core`) and RAG-specific models (in `db/models` like `ChatFile`, `RagDocument`).
    - **Repositories**: Abstracted CRUD operations for all DB models are located in `/backend/repositories`.
- **RAG Pipeline (`/backend/rag`)**: Handles the document ingestion lifecycle. 
    - `connectors.py` manages sync sources.
    - `ingestion.py` manages the Parse → Chunk → Embed → Store pipeline.
    - `retrieval.py` and `reranker.py` handle multi-stage vector search and scoring.
    - `vectorstore.py` interfaces with Milvus.
- **Services**: Domain-specific logic for file storage, RAG tracking, status streaming (via Redis/SSE), and synchronization.
- **Routes & Schemas**: FastAPI endpoints (`/routes`) are paired with Pydantic models (`/schemas`) for request validation and response serialization.
- **Worker**: Handles asynchronous tasks (like heavy RAG ingestion) via an in-process dispatcher, designed to eventually move to a Redis-backed ARQ setup.

### Frontend Architecture (`/frontend`)
A modern React SPA built with Vite and Tailwind CSS.
- **Core Components**: `App.tsx` handles routing between the main chat UI, the Admin dashboard, and the RAG management dashboard.
- **API Client**: Centralized API interaction logic in `api.ts`.
- **State & Proxy**: The dev server proxies `/api/*` requests to the FastAPI backend.

### Skills (`/skills`)
Modular agent capabilities are defined as "Skills". Each skill contains its own instructions and logic, allowing the main agent to dynamically expand its toolkit (e.g., financial analysis, brand guidelines).

## Key Patterns
- **Async First**: Most backend operations use `async/await` for database access and external API calls.
- **Dependency Injection**: Used extensively in FastAPI routes via the `dependencies.py` module.
- **RAG Flow**: Document Upload $\rightarrow$ Validation $\rightarrow$ Persistence $\rightarrow$ Parsing $\rightarrow$ Chunking $\rightarrow$ Embedding $\rightarrow$ Milvus Storage.
