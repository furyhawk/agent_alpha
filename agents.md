# Agent Implementation & Architecture

## Overview
This document outlines the architecture and implementation requirements for AI agents within the Agent Alpha platform. All agent logic must strictly adhere to the **Repository + Service** pattern defined in `/docs/architecture.md`.

## Agent Structure
Agents are built using the `pydantic-ai` framework. Every agent must be modularized as follows:

### 1. Core Agent (`backend/core/`)
The core module should only handle high-level agent lifecycle and basic configuration. It is a "Thin Service" that orchestrates the interaction between the user request, the dependencies, and the LLM.

### 2. Factory Layer (`backend/services/agent_factory.py`)
Complex logic for initializing agents—including model provider setup, Logfire integration, capability registration (`CodeMode`, `ToolSearch`, `MCP`, `WebSearch`, guardrails), subagent setup, skills discovery, and RAG tool injection—resides in the `build_agent()` factory function.

### 3. Service Layer (`backend/services/`)
Business logic related to agent capabilities must be moved to dedicated services:
- **Agent Factory** (`agent_factory.py`): `build_agent()` wires model, capabilities, subagents, skills, and RAG tools into a configured `pydantic-ai` agent.
- **RAG Service** (`rag_service.py`): Constructs retrieval tools for vector search (by document, by collection) and registers them as agent tools.
- **Chat Service** (`chat_service.py`): Manages conversation history, session metadata, and title generation via Valkey.
- **Auth Service** (`auth_service.py`): Handles user registration, password hashing, login, and token lifecycle.

### 4. Repository Layer (`backend/repositories/`)
All direct interactions with data sources (SQLAlchemy models, Milvus vector store, local filesystems) must be abstracted into repositories.
- Repositories are responsible for CRUD operations and state persistence.
- Repositories use `db.flush()` to ensure data integrity without premature commits in transactional blocks.
- **MemoryRepository** (`memory_repository.py`): Encapsulates agent memory filesystem persistence via `LocalBackend`; provides both the memory directory path and the backend instance for agent `RunContext`.

## Tooling & Skills
- **Tools**: Must be decorated with `@agent.tool`. Descriptions must be highly descriptive for LLM comprehension.
- **Skills**: Modular capabilities stored in `/skills/`. These are automatically discovered and registered by `create_deep_agent` when `include_skills=True` and `skill_directories=["./skills"]` are set in the factory.
- **Dependencies**: Use FastAPI's Dependency Injection system to provide Repositories and Services to Agent logic via `RunContext`.

## Patterns
- **Async First**: All agent operations must be asynchronous.
- **Thin Routes**: FastAPI endpoints must only validate input schemas and call the appropriate Service.
- **Dependency Injection**: Never instantiate repositories or services directly inside an agent tool; always use the provided context dependencies.
