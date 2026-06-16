---
name: agent-refactor-plan
description: Plan to refactor backend/core/agent.py to follow Repository+Service pattern and agents.md guidelines.
metadata:
  type: project
---

# Context
The current implementation of `/backend/core/agent.py` violates the "Repository + Service" architecture described in `docs/architecture.md`. It contains heavy configuration logic, mixed business logic (RAG tool building), and direct filesystem persistence logic. The goal is to refactor this into a clean, layered architecture as specified in the new `agents.md`.

# Proposed Approach
I will refactor the agent system by extracting concerns into their respective layers:
1. **Factory Layer**: Extract initialization logic (Logfire, model providers) from `AgentService` into a new `AgentFactory` in `backend/services/`.
2. **Repository Layer**: Create a `MemoryRepository` to handle local filesystem persistence for the agent's memory.
3. **RAG Service**: Move RAG tool construction out of the core agent logic and into a dedicated `RAGService`.
4. **Thin Core**: Refactor `AgentService` in `/backend/core/agent.py` to act as a thin orchestrator that receives pre-configured agents and dependencies via injection.

# Implementation Steps

### Phase 1: Infrastructure Setup
- Create `backend/repositories/memory_repository.py` to encapsulate `LocalBackend` logic.
- Create `backend/services/agent_factory.py` to house the complex initialization logic currently in `AgentService.initialize`.
- Create `backend/services/rag_service.py` to handle RAG tool construction.

### Phase 2: Core Refactoring
- Modify `backend/core/agent.py`:
    - Remove `LocalBackend` and path resolution (Move to `MemoryRepository`).
    - Remove initialization logic (Move to `AgentFactory`).
    - Remove `_build_rag_tools` (Move to `RAGService`).
    - Update `AgentService` to accept a pre-constructed agent and dependencies.

### Phase 3: Dependency Injection & Integration
- Update FastAPI routes or the main entry point to use the new `AgentFactory` and `RAGService`.
- Ensure all tools in the `Skill` system are correctly registered via the new services.

# Critical Files
- `backend/core/agent.py`
- `backend/services/agent_factory.py`
- `backend/repositories/memory_repository.py`
- `backend/services/rag_service.py`

# Verification
- Run `make run` to ensure the backend starts.
- Test the `ask` endpoint to verify that the agent still responds with correct RAG results and memory persistence.
- Verify that the new `AgentFactory` correctly initializes all subagents and skills as before.
