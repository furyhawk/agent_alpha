# Agent Implementation & Architecture

## Overview
This document outlines the architecture and implementation requirements for AI agents within the Agent Alpha platform. All agent logic must strictly adhere to the **Repository + Service** pattern defined in `/docs/architecture.md`.

## Agent Structure
Agents are built using the `pydantic-ai` framework. Every agent must be modularized as follows:

### 1. Core Agent (`backend/core/`)
The core module should only handle high-level agent lifecycle and basic configuration. It is a "Thin Service" that orchestrates the interaction between the user request, the dependencies, and the LLM.

### 2. Factory Layer (`backend/services/factory/`)
Complex logic for initializing agents—including model provider setup, logfire integration, tool registration, and environment variable validation—must reside in specialized factories (e.g., `AgentFactory`).

### 3. Service Layer (`backend/services/`)
Business logic related to agent capabilities must be moved to dedicated services:
- **RAG Service**: Handles the construction of retrieval tools and interaction with vector stores.
- **Skill Service**: Manages the discovery, registration, and execution of modular "Skills".
- **Memory Service**: Orchestrates persistence of conversation history and state.

### 4. Repository Layer (`backend/repositories/`)
All direct interactions with data sources (SQLAlchemy models, Milvus vector store, local filesystems) must be abstracted into repositories.
- Repositories are responsible for CRUD operations and state persistence.
- Repositories use `db.flush()` to ensure data integrity without premature commits in transactional blocks.

## Tooling & Skills
- **Tools**: Must be decorated with `@agent.tool`. Descriptions must be highly descriptive for LLM comprehension.
- **Skills**: Modular capabilities stored in `/skills/`. These are registered by the `SkillService` and injected into agents as tools.
- **Dependencies**: Use FastAPI's Dependency Injection system to provide Repositories and Services to Agent logic via `RunContext`.

## Patterns
- **Async First**: All agent operations must be asynchronous.
- **Thin Routes**: FastAPI endpoints must only validate input schemas and call the appropriate Service.
- **Dependency Injection**: Never instantiate repositories or services directly inside an agent tool; always use the provided context dependencies.
