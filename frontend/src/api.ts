const API_BASE = "/api";

/* ── Chat Types ────────────────────────────────────────────────── */

export interface ChatResponse {
  reply: string;
  session_id: string;
}

export interface MessageData {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface SessionData {
  session_id: string;
  message_count: number;
  user_id: string | null;
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
}

export interface UserSessionData {
  session_id: string;
}

/* ── Send a message ────────────────────────────────────────────── */

export async function sendMessage(
  message: string,
  sessionId?: string,
  userId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
