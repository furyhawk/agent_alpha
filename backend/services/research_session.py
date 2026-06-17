"""Research session management — sandbox, checkpointing, persistence."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai.agent import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
from pydantic_ai.messages import TextPart, UserPromptPart
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import Usage
from pydantic_deep import DeepAgentDeps
from pydantic_deep.toolsets.checkpointing import InMemoryCheckpointStore

from backend.core.config import Settings
from backend.services.capabilities import AuditCapability, PermissionCapability

logger = logging.getLogger(__name__)

# ── Text extensions for file preview ───────────────────────────────────

_TEXT_EXTS = {
    "txt", "md", "csv", "tsv", "json", "jsonl", "py", "js", "ts",
    "jsx", "tsx", "html", "htm", "css", "xml", "yaml", "yml", "toml",
    "ini", "cfg", "conf", "sh", "bash", "zsh", "sql", "r", "rb",
    "go", "rs", "java", "c", "cpp", "h", "hpp", "cs", "swift", "kt",
    "lua", "log", "env", "gitignore", "dockerfile",
}

_CONTENT_TYPES: dict[str, str] = {
    "html": "text/html", "htm": "text/html", "css": "text/css",
    "js": "application/javascript", "json": "application/json",
    "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
    "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf",
}


# ── Session State ──────────────────────────────────────────────────────

@dataclass
class UserSession:
    """Per-user research session state."""

    session_id: str
    deps: DeepAgentDeps
    message_history: list[ModelMessage] = field(default_factory=list)
    pending_approval_state: dict[str, Any] = field(default_factory=dict)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    running_task: asyncio.Task[None] | None = field(default=None)
    latest_todos: list[dict[str, Any]] = field(default_factory=list)
    pending_questions: dict[str, asyncio.Future[str]] = field(default_factory=dict)
    checkpoint_store: InMemoryCheckpointStore = field(default_factory=InMemoryCheckpointStore)
    _notified_tasks: set[str] = field(default_factory=set)
    _injected_tasks: set[str] = field(default_factory=set)


# ── Research Session Service ───────────────────────────────────────────

class ResearchSessionService:
    """Manages research agent lifecycle, sessions, and streaming execution."""

    def __init__(self, settings: Settings, rag_service=None):
        self._settings = settings
        self._rag_service = rag_service
        self._agent: Agent | None = None
        self._session_manager: Any = None
        self._user_sessions: dict[str, UserSession] = {}
        self._audit_cap = AuditCapability()
        self._permission_cap = PermissionCapability()
        self._workspaces_dir: Path = Path.cwd() / "workspaces"

    @property
    def agent(self) -> Agent | None:
        return self._agent

    @property
    def audit_cap(self) -> AuditCapability:
        return self._audit_cap

    @property
    def permission_cap(self) -> PermissionCapability:
        return self._permission_cap

    @property
    def workspaces_dir(self) -> Path:
        return self._workspaces_dir

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Initialize the research agent with MCP servers and session manager."""
        from backend.services.agent_factory import build_agent

        # Build the agent (now includes MCP servers, research prompt, etc.)
        self._agent = build_agent(self._settings, rag_service=self._rag_service)

        # Create session manager for Docker sandbox if configured
        if self._settings.pydantic_deep_backend_type == "docker":
            try:
                from pydantic_ai.backend.session_manager import SessionManager
                self._session_manager = SessionManager(
                    default_runtime="python-datascience",
                    default_idle_timeout=self._settings.session_idle_timeout,
                    workspace_root=str(self._workspaces_dir),
                )
                self._session_manager.start_cleanup_loop(
                    interval=self._settings.session_cleanup_interval
                )
                logger.info("Docker sandbox session manager started")
            except ImportError:
                logger.warning(
                    "Docker sandbox requested but pydantic-ai-backend is not available. "
                    "Falling back to state mode. Install with: uv sync"
                )
                self._settings.pydantic_deep_backend_type = "state"
        else:
            logger.info("Research service running in state mode (no Docker sandbox)")

        # Ensure workspace directories exist
        self._workspaces_dir.mkdir(parents=True, exist_ok=True)
        (self._workspaces_dir / "workspace").mkdir(parents=True, exist_ok=True)

    async def shutdown(self) -> None:
        """Release all sessions and shut down."""
        if self._session_manager is not None:
            count = await self._session_manager.shutdown()
            logger.info(f"Shut down {count} Docker sessions")
        self._user_sessions.clear()

    # ── Session Management ──────────────────────────────────────────────

    async def get_or_create_session(
        self, session_id: str, workspace_root: Path | None = None
    ) -> UserSession:
        """Get existing session or create a new one with isolated workspace."""
        if session_id in self._user_sessions:
            return self._user_sessions[session_id]

        ws_root = workspace_root or self._workspaces_dir
        session_dir = ws_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        if self._session_manager is not None:
            # Docker sandbox mode
            sandbox = await self._session_manager.get_or_create(session_id)
            # Seed workspace with context files
            deep_md = ws_root / "workspace" / "DEEP.md"
            if deep_md.exists():
                sandbox.write("/workspace/DEEP.md", deep_md.read_bytes())
            mem_md = ws_root / "workspace" / "MEMORY.md"
            if mem_md.exists():
                sandbox.write("/workspace/MEMORY.md", mem_md.read_bytes())
            deps = DeepAgentDeps(backend=sandbox, checkpoint_store=InMemoryCheckpointStore())
        else:
            # In-memory state mode — use deps without Docker backend
            deps = DeepAgentDeps(
                backend=None,
                checkpoint_store=InMemoryCheckpointStore(),
            )

        cp_store = InMemoryCheckpointStore()
        deps.checkpoint_store = cp_store

        session = UserSession(
            session_id=session_id,
            deps=deps,
            checkpoint_store=cp_store,
        )

        # Restore message history from disk if available
        restored = self._restore_history(session_id)
        if restored:
            session.message_history = restored
            logger.info(f"Restored {len(restored)} messages for session {session_id}")

        # Restore todos from meta
        meta_file = session_dir / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                session.latest_todos = meta.get("todos", [])
            except Exception:
                pass

        self._user_sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> UserSession | None:
        return self._user_sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions, sorted by most recent."""
        results: list[dict[str, Any]] = []
        for sid, session in self._user_sessions.items():
            meta = self._load_meta(sid)
            results.append({
                "session_id": sid,
                "title": meta.get("title", "New Session"),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
                "message_count": len(session.message_history),
            })
        # Also scan disk for sessions not in memory
        for path in sorted(self._workspaces_dir.iterdir(), reverse=True):
            if path.is_dir() and path.name not in self._user_sessions:
                meta_file = path / "meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        results.append({
                            "session_id": path.name,
                            "title": meta.get("title", "New Session"),
                            "created_at": meta.get("created_at", ""),
                            "updated_at": meta.get("updated_at", ""),
                            "message_count": meta.get("message_count", 0),
                        })
                    except Exception:
                        pass

        results.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return results

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its data."""
        if session_id in self._user_sessions:
            session = self._user_sessions[session_id]
            if session.running_task and not session.running_task.done():
                session.running_task.cancel()
            del self._user_sessions[session_id]

        # Remove from disk
        session_dir = self._workspaces_dir / session_id
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir, ignore_errors=True)
            return True
        return False

    def get_session_history(self, session_id: str) -> list[ModelMessage] | None:
        """Get message history for a session."""
        session = self._user_sessions.get(session_id)
        if session:
            return session.message_history
        return self._restore_history(session_id)

    # ── Checkpoints ─────────────────────────────────────────────────────

    async def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        session = self._user_sessions.get(session_id)
        if not session:
            return []
        all_cps = await session.checkpoint_store.list_all() if session.checkpoint_store else []
        return [
            {
                "id": cp.id,
                "label": cp.label,
                "turn": cp.turn,
                "message_count": cp.message_count,
                "metadata": cp.metadata,
            }
            for cp in (all_cps or [])
        ]

    async def rewind_to_checkpoint(
        self, session_id: str, checkpoint_id: str
    ) -> dict[str, Any] | None:
        session = self._user_sessions.get(session_id)
        if not session or not session.checkpoint_store:
            return None
        result = await session.checkpoint_store.rewind(checkpoint_id)
        if result is None:
            return None
        checkpoint_id, messages = result
        session.message_history = messages
        self._persist_history(session)
        self._save_meta(session)
        return {"checkpoint_id": checkpoint_id, "message_count": len(messages)}

    async def fork_session_from_checkpoint(
        self, session_id: str, checkpoint_id: str
    ) -> dict[str, Any] | None:
        session = self._user_sessions.get(session_id)
        if not session or not session.checkpoint_store:
            return None
        result = await session.checkpoint_store.fork(checkpoint_id)
        if result is None:
            return None
        new_id = str(uuid.uuid4())
        deps_copy = DeepAgentDeps(
            backend=session.deps.backend,
            checkpoint_store=InMemoryCheckpointStore(),
        )
        new_session = UserSession(
            session_id=new_id,
            deps=deps_copy,
            message_history=list(result),
        )
        self._user_sessions[new_id] = new_session
        self._persist_history(new_session)
        self._save_meta(new_session)
        return {"session_id": new_id, "message_count": len(result)}

    # ── Agent Execution (Streaming) ─────────────────────────────────────

    async def run_agent_with_streaming(
        self,
        websocket,
        session: UserSession,
        user_prompt: str | list,
        deferred_results: Any = None,
    ) -> None:
        """Run agent with streaming, sending WebSocket events."""
        from pydantic_ai import Agent as PydanticAgent

        agent = self._agent
        if agent is None:
            await websocket.send_json({"type": "error", "content": "Agent not initialized"})
            await websocket.send_json({"type": "done"})
            return

        # Track streamed text for cancel recovery
        session._streamed_text = ""  # type: ignore[attr-defined]
        cancel_text = (
            user_prompt
            if isinstance(user_prompt, str)
            else " ".join(p for p in user_prompt if isinstance(p, str))
        )
        session._current_user_message = cancel_text  # type: ignore[attr-defined]

        # Prepend completed background task results
        if deferred_results is None and user_prompt:
            task_note = self._collect_completed_task_results(session)
            if task_note:
                if isinstance(user_prompt, str):
                    user_prompt = f"{task_note}\n\n---\n\n{user_prompt}"
                elif isinstance(user_prompt, list):
                    for i, part in enumerate(user_prompt):
                        if isinstance(part, str):
                            user_prompt[i] = f"{task_note}\n\n---\n\n{part}"
                            break

        await websocket.send_json({"type": "start"})

        async with agent.iter(
            user_prompt if deferred_results is None else None,
            deps=session.deps,
            message_history=session.message_history,
            deferred_tool_results=deferred_results,
        ) as run:
            async for node in run:
                await self._process_node(websocket, node, run, session)

            result = run.result

            # Emit latest checkpoint
            if session.checkpoint_store:
                try:
                    all_cps = await session.checkpoint_store.list_all()
                    if all_cps:
                        latest = all_cps[-1]
                        await websocket.send_json({
                            "type": "checkpoint_saved",
                            "checkpoint_id": latest.id,
                            "label": latest.label,
                            "turn": latest.turn,
                            "message_count": latest.message_count,
                            "metadata": latest.metadata,
                        })
                except Exception:
                    pass

        # Handle deferred tool requests (needs approval)
        if isinstance(result.output, DeferredToolRequests):
            session.pending_approval_state = {
                "message_history": result.all_messages(),
                "deferred_requests": result.output,
            }
            approval_requests = []
            for call in result.output.approvals:
                approval_requests.append({
                    "tool_call_id": call.tool_call_id,
                    "tool_name": call.tool_name,
                    "args": call.args if isinstance(call.args, dict) else str(call.args),
                })
            await websocket.send_json({
                "type": "approval_required",
                "requests": approval_requests,
            })
            return

        # Update session message history
        session.message_history = result.all_messages()
        self._persist_history(session)
        self._save_meta(session)

        await websocket.send_json({"type": "response", "content": str(result.output)})
        await websocket.send_json({"type": "done"})

    async def handle_approval(
        self, websocket, session: UserSession, approval_response: dict
    ) -> None:
        """Handle approval/denial from frontend and continue agent."""
        if not session.pending_approval_state:
            await websocket.send_json({"type": "error", "content": "No pending approval"})
            return

        deferred_requests = session.pending_approval_state.get("deferred_requests")
        if not deferred_requests:
            await websocket.send_json({"type": "error", "content": "No deferred requests found"})
            return

        tool_approvals: dict[str, bool | ToolApproved | ToolDenied] = {}
        for tool_call_id, approved in approval_response.items():
            if approved:
                tool_approvals[tool_call_id] = ToolApproved()
            else:
                tool_approvals[tool_call_id] = ToolDenied("User denied this tool call.")

        session.message_history = session.pending_approval_state["message_history"]
        session.pending_approval_state = {}

        try:
            results = deferred_requests.build_results(approvals=tool_approvals)
            await self.run_agent_with_streaming(
                websocket, session, "",
                deferred_results=results,
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "content": str(e)})

    # ── Node Processing (Streaming) ─────────────────────────────────────

    async def _process_node(self, websocket, node, run, session):
        """Process a node and send appropriate WebSocket events."""
        from pydantic_ai import Agent as PydanticAgent
        from pydantic_deep.nodes import End, UserPromptNode

        if isinstance(node, UserPromptNode):
            await websocket.send_json({"type": "status", "content": "Processing..."})
        elif PydanticAgent.is_model_request_node(node):
            await self._stream_model_request(websocket, node, run, session)
        elif PydanticAgent.is_call_tools_node(node):
            await self._stream_tool_calls(websocket, node, run, session)
        elif isinstance(node, End):
            await websocket.send_json({"type": "status", "content": "Completed!"})

    async def _stream_model_request(self, websocket, node, run, session):
        """Stream text chunks from a ModelRequestNode."""
        from pydantic_ai.result import (
            FinalResultEvent, PartDeltaEvent, PartStartEvent,
        )
        from pydantic_ai.messages import TextPartDelta, ThinkingPartDelta, ToolCallPartDelta

        await websocket.send_json({"type": "status", "content": "Researching..."})
        current_tool_name: str | None = None

        async with node.stream(run.ctx) as request_stream:
            final_result_found = False
            async for event in request_stream:
                if isinstance(event, PartStartEvent):
                    if hasattr(event.part, "tool_name"):
                        current_tool_name = event.part.tool_name
                        tool_call_id = getattr(event.part, "tool_call_id", None)
                        await websocket.send_json({
                            "type": "tool_call_start",
                            "tool_name": current_tool_name,
                            "tool_call_id": tool_call_id,
                        })
                elif isinstance(event, PartDeltaEvent):
                    await self._handle_part_delta(websocket, event, current_tool_name, session)
                elif isinstance(event, FinalResultEvent):
                    final_result_found = True
                    break

            if final_result_found:
                prev_text = ""
                async for text in request_stream.stream_text():
                    delta = text[len(prev_text):]
                    if delta:
                        await websocket.send_json({"type": "text_delta", "content": delta})
                        session._streamed_text += delta  # type: ignore[attr-defined]
                    prev_text = text

    async def _handle_part_delta(self, websocket, event, current_tool_name, session):
        """Handle streaming delta events."""
        from pydantic_ai.messages import TextPartDelta, ThinkingPartDelta, ToolCallPartDelta

        if isinstance(event.delta, TextPartDelta):
            await websocket.send_json({"type": "text_delta", "content": event.delta.content_delta})
            session._streamed_text += event.delta.content_delta  # type: ignore[attr-defined]
        elif isinstance(event.delta, ThinkingPartDelta):
            await websocket.send_json({"type": "thinking_delta", "content": event.delta.content_delta})
        elif isinstance(event.delta, ToolCallPartDelta):
            await websocket.send_json({
                "type": "tool_args_delta",
                "tool_name": current_tool_name,
                "args_delta": event.delta.args_delta,
            })

    async def _stream_tool_calls(self, websocket, node, run, session):
        """Stream tool call events from a CallToolsNode."""
        import json as json_mod
        import re

        tool_names_by_id: dict[str, str] = {}
        tool_args_by_id: dict[str, Any] = {}

        async with node.stream(run.ctx) as handle_stream:
            async for event in handle_stream:
                if hasattr(event, 'part') and hasattr(event.part, 'tool_name'):
                    # FunctionToolCallEvent
                    tool_name = event.part.tool_name
                    tool_args = event.part.args
                    tool_call_id = event.part.tool_call_id

                    if tool_call_id:
                        tool_names_by_id[tool_call_id] = tool_name
                        tool_args_by_id[tool_call_id] = tool_args

                    await websocket.send_json({
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "args": tool_args if isinstance(tool_args, dict) else str(tool_args),
                    })

                    # Subagent task status
                    if tool_name == "task":
                        try:
                            args_dict = tool_args if isinstance(tool_args, dict) else json_mod.loads(tool_args)
                            sa_type = args_dict.get("subagent_type", "general-purpose")
                            await websocket.send_json({"type": "status", "content": f"Running {sa_type} subagent..."})
                        except Exception:
                            pass

                    # Live TODO updates
                    if tool_name == "write_todos":
                        try:
                            args_dict = tool_args if isinstance(tool_args, dict) else json_mod.loads(tool_args)
                            todos_data = args_dict.get("todos", [])
                            session.latest_todos = todos_data
                            await self._emit_todos_update(websocket, session)
                        except Exception:
                            pass

                elif hasattr(event, 'tool_call_id'):
                    # FunctionToolResultEvent
                    tool_call_id = event.tool_call_id
                    tool_name = tool_names_by_id.get(tool_call_id, "unknown")
                    result_content = event.result.content

                    await websocket.send_json({
                        "type": "tool_output",
                        "tool_name": tool_name,
                        "output": str(result_content),
                    })

                    # Live audit stats
                    stats = self._audit_cap.get_stats()
                    await websocket.send_json({
                        "type": "middleware_event",
                        "event": "tool_audit",
                        "tool_name": tool_name,
                        "total_calls": stats.call_count,
                        "tools_breakdown": dict(stats.tools_used),
                    })

                    # Report file detection
                    if tool_name == "write_file":
                        try:
                            call_args = tool_args_by_id.get(tool_call_id, {})
                            if isinstance(call_args, str):
                                call_args = json_mod.loads(call_args)
                            written_path = call_args.get("path", "")
                            if "report" in written_path.lower():
                                await websocket.send_json({"type": "report_updated", "path": written_path})
                        except Exception:
                            pass

                    # Live TODO updates
                    result_str = str(result_content)
                    if tool_name == "update_todo_status" and "not found" not in result_str:
                        try:
                            call_args = tool_args_by_id.get(tool_call_id, {})
                            if isinstance(call_args, str):
                                call_args = json_mod.loads(call_args)
                            tid = call_args.get("todo_id", "")
                            new_status = call_args.get("status", "")
                            for todo in session.latest_todos:
                                if todo.get("id") == tid:
                                    todo["status"] = new_status
                                    break
                            await self._emit_todos_update(websocket, session)
                        except Exception:
                            pass
                    elif tool_name == "add_todo":
                        try:
                            id_match = re.search(r"with ID:\s*(\w+)", result_str)
                            if id_match:
                                call_args = tool_args_by_id.get(tool_call_id, {})
                                if isinstance(call_args, str):
                                    call_args = json_mod.loads(call_args)
                                session.latest_todos.append({
                                    "id": id_match.group(1),
                                    "content": call_args.get("content", ""),
                                    "active_form": call_args.get("active_form", ""),
                                    "status": "pending",
                                })
                                await self._emit_todos_update(websocket, session)
                        except Exception:
                            pass
                    elif tool_name == "remove_todo" and "not found" not in result_str:
                        try:
                            call_args = tool_args_by_id.get(tool_call_id, {})
                            if isinstance(call_args, str):
                                call_args = json_mod.loads(call_args)
                            tid = call_args.get("todo_id", "")
                            session.latest_todos = [t for t in session.latest_todos if t.get("id") != tid]
                            await self._emit_todos_update(websocket, session)
                        except Exception:
                            pass

    async def _emit_todos_update(self, websocket, session):
        """Emit todos_update WS event and persist to session meta."""
        todos_data = session.latest_todos
        await websocket.send_json({"type": "todos_update", "todos": todos_data})
        self._save_meta(session, todos=todos_data)

    # ── Background Task Monitoring ──────────────────────────────────────

    async def monitor_background_tasks(self, websocket, session: UserSession):
        """Poll TaskManager for completed/failed tasks and push notifications."""
        from subagents_pydantic_ai import TaskStatus

        task_manager = self._get_task_manager()
        if task_manager is None:
            return

        try:
            while True:
                await asyncio.sleep(1)
                for task_id, handle in list(task_manager.handles.items()):
                    if task_id in session._notified_tasks:
                        continue
                    if handle.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        session._notified_tasks.add(task_id)
                        duration = None
                        if handle.started_at and handle.completed_at:
                            duration = (handle.completed_at - handle.started_at).total_seconds()
                        result_preview = None
                        if handle.result:
                            result_preview = handle.result[:2000]
                        try:
                            await websocket.send_json({
                                "type": "background_task_completed",
                                "task_id": task_id,
                                "subagent_name": handle.subagent_name,
                                "status": handle.status.value,
                                "description": handle.description,
                                "result_preview": result_preview,
                                "error": handle.error,
                                "duration_seconds": duration,
                            })
                        except Exception:
                            return
        except asyncio.CancelledError:
            return

    def _get_task_manager(self):
        """Find the TaskManager from the agent's subagent toolset."""
        if self._agent is None:
            return None
        for ts in self._agent.toolsets:
            tm = getattr(ts, "task_manager", None)
            if tm is not None:
                return tm
        return None

    def _collect_completed_task_results(self, session: UserSession) -> str | None:
        """Collect results from completed background tasks."""
        from subagents_pydantic_ai import TaskStatus

        task_manager = self._get_task_manager()
        if task_manager is None:
            return None

        parts: list[str] = []
        for task_id, handle in list(task_manager.handles.items()):
            if task_id in session._injected_tasks:
                continue
            if handle.status == TaskStatus.COMPLETED and handle.result:
                session._injected_tasks.add(task_id)
                duration = ""
                if handle.started_at and handle.completed_at:
                    secs = (handle.completed_at - handle.started_at).total_seconds()
                    duration = f" ({secs:.1f}s)"
                parts.append(
                    f"- **{handle.subagent_name}**{duration}: {handle.description}\n"
                    f"  Result: {handle.result[:1000]}"
                )
            elif handle.status == TaskStatus.FAILED and handle.error:
                session._injected_tasks.add(task_id)
                parts.append(
                    f"- **{handle.subagent_name}** (FAILED): {handle.description}\n"
                    f"  Error: {handle.error[:500]}"
                )

        if not parts:
            return None

        return (
            "**Note**: The following background tasks have completed since your last message:\n\n"
            + "\n".join(parts)
        )

    # ── Callbacks ───────────────────────────────────────────────────────

    def create_ask_user_callback(self, websocket, session: UserSession):
        """Create an ask_user callback that sends questions via WebSocket."""

        async def callback(question: str, options: list[dict[str, str]]) -> str:
            question_id = str(uuid.uuid4())
            future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
            session.pending_questions[question_id] = future

            await websocket.send_json({
                "type": "ask_user_question",
                "question_id": question_id,
                "question": question,
                "options": options,
            })

            answer = await future
            return answer

        return callback

    # ── Persistence Helpers ─────────────────────────────────────────────

    def _save_meta(self, session: UserSession, title: str | None = None, todos: list | None = None):
        """Write session metadata to meta.json."""
        meta_dir = self._workspaces_dir / session.session_id
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "meta.json"
        now = datetime.now(timezone.utc).isoformat()

        if meta_file.exists():
            try:
                existing = json.loads(meta_file.read_text())
            except Exception:
                existing = {}
            existing["updated_at"] = now
            existing["message_count"] = len(session.message_history)
            if title:
                existing["title"] = title
            if todos is not None:
                existing["todos"] = todos
            meta_file.write_text(json.dumps(existing))
        else:
            meta = {
                "session_id": session.session_id,
                "created_at": now,
                "updated_at": now,
                "title": title or "New Session",
                "message_count": len(session.message_history),
            }
            if todos is not None:
                meta["todos"] = todos
            meta_file.write_text(json.dumps(meta))

    def _load_meta(self, session_id: str) -> dict[str, Any]:
        """Load session metadata from disk."""
        meta_file = self._workspaces_dir / session_id / "meta.json"
        if meta_file.exists():
            try:
                return json.loads(meta_file.read_text())
            except Exception:
                pass
        return {}

    def _persist_history(self, session: UserSession):
        """Serialize message_history to disk."""
        from pydantic import TypeAdapter

        history_dir = self._workspaces_dir / session.session_id
        history_dir.mkdir(parents=True, exist_ok=True)
        history_file = history_dir / "history.json"
        try:
            ta = TypeAdapter(list[ModelMessage])
            history_file.write_bytes(ta.dump_json(session.message_history))
        except Exception as e:
            logger.warning(f"Failed to persist history: {e}")

    def _restore_history(self, session_id: str) -> list[ModelMessage] | None:
        """Restore message_history from disk."""
        from pydantic import TypeAdapter

        history_file = self._workspaces_dir / session_id / "history.json"
        if not history_file.exists():
            return None
        try:
            ta = TypeAdapter(list[ModelMessage])
            return ta.validate_json(history_file.read_bytes())
        except Exception as e:
            logger.warning(f"Failed to restore history for {session_id}: {e}")
            return None

    def _save_partial_history(self, session: UserSession):
        """Save partial history on cancel."""
        user_msg = getattr(session, "_current_user_message", None)
        streamed = getattr(session, "_streamed_text", "")
        if not user_msg:
            return
        session.message_history.append(ModelRequest(parts=[UserPromptPart(content=user_msg)]))
        if streamed:
            session.message_history.append(
                ModelResponse(parts=[TextPart(content=streamed + "\n\n[Response interrupted]")])
            )
        session._streamed_text = ""  # type: ignore[attr-defined]
        session._current_user_message = None  # type: ignore[attr-defined]

    def extract_title(self, user_prompt: str | list) -> str:
        """Extract a session title from the first user message."""
        if isinstance(user_prompt, str):
            text = user_prompt
        elif isinstance(user_prompt, list):
            text = next((p for p in user_prompt if isinstance(p, str)), "")
        else:
            text = str(user_prompt)
        text = text.strip().split("\n")[0]
        return text[:60] if text else "New Session"

    # ── Excalidraw Canvas Management ────────────────────────────────────

    async def save_canvas(self, session_id: str, canvas_url: str) -> None:
        """Save canvas elements to disk for session."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{canvas_url}/api/elements")
                if resp.status_code == 200:
                    data = resp.json()
                    elements = data.get("elements", [])
                    canvas_file = self._workspaces_dir / session_id / "canvas.json"
                    canvas_file.parent.mkdir(parents=True, exist_ok=True)
                    canvas_file.write_text(json.dumps(elements))
        except Exception as e:
            logger.warning(f"Canvas save error for {session_id}: {e}")

    async def load_canvas(self, session_id: str, canvas_url: str) -> None:
        """Load saved canvas elements for session."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                await client.delete(f"{canvas_url}/api/elements/clear")
                canvas_file = self._workspaces_dir / session_id / "canvas.json"
                if canvas_file.exists():
                    elements = json.loads(canvas_file.read_text())
                    if elements:
                        await client.post(
                            f"{canvas_url}/api/elements",
                            json={"elements": elements},
                        )
        except Exception as e:
            logger.warning(f"Canvas load error for {session_id}: {e}")


# ── Module-level singleton ─────────────────────────────────────────────

_service: ResearchSessionService | None = None


def get_research_service() -> ResearchSessionService | None:
    """Return the global ResearchSessionService singleton."""
    return _service


def set_research_service(service: ResearchSessionService) -> None:
    """Set the global ResearchSessionService singleton."""
    global _service
    _service = service
