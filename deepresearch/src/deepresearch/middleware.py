"""Audit, permission, and rate-limit capabilities for DeepResearch.

- AuditCapability: tracks tool usage stats (call count, duration, breakdown)
- PermissionCapability: blocks access to sensitive paths via ModelRetry
- RateLimitRetryCapability: catches rate-limit errors and auto-retries
  with exponential backoff (model-level + tool-level)
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import AbstractCapability

from pydantic_deep.deps import DeepAgentDeps

logger = logging.getLogger(__name__)


@dataclass
class ToolUsageStats:
    """Accumulated tool usage statistics."""

    call_count: int = 0
    total_duration_ms: float = 0
    last_tool: str = ""
    tools_used: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class AuditCapability(AbstractCapability[DeepAgentDeps]):
    """Capability that tracks tool usage for frontend display."""

    stats: ToolUsageStats = field(default_factory=ToolUsageStats)
    _tool_start_times: dict[str, float] = field(default_factory=dict, repr=False)

    def get_stats(self) -> ToolUsageStats:
        return self.stats

    def reset_stats(self) -> None:
        self.stats = ToolUsageStats()
        self._tool_start_times.clear()

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> Any:
        self._tool_start_times[tool_def.name] = time.monotonic()
        return args

    async def after_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        result: Any,
    ) -> Any:
        tool_name = tool_def.name
        self.stats.call_count += 1
        self.stats.last_tool = tool_name
        self.stats.tools_used[tool_name] += 1

        start = self._tool_start_times.pop(tool_name, None)
        if start is not None:
            duration = (time.monotonic() - start) * 1000
            self.stats.total_duration_ms += duration

        return result


# Patterns for sensitive paths that should be blocked
BLOCKED_PATH_PATTERNS = [
    r"/etc/passwd",
    r"/etc/shadow",
    r"\.env$",
    r"\.env\.",
    r"/root/",
    r"\.ssh/",
    r"/proc/",
    r"/sys/",
    r"id_rsa",
    r"id_ed25519",
]

# File-related tools whose path arguments should be checked
FILE_TOOLS = {"read_file", "write_file", "edit_file", "glob", "grep"}


@dataclass
class PermissionCapability(AbstractCapability[DeepAgentDeps]):
    """Capability that blocks access to sensitive paths via ModelRetry."""

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> Any:
        tool_name = tool_def.name
        if tool_name not in FILE_TOOLS:
            return args

        tool_args = args if isinstance(args, dict) else {}
        path = tool_args.get("path", "") or tool_args.get("pattern", "")

        for pattern in BLOCKED_PATH_PATTERNS:
            if re.search(pattern, str(path)):
                logger.warning(
                    f"PermissionCapability BLOCKED: {tool_name}(path={path}) "
                    f"matches pattern '{pattern}'"
                )
                raise ModelRetry(
                    f"Access denied: path matches blocked pattern '{pattern}'. "
                    f"Try a different path."
                )
        return args


# OpenAI rate-limit error markers (both Responses API and Chat Completions)
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "429",
    "too many requests",
    "tokens per min",
    "TPM",
    "requests per min",
    "RPM",
)


def _is_rate_limit_error(error: BaseException) -> bool:
    """Check if an exception is a rate-limit error.

    Detects by:
    1. ``status_code == 429`` attribute (for ``ModelHTTPError``)
    2. String matching on the error message
    """
    # Check for HTTP 429 status code attribute (ModelHTTPError, httpx, etc.)
    status_code = getattr(error, "status_code", None)
    if status_code is not None and status_code == 429:
        return True

    msg = str(error).lower()
    return any(marker in msg for marker in _RATE_LIMIT_MARKERS)


def _parse_retry_after(error: BaseException) -> float | None:
    """Extract retry-after seconds from error message or return None."""
    msg = str(error)
    # Look for "try again in X.Ys" or "try again in X.Y s"
    match = re.search(r"try again in\s+([\d.]+)\s*s", msg)
    if match:
        return float(match.group(1))
    # Look for "Retry-After: X" or "retry_after: X"
    match = re.search(r"(?:retry[_-]after|Retry[_-]After)[:\s]+(\d+)", msg)
    if match:
        return float(match.group(1))
    return None


@dataclass
class RateLimitRetryCapability(AbstractCapability[DeepAgentDeps]):
    """Capability that catches rate-limit errors and auto-retries with
    exponential backoff.

    Uses TWO interception points for maximum reliability:

    **``wrap_model_request``** (primary)
    Wraps the model API call directly. When the handler raises a rate-limit error,
    sleeps for the backoff duration and raises ``ModelRetry``, which pydantic-ai
    catches immediately and re-drives the request. This is the most direct path —
    the error never reaches ``on_model_request_error``.

    **``on_model_request_error``** (secondary backstop)
    Only triggered if ``wrap_model_request`` is not available or doesn't handle
    the error (e.g., another capability's wrapper suppresses it). Same backoff logic.

    **``on_tool_execute_error``** (tool-level)
    Handles rate-limit errors from tool calls (e.g., search MCP servers, browser
    automation). Same backoff logic shared via ``_retry_or_raise()``.

    Backoff is tracked per-run via ``for_run()``.
    """

    base_delay: float = 1.0
    """Initial delay in seconds before the first retry."""

    max_delay: float = 120.0
    """Maximum delay in seconds (cap on exponential backoff)."""

    max_retries_per_run: int = 10
    """Maximum number of rate-limit retries allowed per run."""

    jitter: float = 0.1
    """Fraction of jitter to add (0.0 = no jitter)."""

    # --- per-run state, reset via for_run() ---
    _attempts: int = 0
    _last_error: str = ""

    async def for_run(self, ctx: Any) -> RateLimitRetryCapability:
        """Return a fresh instance for each run (isolated state)."""
        return RateLimitRetryCapability(
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            max_retries_per_run=self.max_retries_per_run,
            jitter=self.jitter,
        )

    def _compute_delay(self) -> float:
        """Compute exponential backoff delay with jitter."""
        delay = min(
            self.base_delay * (2 ** self._attempts),
            self.max_delay,
        )
        jitter_amount = delay * self.jitter
        delay += random.uniform(-jitter_amount, jitter_amount)
        return max(0.1, delay)

    async def _retry_or_raise(
        self,
        *,
        source: str,
        tool_name: str | None = None,
        error: BaseException,
    ) -> None:
        """Shared rate-limit retry logic: track attempts, sleep, raise
        ``ModelRetry`` or re-raise the original error if budget exhausted.

        Never returns normally — always raises.
        """
        self._attempts += 1
        if self._attempts > self.max_retries_per_run:
            logger.error(
                f"Rate-limit retry budget exhausted ({self.max_retries_per_run}) "
                f"from {source}. Last error: {error}"
            )
            raise error

        retry_after = _parse_retry_after(error)
        delay = retry_after if retry_after is not None else self._compute_delay()
        self._last_error = str(error)[:200]

        label = f"{source}/{tool_name}" if tool_name else source
        logger.warning(
            f"Rate limit hit on {label} "
            f"(attempt {self._attempts}). Retrying in {delay:.1f}s. "
            f"Error: {self._last_error}"
        )

        await asyncio.sleep(delay)
        raise ModelRetry(
            f"Rate limit hit on {label} "
            f"(attempt {self._attempts}). Waited {delay:.1f}s. "
            f"Please retry."
        )

    async def wrap_model_request(
        self,
        ctx: Any,
        *,
        request_context: Any,
        handler: Any,
    ) -> Any:
        """Primary rate-limit interception: wraps the model API call.

        If the handler raises a rate-limit error, we sleep and raise
        ``ModelRetry``. pydantic-ai catches ``ModelRetry`` from
        ``wrap_model_request`` immediately (before any capability's
        ``on_model_request_error`` is called), making this the most
        reliable interception point.
        """
        try:
            return await handler(request_context)
        except BaseException as e:
            if _is_rate_limit_error(e):
                await self._retry_or_raise(source="model", error=e)
            raise

    async def on_model_request_error(
        self,
        ctx: Any,
        *,
        request_context: Any,
        error: BaseException,
    ) -> Any:
        """Secondary backstop: handles rate-limit errors from model API calls.

        Only reached if ``wrap_model_request`` didn't handle the error
        (e.g., another capability's wrapper caught and re-raised it, or
        the error came from outside the wrapper).
        """
        if not _is_rate_limit_error(error):
            raise error
        await self._retry_or_raise(source="model", error=error)

    async def on_tool_execute_error(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        error: BaseException,
    ) -> Any:
        """Handle rate-limit errors from tool calls (e.g., search MCP tools)."""
        if not _is_rate_limit_error(error):
            raise error
        await self._retry_or_raise(
            source="tool",
            tool_name=tool_def.name,
            error=error,
        )
