const API_BASE = "/api";

/* ── Token management ──────────────────────────────────────────── */

const TOKEN_KEY = "agent_alpha_auth_token";

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/* ── Chat Types ────────────────────────────────────────────────── */

export interface ChatResponse {
  reply: string;
  session_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  elapsed_seconds: number;
}

export interface MessageData {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface SessionData {
  session_id: string;
  title: string | null;
  message_count: number;
  user_id: string | null;
}

/* ── Auth Types ────────────────────────────────────────────────── */

export interface AuthResponse {
  token: string;
  user_id: string;
  username: string;
  display_name: string;
  role: string;
  team: string | null;
}

/* ── User Types ────────────────────────────────────────────────── */

export interface UserData {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "user" | "viewer";
  team: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserCreateData {
  username: string;
  display_name: string;
  role?: string;
  team?: string | null;
  password?: string;
}

export interface UserSessionData {
  session_id: string;
  title: string | null;
}

/* ── Auth API ──────────────────────────────────────────────────── */

export async function login(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function register(
  username: string,
  displayName: string,
  password: string,
  role?: string,
  team?: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      display_name: displayName,
      password,
      role: role ?? "user",
      team: team ?? null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getMe(): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function logout(): Promise<void> {
  const token = getAuthToken();
  if (!token) return;
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {
    /* ignore network errors on logout */
  });
  clearAuthToken();
}

/* ── Send a message ────────────────────────────────────────────── */

export async function sendMessage(
  message: string,
  sessionId?: string,
  userId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId ?? null,
      user_id: userId ?? null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Load session history ──────────────────────────────────────── */

export async function getHistory(sessionId: string): Promise<MessageData[]> {
  const res = await fetch(
    `${API_BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── User API ──────────────────────────────────────────────────── */

export async function createUser(
  data: UserCreateData,
): Promise<UserData> {
  const res = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listUsers(): Promise<UserData[]> {
  const res = await fetch(`${API_BASE}/users`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getUserSessions(
  userId: string,
): Promise<UserSessionData[]> {
  const res = await fetch(`${API_BASE}/users/${userId}/sessions`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Admin API ─────────────────────────────────────────────────── */

export interface AdminStats {
  total_users: number;
  users_by_role: Record<string, number>;
  users_by_active: Record<string, number>;
  total_sessions: number;
}

export interface AdminUserData {
  id: string;
  username: string;
  display_name: string;
  role: string;
  team: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  session_count: number;
}

export interface AdminSessionData {
  session_id: string;
  title: string | null;
  message_count: number;
  user_id: string | null;
}

export async function getAdminStats(): Promise<AdminStats> {
  const res = await fetch(`${API_BASE}/admin/stats`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function adminListUsers(): Promise<AdminUserData[]> {
  const res = await fetch(`${API_BASE}/admin/users`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function adminUpdateUser(
  userId: string,
  data: { role?: string; is_active?: boolean; display_name?: string; team?: string | null },
): Promise<AdminUserData> {
  const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function adminListSessions(): Promise<AdminSessionData[]> {
  const res = await fetch(`${API_BASE}/admin/sessions`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function adminDeleteUser(userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
}

export async function adminDeleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
}
