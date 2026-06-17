"""Research agent routes — WebSocket + REST endpoints for deep research."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

from backend.core.config import Settings
from backend.core.dependencies import get_settings
from backend.services.research_session import ResearchSessionService, get_research_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["deep-research"])


# ── WebSocket ──────────────────────────────────────────────────────────

@router.websocket("/ws")
async def research_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming deep research chat."""
    service = get_research_service()
    if service is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "content": "Research service not initialized"})
        await websocket.close()
        return

    await websocket.accept()

    session: Any = None
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    monitor_task: asyncio.Task[None] | None = None

    async def _reader() -> None:
        try:
            while True:
                data = await websocket.receive_text()
                await incoming.put(json.loads(data))
        except WebSocketDisconnect:
            await incoming.put({"__disconnect": True})

    reader_task = asyncio.create_task(_reader())

    try:
        while True:
            message_data = await incoming.get()

            if message_data.get("__disconnect"):
                break

            session_id = message_data.get("session_id")

            # First message — create session
            if session is None:
                if not session_id:
                    session_id = str(uuid.uuid4())
                    await websocket.send_json({"type": "session_created", "session_id": session_id})

                session = await service.get_or_create_session(session_id)

                # Set up ask_user callback for planner subagent
                session.deps.ask_user = service.create_ask_user_callback(websocket, session)

                # Start background task monitor
                monitor_task = asyncio.create_task(
                    service.monitor_background_tasks(websocket, session)
                )

                logger.info(f"WebSocket connected for research session: {session_id}")

            # Handle question answers (from planner ask_user)
            question_answer = message_data.get("question_answer")
            if question_answer and session:
                qid = question_answer.get("question_id", "")
                answer = question_answer.get("answer", "")
                if qid in session.pending_questions:
                    session.pending_questions[qid].set_result(answer)
                    del session.pending_questions[qid]
                continue

            user_message = message_data.get("message", "")
            approval_response = message_data.get("approval")
            cancel_request = message_data.get("cancel")
            attachments = message_data.get("attachments", [])

            # Handle cancel
            if cancel_request:
                if session.running_task and not session.running_task.done():
                    logger.info(f"Cancelling research run for session {session.session_id}")
                    session.cancel_event.set()
                    for _qid, fut in list(session.pending_questions.items()):
                        if not fut.done():
                            fut.cancel()
                    session.pending_questions.clear()
                    session.running_task.cancel()
                    with contextlib_suppress(asyncio.CancelledError, Exception):
                        await session.running_task
                    session.running_task = None
                    await websocket.send_json({"type": "cancelled"})
                    await websocket.send_json({"type": "done"})
                continue

            # Handle approval
            if approval_response is not None:
                await service.handle_approval(websocket, session, approval_response)
                continue

            if not user_message and not attachments:
                continue

            # Set session title from first user message
            if user_message:
                meta_dir = Path(service.workspaces_dir) / session.session_id
                meta_file = meta_dir / "meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        if meta.get("title") == "New Session":
                            service._save_meta(session, title=service.extract_title(user_message))
                    except Exception:
                        pass
                else:
                    service._save_meta(session, title=service.extract_title(user_message))

            # Build user prompt (multimodal if attachments present)
            user_prompt: str | list = user_message
            if attachments:
                prompt_parts: list = []
                file_summaries: list[str] = []

                for att in attachments:
                    name = att.get("name", "file")
                    media_type = att.get("type", "application/octet-stream")
                    import base64
                    data = base64.b64decode(att["data"])

                    # Save to container
                    upload_path = session.deps.upload_file(name, data)
                    logger.info(f"Attachment saved: {name} ({len(data)} bytes) -> {upload_path}")

                    if media_type.startswith("image/"):
                        from pydantic_ai.messages import BinaryContent
                        prompt_parts.append(BinaryContent(data=data, media_type=media_type))
                        file_summaries.append(
                            f"- **{name}** (image, {_fmt_size(len(data))})"
                            f" — path: `{upload_path}` — sent inline for visual analysis"
                        )
                    else:
                        file_summaries.append(
                            _build_file_summary(name, upload_path, data, media_type)
                        )

                files_block = "\n".join(file_summaries)
                if user_message:
                    text = (
                        f"{user_message}\n\n"
                        f"**Attached files:**\n{files_block}\n\n"
                        f"Use `read_file` to access full file contents if needed."
                    )
                else:
                    text = (
                        f"I've attached the following files:\n{files_block}\n\n"
                        f"Use `read_file` to access full contents. "
                        f"What would you like to do with them?"
                    )

                prompt_parts.insert(0, text)
                user_prompt = prompt_parts

            # Cancel any previous run
            if session.running_task and not session.running_task.done():
                session.cancel_event.set()
                session.running_task.cancel()
                with contextlib_suppress(asyncio.CancelledError, Exception):
                    await session.running_task

            session.cancel_event.clear()
            session.running_task = asyncio.create_task(
                _run_research_task(service, websocket, session, user_prompt)
            )

    finally:
        reader_task.cancel()
        if monitor_task is not None:
            monitor_task.cancel()
        if session and session.running_task and not session.running_task.done():
            session.running_task.cancel()
        if session:
            logger.info(f"WebSocket disconnected for research session: {session.session_id}")


async def _run_research_task(
    service: ResearchSessionService,
    websocket: WebSocket,
    session: Any,
    user_prompt: str | list,
) -> None:
    """Wrapper that runs the agent and sends done/error."""
    try:
        await service.run_agent_with_streaming(websocket, session, user_prompt)
    except asyncio.CancelledError:
        logger.info(f"Research run cancelled for session {session.session_id}")
        service._save_partial_history(session)
        service._persist_history(session)
        service._save_meta(session)
        raise
    except Exception as e:
        logger.exception("Error in research agent run")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
            await websocket.send_json({"type": "done"})
        except Exception:
            pass
    finally:
        session.running_task = None


# ── REST Endpoints ─────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    """List all research sessions."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    return service.list_sessions()


@router.post("/session/new")
async def create_session():
    """Create a new research session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    session_id = str(uuid.uuid4())
    await service.get_or_create_session(session_id)
    return {"session_id": session_id, "title": "New Session"}


@router.get("/history")
async def get_history(session_id: str = Query(...)):
    """Get conversation history for a session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    history = service.get_session_history(session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"history": history}


@router.get("/todos")
async def get_todos(session_id: str = Query(...)):
    """Get current TODOs for a session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"todos": session.latest_todos}


@router.get("/checkpoints")
async def list_checkpoints(session_id: str = Query(...)):
    """List all checkpoints for a session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    checkpoints = await service.list_checkpoints(session_id)
    return {"checkpoints": checkpoints}


@router.post("/checkpoints/{checkpoint_id}/rewind")
async def rewind_checkpoint(checkpoint_id: str, session_id: str = Query(...)):
    """Rewind a session to a checkpoint."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    result = await service.rewind_to_checkpoint(session_id, checkpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return result


@router.post("/checkpoints/{checkpoint_id}/fork")
async def fork_checkpoint(checkpoint_id: str, session_id: str = Query(...)):
    """Fork a new session from a checkpoint."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")
    result = await service.fork_session_from_checkpoint(session_id, checkpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return result


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Query("", description="Session ID"),
):
    """Upload a file to a session's workspace."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    if not session_id:
        session_id = str(uuid.uuid4())

    session = await service.get_or_create_session(session_id)
    content = await file.read()

    # Save file in workspace
    upload_dir = Path(service.workspaces_dir) / session_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    file_path.write_bytes(content)

    return {
        "filename": file.filename,
        "size": len(content),
        "path": str(file_path),
        "session_id": session_id,
    }


@router.get("/files")
async def list_files(session_id: str = Query(...)):
    """List files in a session's sandbox."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    session_dir = Path(service.workspaces_dir) / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    files_list = []
    for path in session_dir.rglob("*"):
        if path.is_file():
            files_list.append({
                "path": str(path.relative_to(session_dir)),
                "size": path.stat().st_size,
            })

    return {"files": files_list, "session_id": session_id}


@router.get("/files/content/{filepath:path}")
async def get_file_content(filepath: str, session_id: str = Query(...)):
    """Read a text file from a session's sandbox."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    full_path = Path(service.workspaces_dir) / session_id / filepath
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content = full_path.read_text(encoding="utf-8", errors="replace")
    return {"path": filepath, "content": content}


@router.get("/files/binary/{filepath:path}")
async def get_file_binary(filepath: str, session_id: str = Query(...)):
    """Read a binary file from a session's sandbox."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    full_path = Path(service.workspaces_dir) / session_id / filepath
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    media_type = _content_type(ext, "application/octet-stream")

    return Response(content=full_path.read_bytes(), media_type=media_type)


@router.get("/export/{fmt}")
async def export_report(
    fmt: str,
    session_id: str = Query(...),
    filepath: str = Query("/workspace/report.md"),
):
    """Export a research report in various formats."""
    from pathlib import Path

    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    # Resolve file from workspace
    full_path = Path(service.workspaces_dir) / session_id / filepath.lstrip("/")
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    content = full_path.read_text(encoding="utf-8", errors="replace")
    filename = full_path.stem

    if fmt in ("md", "markdown"):
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}.md"},
        )
    elif fmt == "html":
        import markdown as md_lib
        html_body = md_lib.markdown(content, extensions=["tables", "fenced_code"])
        html = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
        return Response(
            content=html,
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename}.html"},
        )
    elif fmt == "pdf":
        try:
            import markdown as md_lib
            from weasyprint import HTML as WeasyHTML
            html_body = md_lib.markdown(content, extensions=["tables", "fenced_code"])
            html = f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
            pdf_bytes = WeasyHTML(string=html).write_pdf()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF export requires weasyprint. Install with: uv sync --extra export",
            )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")


@router.get("/config")
async def get_config():
    """Get research agent configuration."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    agent = service.agent
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    tools_info = []
    for ts in agent.toolsets:
        name = getattr(ts, "prefix", getattr(ts, "id", str(type(ts).__name__)))
        tools_info.append({
            "name": name,
            "type": type(ts).__name__,
        })

    return {
        "toolsets": tools_info,
        "subagents": [s["name"] for s in SUBAGENT_CONFIGS_REF],
        "middleware": ["ForgiveWriteTodosCapability", "AuditCapability", "PermissionCapability"],
        "has_rag": hasattr(agent, "_tools") and len(agent._tools or []) > 0,
    }


@router.post("/reset")
async def reset_session(session_id: str = Query(...)):
    """Reset a research session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cancel running task
    if session.running_task and not session.running_task.done():
        session.running_task.cancel()
        with contextlib_suppress(asyncio.CancelledError, Exception):
            await session.running_task
        session.running_task = None

    # Clear state
    session.message_history = []
    session.latest_todos = []
    session.pending_questions.clear()
    session.pending_approval_state = {}
    session.cancel_event.clear()
    service._persist_history(session)
    service._save_meta(session)

    return {"status": "reset", "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a research session."""
    service = get_research_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Research service not initialized")

    deleted = await service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/health")
async def health():
    """Health check for research service."""
    service = get_research_service()
    if service is None:
        return {"status": "unavailable", "agent": None}
    return {
        "status": "ok",
        "agent": service.agent is not None,
        "sessions": len(service._user_sessions) if hasattr(service, "_user_sessions") else 0,
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    """Format file size in human-readable format."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if n != int(n) else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _build_file_summary(name: str, path: str, data: bytes, media_type: str) -> str:
    """Build a file summary string for multimodal attachment messages."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    size = len(data)
    summary = f"- **{name}** ({_fmt_size(size)}) — path: `{path}`"

    TEXT_EXTS = {
        "txt", "md", "csv", "tsv", "json", "jsonl", "py", "js", "ts",
        "jsx", "tsx", "html", "htm", "css", "xml", "yaml", "yml", "toml",
        "ini", "cfg", "conf", "sh", "bash", "zsh", "sql", "r", "rb",
        "go", "rs", "java", "c", "cpp", "h", "hpp", "cs", "swift", "kt",
        "lua", "log", "env", "gitignore", "dockerfile",
    }

    if ext in TEXT_EXTS or media_type.startswith("text/"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
            except Exception:
                return summary + " — binary file, use `read_file` to inspect"

        lines = text.splitlines()
        char_count = len(text)
        line_count = len(lines)
        summary += f" — {line_count} lines, {char_count} chars"

        preview_lines = lines[:15]
        preview = "\n".join(preview_lines)
        if len(preview) > 800:
            preview = preview[:800] + "..."
        truncated = line_count > 15 or len(preview) >= 800

        summary += f"\n  ```\n{preview}\n  ```"
        if truncated:
            remaining = line_count - 15
            summary += (
                f"\n  *(preview — {remaining} more lines,"
                f' use `read_file("{path}")` for full content)*'
            )
    else:
        summary += f" — binary ({media_type}), use `read_file` to inspect"

    return summary


def _content_type(ext: str, default: str = "application/octet-stream") -> str:
    """Map file extension to content type."""
    CONTENT_TYPES = {
        "html": "text/html", "htm": "text/html", "css": "text/css",
        "js": "application/javascript", "json": "application/json",
        "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
        "pdf": "application/pdf",
    }
    return CONTENT_TYPES.get(ext, default)


def contextlib_suppress(*exceptions):
    """Simple context manager to suppress exceptions (avoids import issues)."""
    import contextlib
    return contextlib.suppress(*exceptions)


# Reference for config endpoint (duplicated from agent_factory to avoid circular imports)
SUBAGENT_CONFIGS_REF = [
    {"name": "general-purpose"},
    {"name": "planner"},
    {"name": "code-reviewer"},
]
