"""Task dispatcher configuration.

In the current implementation, tasks run in-process via
:class:`backend.worker.dispatcher.TaskDispatcher`. For production
deployments with multiple replicas, replace with a Redis-backed
queue (ARQ, Taskiq, or Celery).

To switch to ARQ in the future::

    pip install arq
    arq backend.worker.arq_settings.WorkerSettings
"""

from __future__ import annotations

from backend.core.config import settings
from backend.worker.tasks.rag_tasks import TASK_REGISTRY

# List of registered task functions for ARQ/Taskiq configuration
FUNCTIONS = list(TASK_REGISTRY.values())

# Redis connection info (for future ARQ/Taskiq worker setup)
REDIS_URL = settings.valkey_url

__all__ = ["FUNCTIONS", "REDIS_URL"]

