import { useState, useRef, useEffect } from "react";
import {
  sendMessage,
  getHistory,
  getUserSessions,
  login,
  register,
  logout,
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  type MessageData,
  type AuthResponse,
  type UserSessionData,
} from "./api";
import AdminDashboard from "./Admin";
import RagDashboard from "./RagDashboard";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Message {
  role: "user" | "assistant";
  content: string;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  elapsedSeconds?: number;
}

const STORAGE_SESSION_KEY = "agent_alpha_session_id";

const ROLE_BADGES: Record<string, string> = {
  admin: "bg-purple-600",
  user: "bg-indigo-600",
  viewer: "bg-gray-600",
};

/* ------------------------------------------------------------------ */
/*  Auth Page                                                          */
/* ------------------------------------------------------------------ */

function AuthPage({ onAuth }: { onAuth: (user: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [team, setTeam] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);

    try {
      let result: AuthResponse;
      if (mode === "login") {
        result = await login(username, password);
      } else {
        result = await register(
          username,
          displayName || username,
          password,
          "user",
          team || undefined,
        );
      }
      setAuthToken(result.token);
      onAuth(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex h-dvh max-w-md flex-col items-center justify-center px-6">
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-lg font-bold text-white shadow-lg shadow-indigo-500/25">
          α
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agent Alpha</h1>
          <p className="text-xs text-gray-500">powered by pydantic-ai</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="w-full space-y-4">
        <p className="text-center text-sm text-gray-400">
          {mode === "login" ? "Sign in to your account" : "Create a new account"}
        </p>

        {error && (
          <p className="rounded-lg bg-red-900/40 px-4 py-2 text-center text-sm text-red-400">
            {error}
          </p>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">
            Username
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            placeholder="alice"
            required
            autoFocus
          />
        </div>

        {mode === "register" && (
          <>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">
                Display Name
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Alice"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">
                Team (optional)
              </label>
              <input
                type="text"
                value={team}
                onChange={(e) => setTeam(e.target.value)}
                className="w-full rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Engineering"
              />
            </div>
          </>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            placeholder="••••••••"
            required
            minLength={4}
          />
        </div>

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy
            ? "Please wait…"
            : mode === "login"
              ? "Sign In"
              : "Create Account"}
        </button>

        <p className="text-center text-xs text-gray-500">
          {mode === "login" ? (
            <>
              Don't have an account?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("register");
                  setError("");
                }}
                className="text-indigo-400 hover:underline"
              >
                Register
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
                className="text-indigo-400 hover:underline"
              >
                Sign In
              </button>
            </>
          )}
        </p>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main App                                                           */
/* ------------------------------------------------------------------ */

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => {
    return localStorage.getItem(STORAGE_SESSION_KEY) ?? "";
  });

  /* ── Auth state ──────────────────────────────────────────────────── */
  const [authenticated, setAuthenticated] = useState<AuthResponse | null>(
    null,
  );
  const [authReady, setAuthReady] = useState(false);

  /* ── Admin state ──────────────────────────────────────────────────── */
  const [showAdmin, setShowAdmin] = useState(false);
  const [showRag, setShowRag] = useState(false);

  /* ── Session sidebar state ───────────────────────────────────────── */
  const [userSessions, setUserSessions] = useState<UserSessionData[]>([]);
  const [showSessions, setShowSessions] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  /* Restore auth session from stored token */
  useEffect(() => {
    (async () => {
      const token = getAuthToken();
      if (!token) {
        setAuthReady(true);
        return;
      }
      try {
        const { getMe } = await import("./api");
        const user = await getMe();
        setAuthenticated(user);
      } catch {
        clearAuthToken();
      } finally {
        setAuthReady(true);
      }
    })();
  }, []);

  /* Restore chat history on mount or session change */
  useEffect(() => {
    if (!authenticated) return;
    const sid = localStorage.getItem(STORAGE_SESSION_KEY);
    if (sid) {
      getHistory(sid)
        .then((history: MessageData[]) => {
          if (history.length > 0) {
            setMessages(
              history.map((m) => ({ role: m.role, content: m.content })),
            );
          } else {
            setMessages([
              {
                role: "assistant",
                content:
                  "Hello! I'm **Agent Alpha**. How can I help you today?",
              },
            ]);
          }
        })
        .catch(() => {
          setMessages([
            {
              role: "assistant",
              content:
                "Hello! I'm **Agent Alpha**. How can I help you today?",
            },
          ]);
        });
    } else {
      setMessages([
        {
          role: "assistant",
          content: "Hello! I'm **Agent Alpha**. How can I help you today?",
        },
      ]);
    }
  }, [authenticated]);

  /* Auto-scroll on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ── Auth handlers ────────────────────────────────────────────────── */

  const handleAuth = (user: AuthResponse) => {
    setAuthenticated(user);
  };

  const handleLogout = async () => {
    await logout();
    setAuthenticated(null);
    setMessages([]);
    setSessionId("");
    localStorage.removeItem(STORAGE_SESSION_KEY);
  };

  /* ── Session handlers ────────────────────────────────────────────── */

  const handleNewSession = () => {
    localStorage.removeItem(STORAGE_SESSION_KEY);
    setSessionId("");
    setMessages([
      {
        role: "assistant",
        content: "Hello! I'm **Agent Alpha**. How can I help you today?",
      },
    ]);
  };

  const handleViewSessions = async () => {
    if (!authenticated) return;
    try {
      const sessions = await getUserSessions(authenticated.user_id);
      setUserSessions(sessions);
      setShowSessions(true);
    } catch {
      setUserSessions([]);
      setShowSessions(true);
    }
  };

  const handleSelectSession = (sid: string) => {
    localStorage.setItem(STORAGE_SESSION_KEY, sid);
    setSessionId(sid);
    setShowSessions(false);
    getHistory(sid)
      .then((history: MessageData[]) => {
        if (history.length > 0) {
          setMessages(
            history.map((m) => ({ role: m.role, content: m.content })),
          );
        } else {
          setMessages([
            {
              role: "assistant",
              content:
                "Hello! I'm **Agent Alpha**. How can I help you today?",
            },
          ]);
        }
      })
      .catch(() => {
        setMessages([]);
      });
  };

  /* ── Chat handler ────────────────────────────────────────────────── */

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      // Auth token is sent automatically via api.ts authHeaders()
      const data = await sendMessage(text, sessionId || undefined);
      localStorage.setItem(STORAGE_SESSION_KEY, data.session_id);
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          inputTokens: data.input_tokens,
          outputTokens: data.output_tokens,
          totalTokens: data.total_tokens,
          elapsedSeconds: data.elapsed_seconds,
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ **Error:** ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  /* ── Loading splash ──────────────────────────────────────────────── */

  if (!authReady) {
    return (
      <div className="mx-auto flex h-dvh max-w-4xl items-center justify-center">
        <p className="text-sm text-gray-500">Loading…</p>
      </div>
    );
  }

  /* ── Auth gate ──────────────────────────────────────────────────── */

  if (!authenticated) {
    return <AuthPage onAuth={handleAuth} />;
  }

  /* ── Admin UI ────────────────────────────────────────────────────── */

  if (showAdmin && authenticated.role === "admin") {
    return <AdminDashboard onBack={() => { setShowAdmin(false); setShowRag(false); }} />;
  }

  if (showRag && authenticated.role === "admin") {
    return <RagDashboard onBack={() => { setShowRag(false); setShowAdmin(false); }} />;
  }

  /* ── Chat UI ─────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto flex h-dvh max-w-4xl flex-col">
      {/* ---- Header ---- */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-sm font-bold text-white shadow-lg shadow-indigo-500/25">
          α
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold leading-tight tracking-tight">
            Agent Alpha
          </h1>
          <p className="text-xs text-gray-500">powered by pydantic-ai</p>
        </div>

        {/* User badge */}
        <div className="flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5">
          <span
            className={`h-2 w-2 rounded-full ${ROLE_BADGES[authenticated.role] ?? "bg-gray-500"}`}
          />
          <span className="text-sm text-gray-200">
            {authenticated.display_name}
          </span>
          <span className="text-xs text-gray-500">
            {authenticated.team ? `${authenticated.team} · ` : ""}
            {authenticated.role}
          </span>
        </div>

        {/* New Chat button */}
        <button
          onClick={handleNewSession}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
          title="Start a new chat"
        >
          + New Chat
        </button>

        {/* Sessions button */}
        <button
          onClick={handleViewSessions}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
          title="View my sessions"
        >
          Sessions
        </button>

        {/* Admin button — only for admin role */}
        {authenticated.role === "admin" && (
          <>
            <button
              onClick={() => setShowAdmin(true)}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-purple-400 transition hover:border-purple-500 hover:text-purple-300"
              title="Admin dashboard"
            >
              <svg className="mr-1 inline-block h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Admin
            </button>
            <button
              onClick={() => setShowRag(true)}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-emerald-400 transition hover:border-emerald-500 hover:text-emerald-300"
              title="RAG Dashboard"
            >
              <svg className="mr-1 inline-block h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9a2 2 0 00-1-1.73l-5-3a2 2 0 00-2 0l-5 3A2 2 0 005 9v10a2 2 0 002 2z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 17v-5m0 0l-2-2m2 2l2-2" />
              </svg>
              RAG
            </button>
          </>
        )}

        {/* Logout button */}
        <button
          onClick={handleLogout}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-500 transition hover:border-red-500 hover:text-red-400"
          title="Sign out"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </header>

      {/* ---- Sessions Sidebar ---- */}
      {showSessions && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-100">
                Sessions — {authenticated.display_name}
              </h2>
              <button
                onClick={() => setShowSessions(false)}
                className="text-gray-500 hover:text-gray-300"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            {userSessions.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">
                No sessions yet. Start a chat to create one.
              </p>
            ) : (
              <div className="max-h-64 space-y-2 overflow-y-auto">
                {userSessions.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => handleSelectSession(s.session_id)}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-gray-800 ${
                      sessionId === s.session_id
                        ? "bg-gray-800 ring-1 ring-indigo-500"
                        : ""
                    }`}
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-800 text-xs text-gray-400">
                      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                    </div>
                    <div className="flex-1 truncate">
                      <p className="text-sm text-gray-200">
                        {s.title ?? s.session_id.slice(0, 16) + "…"}
                      </p>
                    </div>
                    <span className="text-xs text-gray-500">
                      {s.session_id.slice(0, 8)}
                    </span>
                  </button>
                ))}
              </div>
            )}
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => {
                  setShowSessions(false);
                  handleNewSession();
                }}
                className="flex-1 rounded-lg border border-indigo-700 px-4 py-2 text-sm text-indigo-400 transition hover:bg-indigo-900/30"
              >
                + New Chat
              </button>
              <button
                onClick={() => setShowSessions(false)}
                className="flex-1 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 transition hover:bg-gray-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---- Messages ---- */}
      <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-thin">
        <div className="space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-800 text-gray-100"
                }`}
              >
                <Markdown content={msg.content} />
                {msg.role === "assistant" && msg.totalTokens !== undefined && (
                  <div className="mt-1.5 flex flex-wrap gap-3 text-[10px] text-gray-500">
                    <span title="Input tokens sent to the model">
                      ↓ {msg.inputTokens} in
                    </span>
                    <span title="Output tokens generated by the model">
                      ↑ {msg.outputTokens} out
                    </span>
                    <span title="Total tokens used">
                      ∑ {msg.totalTokens} total
                    </span>
                    {msg.elapsedSeconds !== undefined && msg.elapsedSeconds > 0 && (
                      <span title="Tokens per second">
                        ⚡ {Math.round(msg.totalTokens / msg.elapsedSeconds).toLocaleString()} tok/s
                      </span>
                    )}
                    {msg.elapsedSeconds !== undefined && (
                      <span title="Elapsed time">
                        ⏱ {msg.elapsedSeconds.toFixed(1)}s
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl bg-gray-800 px-4 py-3 text-sm text-gray-400">
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

      {/* ---- Input ---- */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-gray-800 px-6 py-4"
      >
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Agent Alpha anything…"
            disabled={loading}
            className="flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Minimal Markdown renderer (inline only — no deps needed)          */
/* ------------------------------------------------------------------ */

function Markdown({ content }: { content: string }) {
  const rendered = content
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)__(.+?)__(?!\*)/g, "<strong>$1</strong>")
    .replace(
      /```(\w*)\n([\s\S]*?)```/g,
      "<pre class='my-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs'><code>$2</code></pre>",
    )
    .replace(
      /`([^`]+)`/g,
      "<code class='rounded bg-gray-900 px-1 py-0.5 text-xs text-indigo-300'>$1</code>",
    )
    .replace(/\n/g, "<br />");

  return <span dangerouslySetInnerHTML={{ __html: rendered }} />;
}
