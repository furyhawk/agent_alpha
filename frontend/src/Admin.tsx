import { useState, useEffect } from "react";
import {
  getAdminStats,
  adminListUsers,
  adminUpdateUser,
  adminListSessions,
  adminDeleteSession,
  adminDeleteUser,
  type AdminStats,
  type AdminUserData,
  type AdminSessionData,
} from "./api";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface AdminProps {
  onBack: () => void;
}

const ROLE_COLORS: Record<string, string> = {
  admin: "text-purple-400",
  user: "text-indigo-400",
  viewer: "text-gray-400",
};

/* ------------------------------------------------------------------ */
/*  Admin Dashboard                                                    */
/* ------------------------------------------------------------------ */

export default function AdminDashboard({ onBack }: AdminProps) {
  const [tab, setTab] = useState<"overview" | "users" | "sessions">("overview");

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUserData[]>([]);
  const [sessions, setSessions] = useState<AdminSessionData[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  /* ── Load data ────────────────────────────────────────────────────── */

  const loadAll = async () => {
    setBusy(true);
    setError("");
    try {
      const [s, u, ses] = await Promise.all([
        getAdminStats(),
        adminListUsers(),
        adminListSessions(),
      ]);
      setStats(s);
      setUsers(u);
      setSessions(ses);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  /* ── User role toggle ─────────────────────────────────────────────── */

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await adminUpdateUser(userId, { role: newRole });
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  const handleToggleActive = async (userId: string, current: boolean) => {
    try {
      await adminUpdateUser(userId, { is_active: !current });
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!confirm("Permanently delete this user and all their data?")) return;
    try {
      await adminDeleteUser(userId);
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm("Delete this session and all its messages?")) return;
    try {
      await adminDeleteSession(sessionId);
      await loadAll();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  /* ── Render ───────────────────────────────────────────────────────── */

  return (
    <div className="mx-auto flex h-dvh max-w-6xl flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-4">
        <button
          onClick={onBack}
          className="rounded-lg border border-gray-700 p-2 text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400"
          title="Back to chat"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-purple-600 to-pink-500 text-sm font-bold text-white shadow-lg shadow-purple-500/25">
          A
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-semibold leading-tight tracking-tight">
            Admin Dashboard
          </h1>
          <p className="text-xs text-gray-500">System management</p>
        </div>

        <button
          onClick={loadAll}
          disabled={busy}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-400 transition hover:border-indigo-500 hover:text-indigo-400 disabled:opacity-40"
        >
          Refresh
        </button>
      </header>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800 px-6 pt-3">
        {(["overview", "users", "sessions"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium capitalize transition ${
              tab === t
                ? "border border-b-0 border-gray-700 bg-gray-900 text-gray-100"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t}
            {t === "users" && stats && (
              <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs">
                {stats.total_users}
              </span>
            )}
            {t === "sessions" && stats && (
              <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs">
                {stats.total_sessions}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {error && (
          <div className="mb-4 rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {busy && !stats ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-sm text-gray-500">Loading…</p>
          </div>
        ) : tab === "overview" ? (
          <OverviewTab stats={stats} />
        ) : tab === "users" ? (
          <UsersTab
            users={users}
            onRoleChange={handleRoleChange}
            onToggleActive={handleToggleActive}
            onDeleteUser={handleDeleteUser}
          />
        ) : (
          <SessionsTab sessions={sessions} onDelete={handleDeleteSession} />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Overview Tab                                                       */
/* ------------------------------------------------------------------ */

function OverviewTab({ stats }: { stats: AdminStats | null }) {
  if (!stats) return null;

  const cards = [
    {
      label: "Total Users",
      value: stats.total_users,
      color: "from-indigo-500 to-purple-600",
    },
    {
      label: "Active Users",
      value: stats.users_by_active?.active ?? 0,
      color: "from-emerald-500 to-teal-600",
    },
    {
      label: "Chat Sessions",
      value: stats.total_sessions,
      color: "from-amber-500 to-orange-600",
    },
    {
      label: "Admins",
      value: stats.users_by_role?.admin ?? 0,
      color: "from-purple-500 to-pink-600",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-gray-800 bg-gray-900/60 p-5"
          >
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className="mt-1 text-3xl font-bold text-gray-100">
              {card.value}
            </p>
            <div
              className={`mt-3 h-1 w-full rounded-full bg-gradient-to-r ${card.color}`}
            />
          </div>
        ))}
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Users by role */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            Users by Role
          </h3>
          <div className="space-y-2">
            {Object.entries(stats.users_by_role).map(([role, count]) => (
              <div key={role} className="flex items-center gap-3">
                <span className={`w-20 text-sm capitalize ${ROLE_COLORS[role] ?? "text-gray-400"}`}>
                  {role}
                </span>
                <div className="flex-1">
                  <div className="h-2 rounded-full bg-gray-800">
                    <div
                      className="h-2 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600"
                      style={{
                        width: `${stats.total_users > 0 ? (count / stats.total_users) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-sm text-gray-400">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Active vs inactive */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            User Status
          </h3>
          <div className="space-y-2">
            {Object.entries(stats.users_by_active).map(([status, count]) => (
              <div key={status} className="flex items-center gap-3">
                <span className="w-20 text-sm capitalize text-gray-400">
                  {status}
                </span>
                <div className="flex-1">
                  <div className="h-2 rounded-full bg-gray-800">
                    <div
                      className={`h-2 rounded-full ${
                        status === "active"
                          ? "bg-gradient-to-r from-emerald-500 to-teal-500"
                          : "bg-gradient-to-r from-red-500 to-rose-500"
                      }`}
                      style={{
                        width: `${stats.total_users > 0 ? (count / stats.total_users) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="w-8 text-right text-sm text-gray-400">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Users Tab                                                          */
/* ------------------------------------------------------------------ */

function UsersTab({
  users,
  onRoleChange,
  onToggleActive,
  onDeleteUser,
}: {
  users: AdminUserData[];
  onRoleChange: (id: string, role: string) => void;
  onToggleActive: (id: string, current: boolean) => void;
  onDeleteUser: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
            <th className="pb-3 pr-4">User</th>
            <th className="pb-3 pr-4">Role</th>
            <th className="pb-3 pr-4">Team</th>
            <th className="pb-3 pr-4">Status</th>
            <th className="pb-3 pr-4">Sessions</th>
            <th className="pb-3 pr-4">Created</th>
            <th className="pb-3 pr-2" />
            <th className="pb-3" />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr
              key={u.id}
              className="border-b border-gray-800/50 transition hover:bg-gray-800/30"
            >
              <td className="py-3 pr-4">
                <div>
                  <p className="font-medium text-gray-200">{u.display_name}</p>
                  <p className="text-xs text-gray-500">@{u.username}</p>
                </div>
              </td>
              <td className="py-3 pr-4">
                <select
                  value={u.role}
                  onChange={(e) => onRoleChange(u.id, e.target.value)}
                  className="rounded-lg border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200 outline-none focus:border-indigo-500"
                >
                  <option value="admin">admin</option>
                  <option value="user">user</option>
                  <option value="viewer">viewer</option>
                </select>
              </td>
              <td className="py-3 pr-4 text-gray-400">{u.team ?? "—"}</td>
              <td className="py-3 pr-4">
                <button
                  onClick={() => onToggleActive(u.id, u.is_active)}
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    u.is_active
                      ? "bg-emerald-900/50 text-emerald-400"
                      : "bg-red-900/50 text-red-400"
                  }`}
                >
                  {u.is_active ? "Active" : "Inactive"}
                </button>
              </td>
              <td className="py-3 pr-4 text-gray-400">{u.session_count}</td>
              <td className="py-3 pr-4 text-xs text-gray-500">
                {new Date(u.created_at).toLocaleDateString()}
              </td>
              <td className="py-3 pr-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    ROLE_COLORS[u.role]?.replace("text-", "bg-") ?? "bg-gray-500"
                  }`}
                />
              </td>
              <td className="py-3">
                <button
                  onClick={() => onDeleteUser(u.id)}
                  className="rounded-lg px-2 py-1 text-xs text-red-400 transition hover:bg-red-900/30"
                  title="Delete user"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sessions Tab                                                       */
/* ------------------------------------------------------------------ */

function SessionsTab({
  sessions,
  onDelete,
}: {
  sessions: AdminSessionData[];
  onDelete: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
            <th className="pb-3 pr-4">Session ID</th>
            <th className="pb-3 pr-4">Messages</th>
            <th className="pb-3 pr-4">User ID</th>
            <th className="pb-3" />
          </tr>
        </thead>
        <tbody>
          {sessions.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-8 text-center text-gray-500">
                No sessions yet.
              </td>
            </tr>
          ) : (
            sessions.map((s) => (
              <tr
                key={s.session_id}
                className="border-b border-gray-800/50 transition hover:bg-gray-800/30"
              >
                <td className="py-3 pr-4">
                  <code className="text-xs text-gray-300">
                    {s.session_id.slice(0, 16)}…
                  </code>
                </td>
                <td className="py-3 pr-4 text-gray-400">{s.message_count}</td>
                <td className="py-3 pr-4">
                  {s.user_id ? (
                    <code className="text-xs text-gray-500">
                      {s.user_id.slice(0, 12)}…
                    </code>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="py-3">
                  <button
                    onClick={() => onDelete(s.session_id)}
                    className="rounded-lg px-2 py-1 text-xs text-red-400 transition hover:bg-red-900/30"
                    title="Delete session"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
