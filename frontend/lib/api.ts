import type {
  AnalyticsSummary,
  Asset,
  BizTask,
  Brand,
  BusinessProfile,
  CampaignDetail,
  CampaignItem,
  CampaignProspect,
  CampaignSummary,
  ChatMessage,
  ClientStrategy,
  Conversation,
  Health,
  KnowledgeStatus,
  Opportunity,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

/** Error that carries the HTTP status, so callers can detect 401 (expired/invalid token). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "tr_token";
const ROLE_KEY = "tr_role";
const USER_KEY = "tr_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

/** Cached role/username for an instant (flash-free) render; the server (/auth/me) is authoritative. */
export function getRole(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(ROLE_KEY) || "";
}

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(USER_KEY) || "";
}

/** Persist the full session (token + role + username) after a successful sign-in. */
export function setSession(token: string, role: string, username: string): void {
  setToken(token);
  try {
    window.localStorage.setItem(ROLE_KEY, role);
    window.localStorage.setItem(USER_KEY, username);
  } catch {
    /* ignore */
  }
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ROLE_KEY);
  window.localStorage.removeItem(USER_KEY);
}

/** The current session's identity — role is derived server-side from the token (can't be spoofed). */
export async function getMe(): Promise<{ username: string; role: string }> {
  const res = await fetchRetry(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, "Failed to load session");
  return res.json();
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Retry an idempotent GET through a transient backend blip. A deploy restarts the server for ~2-4s and
// returns 502/503/504 (or a network error) during that window. Without this, view loads (past
// generations, history, campaigns) that fired during a deploy came back EMPTY and were silently
// swallowed — looking like the data "vanished" after every deployment. Only use for GETs (never POSTs,
// which could double-submit).
async function fetchRetry(input: string, init: RequestInit = {}, tries = 4): Promise<Response> {
  const TRANSIENT = new Set([502, 503, 504]);
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(input, init);
      if (res.ok || !TRANSIENT.has(res.status) || attempt >= tries) return res;
    } catch (e) {
      if (attempt >= tries) throw e;
    }
    await new Promise((r) => setTimeout(r, Math.min(1200, 500 * (attempt + 1))));
  }
}

export async function login(
  username: string,
  password: string,
): Promise<{ token: string; username: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Invalid credentials");
  }
  return res.json();
}

export async function forgotPassword(
  email: string,
): Promise<{ message: string; dev_code: string | null }> {
  const res = await fetch(`${API_BASE}/api/auth/forgot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error("Couldn't send a reset code — please try again.");
  return res.json();
}

export async function resetPassword(
  email: string,
  code: string,
  new_password: string,
): Promise<{ token: string; username: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/auth/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Invalid or expired reset code");
  }
  return res.json();
}

export async function getHealth(): Promise<Health> {
  const res = await fetchRetry(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Backend unavailable");
  return res.json();
}

export async function getBrand(): Promise<Brand> {
  const res = await fetchRetry(`${API_BASE}/api/brand`, { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, "Failed to load brand");
  return res.json();
}

export async function getConversations(kind?: string): Promise<Conversation[]> {
  const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  const res = await fetchRetry(`${API_BASE}/api/conversations${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function deleteConversation(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Delete failed");
}

export async function getMessages(id: number): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}/messages`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json();
}

export async function renameCampaign(id: number, name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Rename failed");
}

/** Update an internal campaign's brief/description (the context that grounds all generation). */
export async function updateCampaignBrief(id: number, goal: string): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ goal }),
  });
  if (!res.ok) throw new Error("Failed to update the brief");
  return res.json();
}

export async function setCampaignSector(id: number, sector: string): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ sector }),
  });
  if (!res.ok) throw new Error("Re-target failed");
  return res.json();
}

export async function deleteCampaign(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Delete failed");
}

/** Soft archive/restore a campaign (drops from / returns to the planning rail; nothing deleted). */
export async function setCampaignStatus(id: number, status: "planning" | "archived"): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Archive failed");
  return res.json();
}

export async function updateCampaignItem(
  id: number,
  patch: { scheduled_date?: string; status?: "planned" | "generated" },
): Promise<CampaignItem> {
  const res = await fetch(`${API_BASE}/api/campaign-items/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Update failed");
  return res.json();
}

export async function exportCampaignProspects(id: number, name: string): Promise<void> {
  await downloadFile(`${API_BASE}/api/campaigns/${id}/prospects/export`, `${name || "campaign"}-clients.csv`);
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  const res = await fetch(`${API_BASE}/api/analytics/summary`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load analytics");
  return res.json();
}

export async function deleteAsset(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/assets/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Delete failed");
}

export async function exportCampaign(id: number, name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}/export`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name || "campaign"}.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Force a real download (cross-origin <a download> is ignored by browsers, so fetch->blob->save). */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objUrl);
}

export interface DeckSlide {
  slide: number;
  title: string;
  text: string;
}

export async function getDeckPreview(deckFileUrl: string): Promise<{ slide_count: number; slides: DeckSlide[] }> {
  const res = await fetch(`${API_BASE}${deckFileUrl}/preview`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Preview unavailable (${res.status})`);
  return res.json();
}

export async function planCampaign(payload: {
  name: string;
  goal: string;
  audience: string;
  sector?: string;
  channels: string[];
  timeframe: string;
  start_date?: string;
}): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Planning failed");
  return res.json();
}

export async function generateCampaignItem(itemId: number): Promise<CampaignItem> {
  const res = await fetch(`${API_BASE}/api/campaign-items/${itemId}/generate`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Generation failed");
  return res.json();
}

export async function planCampaignChat(
  messages: { role: string; content: string }[],
): Promise<{ done: boolean; reply: string; campaign?: CampaignDetail }> {
  const res = await fetch(`${API_BASE}/api/campaigns/plan-chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error("Planning failed");
  return res.json();
}

export async function getCampaigns(status?: string, type?: string): Promise<CampaignSummary[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (type) params.set("type", type);
  const q = params.toString() ? `?${params.toString()}` : "";
  const res = await fetchRetry(`${API_BASE}/api/campaigns${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load campaigns");
  return res.json();
}

export async function getCampaign(id: number): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load campaign");
  return res.json();
}

/** Create an INTERNAL campaign shell (folder + its chat thread). The description is the brief that
 * grounds everything generated in that folder. */
export async function createInternalCampaign(name: string, description: string): Promise<CampaignDetail> {
  const res = await fetch(`${API_BASE}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, description, type: "internal" }),
  });
  if (!res.ok) throw new Error("Failed to create campaign");
  return res.json();
}

/** The internal campaign's chat thread (restores the conversation when reopening the folder). */
export async function getCampaignMessages(
  id: number,
): Promise<{ conversation_id: number | null; messages: { role: string; content: string; assets: Asset[] }[] }> {
  const res = await fetch(`${API_BASE}/api/campaigns/${id}/messages`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load campaign chat");
  return res.json();
}

export async function getCampaignProspects(
  campaignId: number,
  status?: string,
): Promise<CampaignProspect[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetchRetry(`${API_BASE}/api/campaigns/${campaignId}/prospects${q}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load target clients");
  return res.json();
}

export async function getCampaignProspectStrategy(
  id: number,
): Promise<{ company: string; strategy: ClientStrategy }> {
  const res = await fetch(`${API_BASE}/api/campaign-prospects/${id}/strategy`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load strategy");
  return res.json();
}

export async function markCampaignProspectDone(
  id: number,
): Promise<{ done_id: number; replacements: CampaignProspect[] }> {
  const res = await fetch(`${API_BASE}/api/campaign-prospects/${id}/done`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Action failed");
  return res.json();
}

export async function deleteCampaignProspect(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/campaign-prospects/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Delete failed");
}

export async function revokeCampaignProspect(id: number): Promise<CampaignProspect> {
  const res = await fetch(`${API_BASE}/api/campaign-prospects/${id}/revoke`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Revoke failed");
  return res.json();
}

export async function getAssets(type?: string): Promise<Asset[]> {
  const q = type ? `?type=${encodeURIComponent(type)}` : "";
  const res = await fetchRetry(`${API_BASE}/api/assets${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load assets");
  return res.json();
}

// --- Business Dev ---------------------------------------------------------
export async function getBusinessProfiles(): Promise<BusinessProfile[]> {
  const res = await fetch(`${API_BASE}/api/business/profiles`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load profiles");
  return res.json();
}

export async function discoverProspects(
  profileKey: string | null,
  query: string,
  count = 8,
  filters?: Record<string, string>,
): Promise<{ count: number; opportunities: Opportunity[] }> {
  const res = await fetch(`${API_BASE}/api/business/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ profile_key: profileKey, query, count, filters }),
  });
  if (!res.ok) throw new Error("Discovery failed");
  return res.json();
}

export async function intakeCompany(
  company: string,
  website = "",
): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/business/intake`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ company, website }),
  });
  if (!res.ok) throw new Error("Analysis failed");
  return res.json();
}

export async function getOpportunities(status?: string): Promise<Opportunity[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetchRetry(`${API_BASE}/api/opportunities${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load opportunities");
  return res.json();
}

export async function updateOpportunity(id: number, status: string): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Update failed");
  return res.json();
}

export async function setOpportunitySaved(id: number, saved: boolean): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ saved }),
  });
  if (!res.ok) throw new Error("Save failed");
  return res.json();
}

export async function deleteOpportunity(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Delete failed");
}

export async function clearOpportunities(): Promise<number> {
  const res = await fetch(`${API_BASE}/api/opportunities`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Clear failed");
  const data = await res.json().catch(() => ({ deleted: 0 }));
  return data.deleted ?? 0;
}

export async function generateOutreach(id: number): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}/outreach`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Outreach failed");
  return res.json();
}

/** Track-only outreach activity (mark sent/replied/meeting + notes). Pass "now" to stamp current time. */
export async function trackOutreach(
  id: number,
  patch: { channel?: string; sent_at?: string; replied_at?: string; meeting_at?: string; notes?: string },
): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}/track`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Track failed");
  return res.json();
}

/** Fetch provider-verified contacts on demand (no-op server-side if enrichment is unconfigured). */
export async function enrichContacts(id: number): Promise<Opportunity> {
  const res = await fetch(`${API_BASE}/api/opportunities/${id}/enrich`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Enrich failed");
  return res.json();
}

export async function bulkOpportunities(payload: {
  ids: number[];
  action: "status" | "save" | "unsave" | "delete";
  status?: string;
}): Promise<{ updated: Opportunity[]; deleted: number[] }> {
  const res = await fetch(`${API_BASE}/api/opportunities/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Bulk action failed");
  return res.json();
}

export async function exportOpportunities(opts?: { status?: string; saved?: boolean }): Promise<void> {
  const params = new URLSearchParams();
  if (opts?.status) params.set("status", opts.status);
  if (opts?.saved) params.set("saved", "true");
  const q = params.toString() ? `?${params.toString()}` : "";
  await downloadFile(`${API_BASE}/api/opportunities/export${q}`, "prospects.csv");
}

export async function getTasks(status?: string): Promise<BizTask[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`${API_BASE}/api/tasks${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load tasks");
  return res.json();
}

export async function updateTask(
  id: number,
  patch: { status?: "pending" | "done" | "snoozed"; snooze_days?: number; due_at?: string; note?: string },
): Promise<BizTask> {
  const res = await fetch(`${API_BASE}/api/tasks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Task update failed");
  return res.json();
}

export async function deleteTask(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/tasks/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Task delete failed");
}

export async function regenerateAsset(
  id: number,
  opts?: { instruction?: string; replace?: boolean },
): Promise<Asset> {
  const res = await fetch(`${API_BASE}/api/assets/${id}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ instruction: opts?.instruction ?? "", replace: opts?.replace ?? false }),
  });
  if (!res.ok) throw new Error("Regenerate failed");
  return res.json();
}

export async function uploadBrandFile(file: File): Promise<{ filename: string; kind: string; chunks: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/knowledge/upload-brand-file`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Upload failed");
  }
  return res.json();
}

export async function getKnowledgeStatus(): Promise<KnowledgeStatus> {
  const res = await fetch(`${API_BASE}/api/knowledge/status`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load knowledge status");
  return res.json();
}

/** Resolve a relative backend file path (e.g. /api/files/...) to an absolute URL. */
export function fileUrl(path: string | null | undefined): string {
  if (!path) return "";
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

export interface AttachmentMeta {
  id: number;
  filename: string;
  kind: string;
  chars: number;
  chunks: number;
  text: string;
}

/** Upload a file as chat context. The backend extracts + embeds it and returns an excerpt. */
export async function uploadAttachment(file: File): Promise<AttachmentMeta> {
  const form = new FormData();
  form.append("file", file);
  // Note: do NOT set Content-Type — the browser sets the multipart boundary.
  const res = await fetch(`${API_BASE}/api/chat/attach`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Upload failed");
  }
  return res.json();
}

export interface ChatHandlers {
  onMeta?: (m: { conversation_id: number; title: string }) => void;
  onStatus?: (text: string) => void;
  onToken?: (text: string) => void;
  onAsset?: (asset: Asset) => void;
  onChips?: (items: string[]) => void;
  onDone?: (text: string) => void;
  onError?: (text: string) => void;
}

/**
 * POST to the SSE chat endpoint and parse the event stream incrementally.
 * Uses fetch + ReadableStream because we need POST + an auth header
 * (EventSource only supports GET without custom headers).
 */
export async function streamChat(
  message: string,
  conversationId: number | null,
  handlers: ChatHandlers,
  endpoint: string = "/api/chat/stream",
  attachments?: { name: string; text: string; id?: number; kind?: string }[],
  signal?: AbortSignal,
): Promise<void> {
  const payload = JSON.stringify({
    message,
    conversation_id: conversationId,
    attachments: attachments && attachments.length ? attachments : undefined,
  });
  // Transient gateway errors (502/503/504) and pre-response network blips happen when the backend is
  // briefly restarting (e.g. a deploy). Retry the INITIAL connection a couple times before surfacing
  // an error so a short blip doesn't dump the user to "network error". We only retry before any data
  // has streamed — never mid-stream, which would duplicate a partial reply.
  const TRANSIENT = new Set([502, 503, 504]);
  const MAX_RETRY = 4; // up to 5 attempts (~4s total) — rides through a backend restart during a deploy
  const wait = (a: number) => new Promise((r) => setTimeout(r, Math.min(1200, 600 * (a + 1))));
  let res: Response | null = null;
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: payload,
        signal,
      });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return; // superseded by a newer turn — silent
      if (attempt < MAX_RETRY) {
        await wait(attempt);
        continue; // network blip before any response — retry
      }
      handlers.onError?.("Couldn’t reach the server — please try again in a moment.");
      return;
    }
    if (res.ok || !TRANSIENT.has(res.status) || attempt >= MAX_RETRY) break;
    await wait(attempt); // backend restarting (e.g. a deploy) — retry
  }

  if (!res || !res.ok || !res.body) {
    handlers.onError?.(res ? `Request failed (${res.status})` : "Connection failed");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let event = "message";
      let dataRaw = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataRaw += line.slice(5).trim();
      }
      if (!dataRaw) continue;
      let data: {
        text?: string;
        conversation_id?: number;
        title?: string;
        [key: string]: unknown;
      };
      try {
        data = JSON.parse(dataRaw);
      } catch {
        continue;
      }
      switch (event) {
        case "meta":
          handlers.onMeta?.({
            conversation_id: data.conversation_id!,
            title: data.title!,
          });
          break;
        case "status":
          handlers.onStatus?.(data.text ?? "");
          break;
        case "token":
          handlers.onToken?.(data.text ?? "");
          break;
        case "asset":
          handlers.onAsset?.(data as unknown as Asset);
          break;
        case "chips":
          handlers.onChips?.((data as { items?: string[] }).items ?? []);
          break;
        case "done":
          handlers.onDone?.(data.text ?? "");
          break;
        case "error":
          handlers.onError?.(data.text ?? "Something went wrong");
          break;
      }
    }
  }
  } catch (e) {
    if ((e as Error)?.name === "AbortError") return; // superseded by a newer turn — silent
    // mid-stream connection drop — surface it so the UI recovers instead of hanging.
    handlers.onError?.((e as Error)?.message || "Connection lost");
  }
}
