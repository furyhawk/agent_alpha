"""Forgiving write-todos capability — handles empty tool call arguments gracefully.

Some local LLMs have weak function-calling capabilities and generate
empty ``{}`` instead of the required ``todos`` parameter when calling
``write_todos``.  This capability intercepts the validation error and
supplies an empty ``todos`` list, allowing the tool to execute with a
no-op result instead of crashing the agent after exhausting retries.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import RawToolArgs, ValidatedToolArgs
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_core import ValidationError


class ForgiveWriteTodosCapability(AbstractCapability[Any]):
    """Catches ``ValidationError`` when ``write_todos`` is called with
    missing ``todos`` and supplies an empty list instead.

    This prevents the agent from crashing when a local model generates
    malformed tool call arguments (e.g. ``write_todos({})``).
    """

    async def on_tool_validate_error(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: RawToolArgs,
        error: ValidationError | ModelRetry,
    ) -> ValidatedToolArgs:
        if call.tool_name == "write_todos" and isinstance(error, ValidationError):
            # Check if the error is about the missing 'todos' field
            for err in error.errors():
                if err.get("loc") == ("todos",) and err.get("type") == "missing":
                    return {"todos": []}
        raise error
