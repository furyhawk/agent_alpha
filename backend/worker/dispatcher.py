"""Lightweight async task dispatcher.

Dispatches background tasks to the configured backend.
Currently uses in-process ``asyncio.create_task`` for simplicity.
A Redis-backed ARQ/Taskiq worker can replace this for production use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Task:
    """Represents a background task to be executed."""

    def __init__(self, name: str, kwargs: dict[str, Any]) -> None:
        self.name = name
        self.kwargs = kwargs


class TaskDispatcher:
    """Dispatches background tasks.

    In the current implementation, tasks are executed in-process using
    ``asyncio.create_task``. For production, swap the backend to use
    Redis (ARQ or Taskiq) for cross-process execution.
    """

    def __init__(self) -> None:
        self._running: set[asyncio.Task] = set()

    def delay(self, task_name: str, **kwargs: Any) -> None:
        """Enqueue a task for background execution.

        This returns immediately. The task is executed asynchronously
        in the event loop.
        """
        task = asyncio.create_task(self._execute(task_name, kwargs))
        self._running.add(task)
        task.add_done_callback(self._running.discard)
        logger.debug("Dispatched task: %s (kwargs=%s)", task_name, kwargs)

    async def _execute(self, name: str, kwargs: dict[str, Any]) -> None:
        """Look up the task function and run it."""
        from backend.worker.tasks.rag_tasks import TASK_REGISTRY

        fn = TASK_REGISTRY.get(name)
        if fn is None:
            logger.error("Unknown task: %s", name)
            return
        try:
            await fn({"dispatcher": self}, **kwargs)
        except Exception as exc:
            logger.exception("Task %s failed: %s", name, exc)

    async def shutdown(self) -> None:
        """Cancel all running tasks (called on app shutdown)."""
        for task in self._running:
            task.cancel()
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)
        self._running.clear()


# Module-level singleton
_dispatcher: TaskDispatcher | None = None


def get_dispatcher() -> TaskDispatcher:
    """Return the shared TaskDispatcher singleton."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = TaskDispatcher()
    return _dispatcher


def shutdown_dispatcher() -> None:
    """Shutdown and clear the dispatcher singleton."""
    global _dispatcher
    if _dispatcher is not None:
        # Schedule shutdown on the running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_dispatcher.shutdown())
        except RuntimeError:
            pass  # No running loop — nothing to clean up
        _dispatcher = None
