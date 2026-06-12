import { useState, useRef, useEffect } from "react";
import {
  sendMessage,
  getHistory,
  listUsers,
  createUser,
  getUserSessions,
  type MessageData,
  type UserData,
  type UserSessionData,
} from "./api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STORAGE_SESSION_KEY = "agent_alpha_session_id";
const STORAGE_USER_KEY = "agent_alpha_user_id";

const ROLE_BADGES: Record<string, string> = {
  admin: "bg-purple-600",
  user: "bg-indigo-600",
  viewer: "bg-gray-600",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>(() => {
    return localStorage.getItem(STORAGE_SESSION_KEY) ?? "";
  });

  /* ── User state ──────────────────────────────────────────────────── */
  const [users, setUsers] = useState<UserData[]>([]);
  const [currentUser, setCurrentUser] = useState<UserData | null>(null);
  const [showUserPanel, setShowUserPanel] = useState(false);
  const [showCreateUser, setShowCreateUser] = useState(false);

  /* ── Create user form state ──────────────────────────────────────── */
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [newTeam, setNewTeam] = useState("");

  /* ── Session sidebar state ───────────────────────────────────────── */
  const [userSessions, setUserSessions] = useState<UserSessionData[]>([]);
  const [showSessions, setShowSessions] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  /* Load users on mount and restore selected user */
  useEffect(() => {
    const storedUserId = localStorage.getItem(STORAGE_USER_KEY);

    listUsers()
      .then((allUsers) => {
        setUsers(allUsers);
        if (storedUserId) {
          const found = allUsers.find((u) => u.id === storedUserId);
          if (found) setCurrentUser(found);
        }
      })
      .catch(() => {
        // Users table may not exist yet — that's OK.
      });
  }, []);

  /* Restore chat history on mount or session change */
  useEffect(() => {
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
  }, []);

  /* Auto-scroll on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ── User handlers ────────────────────────────────────────────────── */

  const handleSelectUser = (user: UserData) => {
    setCurrentUser(user);
    localStorage.setItem(STORAGE_USER_KEY, user.id);
    setShowUserPanel(false);
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newDisplayName.trim()) return;

    try {
      const user = await createUser({
        username: newUsername.trim(),
        display_name: newDisplayName.trim(),
        role: newRole,
        team: newTeam.trim() || null,
      });
      setUsers((prev) => [...prev, user]);
      setCurrentUser(user);
      localStorage.setItem(STORAGE_USER_KEY, user.id);
      setNewUsername("");
      setNewDisplayName("");
      setNewRole("user");
      setNewTeam("");
      setShowCreateUser(false);
      setShowUserPanel(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      alert(`Failed to create user: ${msg}`);
    }
  };

  const handleViewSessions = async () => {
    if (!currentUser) return;
    try {
      const sessions = await getUserSessions(currentUser.id);
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
    // Reload messages for this session.
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
      const data = await sendMessage(
        text,
        sessionId || undefined,
        currentUser?.id,
      );
      localStorage.setItem(STORAGE_SESSION_KEY, data.session_id);
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
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

  /* ── Render ──────────────────────────────────────────────────────── */

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
        <div className="relative">
          <button
            onClick={() => setShowUserPanel(!showUserPanel)}
            className="flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-sm transition hover:border-indigo-500"
          >
            {currentUser ? (
              <>
                <span
                  className={`h-2 w-2 rounded-full ${ROLE_BADGES[currentUser.role] ?? "bg-gray-500"}`}
                />
                <span className="text-gray-200">{currentUser.display_name}</span>
                <span className="text-xs text-gray-500">
                  {currentUser.team ? `${currentUser.team} · ` : ""}
                  {currentUser.role}
                </span>
              </>
            ) : (
              <span className="text-gray-400">Select user</span>
            )}
            <svg
              className={`h-4 w-4 text-gray-400 transition ${showUserPanel ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {/* User dropdown panel */}
          {showUserPanel && (
            <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-xl border border-gray-700 bg-gray-900 p-3 shadow-2xl">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Users
              </p>
              {users.length === 0 && (
                <p className="py-2 text-sm text-gray-500">
                  No users yet. Create one below.
                </p>
              )}
              <div className="mb-2 max-h-48 space-y-1 overflow-y-auto">
                {users.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => handleSelectUser(user)}
                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition hover:bg-gray-800 ${
                      currentUser?.id === user.id
                        ? "bg-gray-800 ring-1 ring-indigo-500"
                        : ""
                    }`}
                  >
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${ROLE_BADGES[user.role] ?? "bg-gray-500"}`}
                    />
                    <span className="flex-1 truncate text-gray-200">
                      {user.display_name}
                    </span>
                    <span className="text-xs text-gray-500">
                      {user.team ?? user.role}
                    </span>
                  </button>
                ))}
              </div>
              <button
                onClick={() => {
                  setShowUserPanel(false);
                  setShowCreateUser(true);
                }}
                className="w-full rounded-lg border border-dashed border-gray-600 px-3 py-2 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
              >
                + New user
              </button>
            </div>
          )}
        </div>

        {/* Sessions button */}
        {currentUser && (
          <button
            onClick={handleViewSessions}
            className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
            title="View my sessions"
          >
            Sessions
          </button>
        )}
      </header>

      {/* ---- Create User Modal ---- */}
      {showCreateUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <form
            onSubmit={handleCreateUser}
            className="w-full max-w-sm rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl"
          >
            <h2 className="mb-4 text-lg font-semibold text-gray-100">
              Create User
            </h2>

            <label className="mb-1 block text-xs font-medium text-gray-400">
              Username
            </label>
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className="mb-3 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500"
              placeholder="alice"
              required
            />

            <label className="mb-1 block text-xs font-medium text-gray-400">
              Display Name
            </label>
            <input
              type="text"
              value={newDisplayName}
              onChange={(e) => setNewDisplayName(e.target.value)}
              className="mb-3 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500"
              placeholder="Alice"
              required
            />

            <label className="mb-1 block text-xs font-medium text-gray-400">
              Team
            </label>
            <input
              type="text"
              value={newTeam}
              onChange={(e) => setNewTeam(e.target.value)}
              className="mb-3 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500"
              placeholder="Engineering (optional)"
            />

            <label className="mb-1 block text-xs font-medium text-gray-400">
              Role
            </label>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 outline-none focus:border-indigo-500"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="viewer">Viewer</option>
            </select>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setShowCreateUser(false)}
                className="flex-1 rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 transition hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ---- Sessions Sidebar ---- */}
      {showSessions && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-100">
                Sessions — {currentUser?.display_name}
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
                        {s.session_id.slice(0, 16)}…
                      </p>
                    </div>
                    <span className="text-xs text-gray-500">
                      {s.session_id.slice(0, 8)}
                    </span>
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setShowSessions(false)}
              className="mt-4 w-full rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 transition hover:bg-gray-800"
            >
              Close
            </button>
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
