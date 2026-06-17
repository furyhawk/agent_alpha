import { useState, useRef, useEffect, useCallback } from "react";
import {
  createResearchSession,
  listResearchSessions,
  deleteResearchSession,
  getResearchTodos,
  listResearchCheckpoints,
  rewindResearchCheckpoint,
  forkResearchCheckpoint,
  getResearchExportUrl,
  type ResearchSession,
  type ResearchCheckpoint,
} from "../research-api";

/* ── Types ─────────────────────────────────────────────────────── */

interface ChatMessage {
  type: "user" | "assistant" | "system" | "tool";
  content: string;
  toolName?: string;
  timestamp: number;
}

interface ToolCall {
  toolName: string;
  args: unknown;
  output?: string;
  status: "running" | "complete" | "error";
}

/* ── Constants ─────────────────────────────────────────────────── */

const WS_BASE = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;

/* ── Research Page ─────────────────────────────────────────────── */

export default function ResearchPage({ onBack }: { onBack: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const [todos, setTodos] = useState<Record<string, unknown>[]>([]);
  const [checkpoints, setCheckpoints] = useState<ResearchCheckpoint[]>([]);
  const [showCheckpoints, setShowCheckpoints] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [statusText, setStatusText] = useState("");
  const [connected, setConnected] = useState(false);
  const [streamingText, setStreamingText] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  /* ── Load sessions on mount ──────────────────────────────────── */
  useEffect(() => {
    listResearchSessions()
      .then(setSessions)
      .catch(() => {});
  }, []);

  /* ── Auto-scroll ─────────────────────────────────────────────── */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  /* ── Connect WebSocket ───────────────────────────────────────── */
  const connectWs = useCallback((sid: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`${WS_BASE}/api/research/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Send session ID to resume or create
      ws.send(JSON.stringify({ session_id: sid }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case "session_created":
            setSessionId(data.session_id);
            // Update sessions list
            listResearchSessions().then(setSessions).catch(() => {});
            break;

          case "start":
            setLoading(true);
            setStreamingText("");
            setToolCalls([]);
            break;

          case "text_delta":
            setStreamingText((prev) => prev + data.content);
            break;

          case "thinking_delta":
            // Could show thinking in a separate pane
            break;

          case "status":
            setStatusText(data.content);
            break;

          case "tool_start":
            setToolCalls((prev) => [
              ...prev,
              {
                toolName: data.tool_name,
                args: data.args,
                status: "running",
              },
            ]);
            break;

          case "tool_output":
            setToolCalls((prev) => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].toolName === data.tool_name && updated[i].status === "running") {
                  updated[i] = { ...updated[i], output: data.output, status: "complete" };
                  break;
                }
              }
              return updated;
            });
            break;

          case "tool_args_delta":
            // Append to last tool's args if same tool name
            setToolCalls((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.toolName === data.tool_name && last.status === "running") {
                updated[updated.length - 1] = {
                  ...last,
                  args: (last.args || "") + (data.args_delta || ""),
                };
              }
              return updated;
            });
            break;

          case "response":
            setMessages((prev) => [
              ...prev,
              {
                type: "assistant",
                content: streamingText || data.content,
                timestamp: Date.now(),
              },
            ]);
            setStreamingText("");
            break;

          case "done":
            setLoading(false);
            setStatusText("");
            setStreamingText("");
            // Refresh sessions list
            listResearchSessions().then(setSessions).catch(() => {});
            break;

          case "cancelled":
            setLoading(false);
            setStatusText("Cancelled");
            break;

          case "error":
            setMessages((prev) => [
              ...prev,
              { type: "system", content: `❌ Error: ${data.content}`, timestamp: Date.now() },
            ]);
            setLoading(false);
            break;

          case "todos_update":
            setTodos(data.todos || []);
            break;

          case "checkpoint_saved":
            // Refresh checkpoints
            if (sessionId) {
              listResearchCheckpoints(sessionId).then((r) => setCheckpoints(r.checkpoints)).catch(() => {});
            }
            break;

          case "checkpoint_rewind":
            setMessages([]);
            setStreamingText("");
            break;

          case "middleware_event":
            if (data.event === "tool_audit") {
              // Could show audit stats
            }
            break;

          case "approval_required":
            setStatusText("⚠️ Approval required for tool execution");
            break;

          case "ask_user_question":
            setStatusText(`❓ ${data.question}`);
            break;

          case "tool_call_start":
            // Tool call starting (from model request streaming)
            break;

          case "background_task_completed":
            setMessages((prev) => [
              ...prev,
              {
                type: "system",
                content: `✅ Subagent "${data.subagent_name}" completed (${data.duration_seconds?.toFixed(1) || "?"}s)`,
                timestamp: Date.now(),
              },
            ]);
            break;

          case "report_updated":
            setStatusText(`📄 Report updated: ${data.path}`);
            break;

          case "canvas_ready":
            setStatusText("Canvas ready");
            break;
        }
      } catch (err) {
        console.error("WS parse error:", err);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (loading) setLoading(false);
    };

    ws.onerror = () => {
      setConnected(false);
    };
  }, [loading, sessionId, streamingText]);

  /* ── Send message ────────────────────────────────────────────── */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading || !wsRef.current) return;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { type: "user", content: text, timestamp: Date.now() },
    ]);

    wsRef.current.send(JSON.stringify({
      message: text,
      session_id: sessionId || undefined,
    }));

    // If no session yet, the WS handler will create one
  };

  /* ── Create new session ──────────────────────────────────────── */
  const handleNewSession = async () => {
    try {
      const newSession = await createResearchSession();
      setSessionId(newSession.session_id);
      setMessages([]);
      setTodos([]);
      setCheckpoints([]);
      setToolCalls([]);
      setStreamingText("");
      connectWs(newSession.session_id);
      listResearchSessions().then(setSessions).catch(() => {});
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { type: "system", content: `❌ Failed to create session: ${err}`, timestamp: Date.now() },
      ]);
    }
  };

  /* ── Select existing session ─────────────────────────────────── */
  const handleSelectSession = (sid: string) => {
    setSessionId(sid);
    setMessages([]);
    setTodos([]);
    setCheckpoints([]);
    setToolCalls([]);
    setStreamingText("");
    setShowSessions(false);

    // Load checkpoints
    listResearchCheckpoints(sid).then((r) => setCheckpoints(r.checkpoints)).catch(() => {});
    getResearchTodos(sid).then((r) => setTodos(r.todos)).catch(() => {});

    // Connect WebSocket
    connectWs(sid);
  };

  /* ── Initialize WS when connecting without a session ─────────── */
  const handleStartChatting = () => {
    const sid = sessionId || "new";
    connectWs(sid);
  };

  /* ── Cancel running agent ────────────────────────────────────── */
  const handleCancel = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ cancel: true, session_id: sessionId }));
    }
  };

  /* ── Rewind to checkpoint ────────────────────────────────────── */
  const handleRewind = async (cpId: string) => {
    if (!sessionId) return;
    try {
      await rewindResearchCheckpoint(sessionId, cpId);
      setMessages([]);
      setStreamingText("");
    } catch (err) {
      console.error("Rewind failed:", err);
    }
  };

  /* ── Fork from checkpoint ────────────────────────────────────── */
  const handleFork = async (cpId: string) => {
    if (!sessionId) return;
    try {
      const result = await forkResearchCheckpoint(sessionId, cpId);
      setSessionId(result.session_id);
      setMessages([]);
      setStreamingText("");
      connectWs(result.session_id);
    } catch (err) {
      console.error("Fork failed:", err);
    }
  };

  /* ── Delete session ──────────────────────────────────────────── */
  const handleDeleteSession = async (sid: string) => {
    try {
      await deleteResearchSession(sid);
      if (sessionId === sid) {
        setSessionId("");
        setMessages([]);
        setTodos([]);
        setCheckpoints([]);
      }
      setSessions((prev) => prev.filter((s) => s.session_id !== sid));
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  /* ── Render ──────────────────────────────────────────────────── */
  return (
    <div className="mx-auto flex h-dvh max-w-6xl flex-col">
      {/* ── Header ── */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-3">
        <button
          onClick={onBack}
          className="rounded-lg border border-gray-700 px-2.5 py-1.5 text-sm text-gray-400 transition hover:border-gray-500 hover:text-gray-200"
        >
          ← Back
        </button>

        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 text-xs font-bold text-white">
          R
        </div>
        <div className="flex-1">
          <h1 className="text-base font-semibold leading-tight tracking-tight">
            Deep Research
          </h1>
          <p className="text-[10px] text-gray-500">
            {connected ? "● Connected" : "○ Disconnected"}
            {statusText && ` · ${statusText}`}
          </p>
        </div>

        <button
          onClick={handleNewSession}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-cyan-500 hover:text-cyan-400"
        >
          + New
        </button>

        <button
          onClick={() => {
            setShowSessions(!showSessions);
            if (!showSessions) listResearchSessions().then(setSessions).catch(() => {});
          }}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-cyan-500 hover:text-cyan-400"
        >
          Sessions
        </button>

        {checkpoints.length > 0 && (
          <button
            onClick={() => setShowCheckpoints(!showCheckpoints)}
            className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-amber-400 transition hover:border-amber-500"
          >
            ⤶ {checkpoints.length}
          </button>
        )}

        {sessionId && (
          <a
            href={getResearchExportUrl(sessionId, "md")}
            target="_blank"
            rel="noopener"
            className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-emerald-400 transition hover:border-emerald-500"
          >
            Export
          </a>
        )}
      </header>

      {/* ── Sessions Sidebar ── */}
      {showSessions && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-100">
                Research Sessions
              </h2>
              <button onClick={() => setShowSessions(false)} className="text-gray-500 hover:text-gray-300">✕</button>
            </div>
            {sessions.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">No sessions yet.</p>
            ) : (
              <div className="max-h-80 space-y-2 overflow-y-auto">
                {sessions.map((s) => (
                  <div key={s.session_id} className="flex items-center gap-2">
                    <button
                      onClick={() => handleSelectSession(s.session_id)}
                      className={`flex-1 rounded-lg px-3 py-2.5 text-left transition hover:bg-gray-800 ${
                        sessionId === s.session_id ? "bg-gray-800 ring-1 ring-cyan-500" : ""
                      }`}
                    >
                      <p className="truncate text-sm text-gray-200">
                        {s.title ?? s.session_id.slice(0, 8) + "…"}
                      </p>
                      <p className="mt-0.5 text-[11px] text-gray-500">
                        {s.message_count} messages
                      </p>
                    </button>
                    <button
                      onClick={() => handleDeleteSession(s.session_id)}
                      className="text-xs text-red-500 hover:text-red-400"
                      title="Delete session"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 flex gap-2">
              <button onClick={handleNewSession} className="flex-1 rounded-lg border border-cyan-700 px-4 py-2 text-sm text-cyan-400">
                + New Session
              </button>
              <button onClick={() => setShowSessions(false)} className="flex-1 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Checkpoints Sidebar ── */}
      {showCheckpoints && checkpoints.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-100">Checkpoints</h2>
              <button onClick={() => setShowCheckpoints(false)} className="text-gray-500 hover:text-gray-300">✕</button>
            </div>
            <div className="max-h-80 space-y-2 overflow-y-auto">
              {checkpoints.map((cp) => (
                <div key={cp.id} className="rounded-lg border border-gray-700 p-3">
                  <p className="text-sm text-gray-200">{cp.label || `Checkpoint ${cp.turn}`}</p>
                  <p className="text-xs text-gray-500">{cp.message_count} messages · Turn {cp.turn}</p>
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={() => handleRewind(cp.id)}
                      className="rounded border border-amber-600 px-2 py-1 text-xs text-amber-400 hover:bg-amber-900/30"
                    >
                      ⤶ Rewind
                    </button>
                    <button
                      onClick={() => handleFork(cp.id)}
                      className="rounded border border-cyan-600 px-2 py-1 text-xs text-cyan-400 hover:bg-cyan-900/30"
                    >
                      ↪ Fork
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Main chat area */}
        <div className="flex flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {messages.length === 0 && !sessionId && !loading && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 text-2xl font-bold text-white shadow-lg shadow-cyan-500/25">
                  R
                </div>
                <h2 className="mb-2 text-xl font-semibold text-gray-100">Deep Research</h2>
                <p className="mb-6 max-w-md text-sm text-gray-500">
                  Autonomous research agent with web search, code execution, subagents, and more.
                </p>
                <button
                  onClick={handleStartChatting}
                  className="rounded-xl bg-cyan-600 px-6 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500"
                >
                  Start Researching
                </button>
              </div>
            )}

            <div className="space-y-4">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.type === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                      msg.type === "user"
                        ? "bg-cyan-700 text-white"
                        : msg.type === "system"
                          ? "bg-gray-800/50 text-gray-400 italic"
                          : "bg-gray-800 text-gray-100"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}

              {/* Streaming text */}
              {streamingText && (
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl bg-gray-800 px-4 py-2.5 text-sm leading-relaxed text-gray-100">
                    {streamingText}
                    <span className="ml-1 inline-block h-3 w-2 animate-pulse bg-cyan-400" />
                  </div>
                </div>
              )}

              {/* Tool Calls */}
              {toolCalls.length > 0 && (
                <div className="space-y-1 rounded-lg bg-gray-900 p-3">
                  <p className="mb-1 text-xs font-medium text-gray-500">Tool Calls</p>
                  {toolCalls.map((tc, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          tc.status === "running" ? "animate-pulse bg-yellow-400" : "bg-green-400"
                        }`}
                      />
                      <span className="font-mono text-cyan-300">{tc.toolName}</span>
                      {tc.status === "running" && <span className="text-gray-500">…</span>}
                    </div>
                  ))}
                </div>
              )}

              {/* TODO list */}
              {todos.length > 0 && (
                <div className="rounded-lg border border-gray-700 bg-gray-900 p-3">
                  <p className="mb-2 text-xs font-medium text-gray-400">Progress</p>
                  {todos.map((todo: Record<string, unknown>, i: number) => (
                    <div key={i} className="flex items-center gap-2 py-0.5 text-xs">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          todo.status === "completed" ? "bg-green-400" :
                          todo.status === "in_progress" ? "animate-pulse bg-yellow-400" : "bg-gray-600"
                        }`}
                      />
                      <span className={todo.status === "completed" ? "text-gray-500 line-through" : "text-gray-300"}>
                        {String(todo.content || "")}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Loading indicator */}
              {loading && !streamingText && (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-gray-800 px-4 py-3 text-sm text-gray-400">
                    <span className="inline-flex gap-1">
                      <span className="animate-bounce">●</span>
                      <span className="animate-bounce [animation-delay:0.15s]">●</span>
                      <span className="animate-bounce [animation-delay:0.3s]">●</span>
                    </span>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </div>

          {/* ── Input ── */}
          <form onSubmit={handleSubmit} className="border-t border-gray-800 px-6 py-3">
            <div className="flex gap-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask anything…"
                disabled={loading}
                className="flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={loading || !input.trim() || !connected}
                className="rounded-xl bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Send
              </button>
              {loading && (
                <button
                  type="button"
                  onClick={handleCancel}
                  className="rounded-xl border border-red-700 px-4 py-2.5 text-sm text-red-400 transition hover:bg-red-900/30"
                >
                  Cancel
                </button>
              )}
              {!connected && sessionId && (
                <button
                  type="button"
                  onClick={() => connectWs(sessionId)}
                  className="rounded-xl border border-yellow-700 px-4 py-2.5 text-sm text-yellow-400"
                >
                  Reconnect
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
