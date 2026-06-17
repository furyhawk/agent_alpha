
const API_BASE = "/api";

/* ── Deep Research API ──────────────────────────────────────────────── */

export interface ResearchSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ResearchCheckpoint {
  id: string;
  label: string;
  turn: number;
  message_count: number;
  metadata?: Record<string, unknown>;
}

export async function createResearchSession(): Promise<{ session_id: string; title: string }> {
  const res = await fetch(`${API_BASE}/research/session/new`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listResearchSessions(): Promise<ResearchSession[]> {
  const res = await fetch(`${API_BASE}/research/sessions`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteResearchSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/research/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function getResearchHistory(sessionId: string): Promise<{ history: unknown[] }> {
  const res = await fetch(`${API_BASE}/research/history?session_id=${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getResearchTodos(sessionId: string): Promise<{ todos: Record<string, unknown>[] }> {
  const res = await fetch(`${API_BASE}/research/todos?session_id=${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listResearchCheckpoints(sessionId: string): Promise<{ checkpoints: ResearchCheckpoint[] }> {
  const res = await fetch(`${API_BASE}/research/checkpoints?session_id=${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function rewindResearchCheckpoint(sessionId: string, checkpointId: string): Promise<{ checkpoint_id: string; message_count: number }> {
  const res = await fetch(
    `${API_BASE}/research/checkpoints/${encodeURIComponent(checkpointId)}/rewind?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function forkResearchCheckpoint(sessionId: string, checkpointId: string): Promise<{ session_id: string; message_count: number }> {
  const res = await fetch(
    `${API_BASE}/research/checkpoints/${encodeURIComponent(checkpointId)}/fork?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getResearchConfig(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/research/config`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function resetResearchSession(sessionId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/research/reset?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function uploadResearchFile(sessionId: string, file: File): Promise<{ filename: string; size: number; path: string; session_id: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/research/upload?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listResearchFiles(sessionId: string): Promise<{ files: { path: string; size: number }[] }> {
  const res = await fetch(`${API_BASE}/research/files?session_id=${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getResearchFileContent(sessionId: string, filepath: string): Promise<{ path: string; content: string }> {
  const res = await fetch(
    `${API_BASE}/research/files/content/${encodeURIComponent(filepath)}?session_id=${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function getResearchExportUrl(sessionId: string, fmt: string, filepath?: string): string {
  let url = `${API_BASE}/research/export/${fmt}?session_id=${encodeURIComponent(sessionId)}`;
  if (filepath) url += `&filepath=${encodeURIComponent(filepath)}`;
  return url;
}
