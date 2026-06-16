import os as _os
from pydantic_ai_backends import LocalBackend

class MemoryRepository:
    """Handles local filesystem persistence for agent memory."""

    def __init__(self) -> None:
        # In /backend/repositories/memory_repository.py,
        # the project root is 3 levels up from this file.
        self._agent_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        self._backend = LocalBackend(root_dir=self._agent_root)

    @property
    def backend(self) -> LocalBackend:
        return self._backend

    @property
    def memory_dir(self) -> str:
        return _os.path.join(self._agent_root, ".agent_memory")
