const API_BASE = "/api";

/* ── Types ──────────────────────────────────────────────────────── */

export interface ChatResponse {
  reply: string;
  session_id: string;
}

export interface MessageData {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

/* ── Send a message ────────────────────────────────────────────── */

export async function sendMessage(
  message: string,
  sessionId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
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
