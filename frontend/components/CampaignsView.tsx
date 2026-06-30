"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  createInternalCampaign,
  deleteCampaign,
  deleteCampaignProspect,
  exportCampaignProspects,
  deleteAsset,
  getCampaign,
  getCampaignMessages,
  getCampaignProspects,
  getCampaignProspectStrategy,
  getCampaigns,
  markCampaignProspectDone,
  planCampaign,
  planCampaignChat,
  revokeCampaignProspect,
  setCampaignSector,
  setCampaignStatus,
  streamChat,
  updateCampaignBrief,
  updateCampaignItem,
  uploadAttachment,
} from "@/lib/api";
import type {
  Asset,
  Attachment,
  CampaignDetail,
  CampaignItem,
  CampaignProspect,
  CampaignSummary,
  ChatMessage,
  ClientStrategy,
} from "@/lib/types";
import { AssetCard } from "./AssetCard";
import { Avatar } from "./Avatar";
import { EmptyState } from "./EmptyState";
import { Markdown } from "./Markdown";

type CampaignTab = "internal" | "external";

// Real-time campaign quick-starts by sector — each builds a context-grounded campaign whose
// Target clients are real companies discovered for that vertical.
// The five canonical target sectors a campaign folder can be locked to.
const SECTORS = [
  "IT & Software",
  "Healthcare",
  "Staffing & Recruiting",
  "Finance & Fintech",
  "Corporate / Non-IT",
];

const VERTICALS = [
  {
    label: "IT / Software",
    sector: "IT & Software",
    goal: "Win IT & software companies hiring engineering and product talent at volume",
    audience:
      "IT and software companies (50–5,000 employees) hiring software engineers, developers, data and product roles at volume",
  },
  {
    label: "Non-IT / Corporate",
    sector: "Corporate / Non-IT",
    goal: "Win corporate employers hiring back-office and operations talent at volume",
    audience:
      "Mid-market corporate employers hiring finance, operations, administrative, customer-success and sales roles at volume",
  },
  {
    label: "Healthcare",
    sector: "Healthcare",
    goal: "Win healthcare systems and clinical staffing firms",
    audience:
      "Healthcare systems, hospitals and clinical/healthcare staffing agencies hiring nurses, allied-health and clinical roles at volume",
  },
  {
    label: "Staffing & Recruiting",
    sector: "Staffing & Recruiting",
    goal: "Win staffing agencies overloaded with open requisitions",
    audience:
      "Staffing and recruiting agencies overloaded with requisitions that need offshore sourcing and recruiting capacity",
  },
];

export function CampaignsView() {
  const [tab, setTab] = useState<CampaignTab>("internal");
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyVertical, setBusyVertical] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const loadList = useCallback(async () => {
    // Active: Internal = promote-Talentrupt folders; External = the planned client campaigns.
    // Archived view: archived campaigns of the current type (restorable).
    const c = showArchived
      ? await getCampaigns("archived", tab)
      : tab === "internal"
        ? await getCampaigns(undefined, "internal")
        : await getCampaigns("planning", "external");
    setCampaigns(c);
    return c;
  }, [tab, showArchived]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  function switchTab(next: CampaignTab) {
    if (next === tab) return;
    setTab(next);
    setSelected(null);
    setDetail(null);
    setCreating(false);
    setShowArchived(false);
  }

  function toggleArchived() {
    setShowArchived((v) => !v);
    setSelected(null);
    setDetail(null);
    setCreating(false);
  }

  async function restore(id: number) {
    try {
      await setCampaignStatus(id, "planning");
    } catch {
      /* ignore — still refresh the list */
    }
    if (selected === id) {
      setSelected(null);
      setDetail(null);
    }
    await loadList();
  }

  async function onInternalCreated(c: CampaignDetail) {
    setCreating(false);
    await loadList();
    setSelected(c.id);
    setDetail(c);
  }

  useEffect(() => {
    if (selected == null) {
      setDetail(null);
      return;
    }
    getCampaign(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  // Deep-link from a campaign asset card ("Open campaign →" -> /campaigns?open=<id>).
  const openParam = useSearchParams().get("open");
  useEffect(() => {
    const id = Number(openParam);
    if (openParam && Number.isFinite(id) && id > 0) {
      setCreating(false);
      setSelected(id);
    }
  }, [openParam]);

  function openNew() {
    setCreating(true);
    setSelected(null);
    setDetail(null);
  }

  async function onPlanned(c: CampaignDetail) {
    setCreating(false);
    await loadList();
    setSelected(c.id);
    setDetail(c);
  }

  async function removeCampaign(id: number) {
    if (!confirm("Delete this campaign and its target clients & assets? This can't be undone.")) return;
    try {
      await deleteCampaign(id);
    } catch {
      /* ignore — still drop it from the rail */
    }
    if (selected === id) {
      setSelected(null);
      setDetail(null);
    }
    await loadList();
  }

  async function archive(id: number) {
    if (!confirm("Archive this campaign? It drops from the list but isn't deleted (recoverable).")) return;
    try {
      await setCampaignStatus(id, "archived");
    } catch {
      /* ignore — still drop it from the rail */
    }
    if (selected === id) {
      setSelected(null);
      setDetail(null);
    }
    await loadList();
  }

  async function onSectorChange(id: number, sector: string) {
    await setCampaignSector(id, sector);
    const fresh = await getCampaign(id); // updated sector + realigned audience; clients re-fill
    setDetail(fresh);
  }

  async function startVertical(v: (typeof VERTICALS)[number]) {
    const name = `${v.label} — RPO Outreach`;
    // Don't duplicate a sector: if a campaign for this sector already exists, just open it.
    // Prefer the canonical quick-start name, then any folder already targeting the same sector.
    const existing =
      campaigns.find((c) => c.name === name) ||
      campaigns.find((c) => (c.sector || "") === v.sector);
    if (existing) {
      setCreating(false);
      setSelected(existing.id);
      return;
    }
    setBusyVertical(v.label);
    try {
      const c = await planCampaign({
        name,
        goal: v.goal,
        audience: v.audience,
        sector: v.sector,
        channels: ["LinkedIn"],
        timeframe: "4 weeks",
      });
      await onPlanned(c);
    } finally {
      setBusyVertical(null);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        {/* Rail */}
        <div className="flex w-60 shrink-0 flex-col border-r border-[var(--border)]">
          <div className="space-y-3 p-3">
            {/* Internal (promote Talentrupt) vs External (client-targeting) folders */}
            <div className="flex rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium">
              {(["internal", "external"] as CampaignTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => switchTab(t)}
                  className={`flex-1 rounded-md px-2 py-1.5 capitalize transition ${
                    tab === t ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            {!showArchived && (
              <button onClick={openNew} className="btn-primary w-full">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
                New campaign
              </button>
            )}
            {!showArchived && tab === "external" && (
              <div>
                <div className="mb-1.5 px-1 text-[10px] uppercase tracking-wider text-muted">
                  Quick-start by sector
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {VERTICALS.map((v) => (
                    <button
                      key={v.label}
                      onClick={() => startVertical(v)}
                      disabled={!!busyVertical}
                      title={`Build a campaign with real ${v.label} target clients`}
                      className="rounded-lg border border-[var(--border)] px-2 py-1.5 text-[11px] text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-50"
                    >
                      {busyVertical === v.label ? "Building…" : v.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <button
              onClick={toggleArchived}
              className={`flex w-full items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs transition ${
                showArchived
                  ? "border-[var(--brand-navy)] text-foreground"
                  : "border-[var(--border)] text-muted hover:border-[var(--brand-red)] hover:text-foreground"
              }`}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" /></svg>
              {showArchived ? "← Back to active" : "View archived"}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-3">
            {campaigns.map((c) => (
              <div key={c.id} className="group relative">
                <button
                  onClick={() => { setCreating(false); setSelected(c.id); }}
                  className={`mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 pr-14 text-left text-sm transition ${
                    selected === c.id
                      ? "bg-[var(--brand-navy)] text-cream"
                      : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9h18M7 3v3M17 3v3M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" /></svg>
                  <span className="truncate">{c.name}</span>
                </button>
                {showArchived ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); restore(c.id); }}
                    title="Restore campaign"
                    aria-label={`Restore ${c.name}`}
                    className="absolute right-7 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 109-9 9 9 0 00-6.36 2.64L3 8M3 3v5h5" /></svg>
                  </button>
                ) : (
                  <button
                    onClick={(e) => { e.stopPropagation(); archive(c.id); }}
                    title="Archive campaign (recoverable)"
                    aria-label={`Archive ${c.name}`}
                    className="absolute right-7 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" /></svg>
                  </button>
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); removeCampaign(c.id); }}
                  title="Delete campaign"
                  aria-label={`Delete ${c.name}`}
                  className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Main */}
        <div className="min-w-0 flex-1 overflow-y-auto p-6">
          {creating ? (
            tab === "internal" ? (
              <NewInternalCampaign onCreated={onInternalCreated} />
            ) : (
              <NewCampaignChat onPlanned={onPlanned} />
            )
          ) : detail ? (
            detail.type === "internal" ? (
              <InternalCampaignView key={detail.id} detail={detail} />
            ) : (
              <CampaignDetailView
                detail={detail}
                onSectorChange={(s) => onSectorChange(detail.id, s)}
              />
            )
          ) : tab === "internal" ? (
            <EmptyState
              title="Start an internal campaign"
              subtitle="Promote Talentrupt itself — a magazine launch, an announcement, a LinkedIn series. Name it, then describe it in chat and I'll generate the posts, visuals, decks and PDFs into its folder."
              icon={<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9h18M7 3v3M17 3v3M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" /></svg>}
            >
              <button onClick={openNew} className="btn-primary mx-auto">New campaign</button>
            </EmptyState>
          ) : (
            <EmptyState
              title="Start a campaign by sector"
              subtitle="Pick a sector above (IT, Non-IT, Healthcare, Staffing) for a campaign with real, scored target clients — or describe your own."
              icon={<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9h18M7 3v3M17 3v3M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" /></svg>}
            >
              <button onClick={openNew} className="btn-primary mx-auto">New campaign</button>
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}

const GREETING =
  "Tell me about the campaign you want to plan — the goal, who it's for, channels, and how long it should run. " +
  "You can just describe it in a sentence and I'll draft the brief and a dated content calendar.";

const STARTERS = [
  "A 4-week LinkedIn campaign to win healthcare staffing agency clients",
  "Plan a data-driven hiring awareness push for 6 weeks on LinkedIn + Email",
  "A campaign on scaling recruiting without overhead, for staffing firm owners",
];

function NewCampaignChat({ onPlanned }: { onPlanned: (c: CampaignDetail) => void }) {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: GREETING },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, busy]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const next = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await planCampaignChat(next.map((m) => ({ role: m.role, content: m.content })));
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.done && res.campaign) {
        setTimeout(() => onPlanned(res.campaign!), 600);
      }
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "⚠️ Something went wrong — try again." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <div>
        <h2 className="font-heading text-xl font-semibold">New campaign</h2>
        <p className="mt-1 text-sm text-muted">
          Describe what you want — I'll understand the intent and plan it.
        </p>
      </div>

      <div ref={scrollRef} className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl bg-[var(--brand-navy)] px-4 py-2.5 text-sm text-cream">{m.content}</div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm">{m.content}</div>
            </div>
          ),
        )}
        {messages.length === 1 && (
          <div className="grid gap-2 pt-1 sm:grid-cols-1">
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-left text-sm text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {busy && (
          <div className="flex items-center gap-2 px-2 text-xs text-muted">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
            Planning…
          </div>
        )}
      </div>

      <div className="mt-3 flex items-end gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 focus-within:border-[var(--brand-red)]">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
          }}
          rows={1}
          placeholder="Describe the campaign…"
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted"
        />
        <button onClick={() => send(input)} disabled={busy || !input.trim()} className="btn-primary !px-3 !py-2" aria-label="Send">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
        </button>
      </div>
    </div>
  );
}

function CampaignDetailView({
  detail,
  onSectorChange,
}: {
  detail: CampaignDetail;
  onSectorChange: (sector: string) => Promise<void>;
}) {
  const [retargeting, setRetargeting] = useState(false);
  const [view, setView] = useState<"clients" | "calendar">("clients");
  const sector = detail.resolved_sector || "";
  const segCls = (active: boolean) =>
    `rounded-lg px-3 py-1.5 text-xs transition ${active ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)]"}`;

  async function change(next: string) {
    if (!next || next === sector || retargeting) return;
    setRetargeting(true);
    try {
      await onSectorChange(next);
    } finally {
      setRetargeting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-heading text-xl font-semibold">{detail.name}</h2>
          {detail.audience ? (
            <p className="mt-0.5 text-sm text-muted">Target audience: {detail.audience}</p>
          ) : detail.timeline ? (
            <p className="mt-0.5 text-sm text-muted">{detail.timeline}</p>
          ) : null}
          {/* Target sector — what actually drives which clients this folder generates. */}
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Target sector</span>
            <select
              value={sector}
              disabled={retargeting}
              onChange={(e) => change(e.target.value)}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-xs disabled:opacity-50"
              title="Only clients in this sector are generated for this campaign"
            >
              {!sector && <option value="">Select a sector…</option>}
              {SECTORS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            {retargeting && <span className="text-[11px] text-muted">re-targeting clients…</span>}
          </div>
        </div>
      </div>

      {/* View toggle: scored target clients vs the content calendar */}
      <div className="mb-3 mt-6 flex items-center gap-1">
        <button onClick={() => setView("clients")} className={segCls(view === "clients")}>Target clients</button>
        <button onClick={() => setView("calendar")} className={segCls(view === "calendar")}>Content ideas</button>
      </div>
      {view === "calendar" ? (
        // Keyed by campaign id so switching folders remounts the calendar with THIS campaign's
        // items (it seeds local state from props via useState, so without the key it'd stay stale).
        <CampaignCalendar key={detail.id} items={detail.items || []} />
      ) : (
        // Keyed by sector so changing it remounts + re-fetches the (re-filled) clients.
        <CampaignClients key={`${detail.id}:${sector}`} campaignId={detail.id} campaignName={detail.name} />
      )}
    </div>
  );
}

function CampaignClients({ campaignId, campaignName }: { campaignId: number; campaignName: string }) {
  const [tab, setTab] = useState<"active" | "history">("active");
  const [clients, setClients] = useState<CampaignProspect[] | null>(null);
  const [history, setHistory] = useState<CampaignProspect[] | null>(null);
  const [historyTick, setHistoryTick] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [strategyClient, setStrategyClient] = useState<CampaignProspect | null>(null);

  useEffect(() => {
    let alive = true;
    setClients(null);
    getCampaignProspects(campaignId)
      .then((c) => alive && setClients(c))
      .catch(() => alive && setClients([]));
    return () => {
      alive = false;
    };
  }, [campaignId]);

  // Load the Done history eagerly (so the History count badge is accurate without opening it)
  // and refresh it whenever a client is marked Done (historyTick bumps).
  useEffect(() => {
    let alive = true;
    getCampaignProspects(campaignId, "done")
      .then((h) => alive && setHistory(h))
      .catch(() => alive && setHistory([]));
    return () => {
      alive = false;
    };
  }, [campaignId, historyTick]);

  async function markDone(id: number) {
    setBusyId(id);
    setNote("");
    try {
      const res = await markCampaignProspectDone(id);
      setClients((prev) => {
        const list = (prev ?? []).filter((c) => c.id !== id);
        return [...list, ...(res.replacements ?? [])];
      });
      if (!res.replacements?.length) setNote("No fresh match available right now — try again shortly.");
      setHistoryTick((t) => t + 1); // refresh History so its count + list include the newly-done client
    } catch {
      /* leave the card in place so the user can retry */
    } finally {
      setBusyId(null);
    }
  }

  async function removeHistory(id: number) {
    if (!confirm("Remove this client from history?")) return;
    setHistory((prev) => (prev ?? []).filter((c) => c.id !== id)); // optimistic
    try {
      await deleteCampaignProspect(id);
    } catch {
      setHistoryTick((t) => t + 1); // failed — re-sync from the server
    }
  }

  // Revoke = undo a Done: move the client from History back into Active.
  async function revokeClient(id: number) {
    const item = (history ?? []).find((c) => c.id === id);
    setHistory((prev) => (prev ?? []).filter((c) => c.id !== id)); // optimistic
    if (item) setClients((prev) => [...(prev ?? []), { ...item, status: "active" }]);
    try {
      await revokeCampaignProspect(id);
    } catch {
      setHistoryTick((t) => t + 1); // re-sync history
      getCampaignProspects(campaignId).then(setClients).catch(() => {}); // re-sync active
    }
  }

  const box = (text: string, spin = false) => (
    <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-muted">
      {spin && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />}
      {text}
    </div>
  );

  return (
    <div>
      <div className="mb-2 flex items-center gap-1">
        <button
          onClick={() => { setTab("active"); setNote(""); }}
          className={`rounded-lg px-2.5 py-1 text-xs transition ${tab === "active" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)]"}`}
        >
          Active
        </button>
        <button
          onClick={() => { setTab("history"); setNote(""); }}
          className={`rounded-lg px-2.5 py-1 text-xs transition ${tab === "history" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)]"}`}
        >
          History{history && history.length > 0 ? ` (${history.length})` : ""}
        </button>
        <button
          onClick={() => exportCampaignProspects(campaignId, campaignName).catch(() => {})}
          title="Download these target clients as CSV"
          className="ml-auto rounded-lg px-2.5 py-1 text-xs text-muted transition hover:text-foreground"
        >
          Export CSV
        </button>
      </div>

      {tab === "active" ? (
        clients === null ? (
          box("Finding matching clients with their fit score…", true)
        ) : clients.length === 0 ? (
          box("No matching clients surfaced yet — try reopening this campaign shortly.")
        ) : (
          <div>
            <div className="grid gap-2 sm:grid-cols-2">
              {[...clients]
                .sort((a, b) => b.fit_score - a.fit_score)
                .map((c) => (
                  <ClientCard key={c.id} client={c} busy={busyId === c.id} onDone={() => markDone(c.id)} onOpen={() => setStrategyClient(c)} />
                ))}
            </div>
            {note && <p className="mt-2 text-[11px] text-muted">{note}</p>}
          </div>
        )
      ) : history === null ? (
        box("Loading history…", true)
      ) : history.length === 0 ? (
        box("No clients marked Done yet. Tap Done on a client to move it here.")
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {history.map((c) => (
            <ClientCard
              key={c.id}
              client={c}
              busy={false}
              onOpen={() => setStrategyClient(c)}
              onRevoke={() => revokeClient(c.id)}
              onDelete={() => removeHistory(c.id)}
            />
          ))}
        </div>
      )}

      {strategyClient && (
        <StrategyModal client={strategyClient} onClose={() => setStrategyClient(null)} />
      )}
    </div>
  );
}

// Content IDEAS for an external campaign — a dated plan of post/image/deck ideas the user can take into
// Chat or Create to actually generate. (No generate/open here; this is an inspiration board.)
function CampaignCalendar({ items: initial }: { items: CampaignItem[] }) {
  const [items, setItems] = useState<CampaignItem[]>(initial);

  async function reschedule(id: number, date: string) {
    if (!date) return;
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, scheduled_date: date } : i))); // optimistic
    try {
      const up = await updateCampaignItem(id, { scheduled_date: date });
      setItems((prev) => prev.map((i) => (i.id === id ? up : i)));
    } catch {
      /* leave the optimistic value; a reopen re-syncs */
    }
  }

  if (!items.length) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-muted">
        No content ideas for this campaign yet.
      </div>
    );
  }

  const groups: Record<string, CampaignItem[]> = {};
  for (const it of [...items].sort((a, b) => (a.scheduled_date || "").localeCompare(b.scheduled_date || ""))) {
    const k = (it.scheduled_date || "").slice(0, 10) || "Unscheduled";
    (groups[k] ??= []).push(it);
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Content ideas for this campaign — take any idea into <span className="text-foreground">Chat</span> or{" "}
        <span className="text-foreground">Create</span> to generate the post, image, or deck.
      </p>
      {Object.entries(groups).map(([date, its]) => (
        <div key={date}>
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">{date}</div>
          <div className="space-y-1.5">
            {its.map((it) => (
              <div key={it.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm">
                <span className="chip bg-[var(--surface-2)]">{it.channel}</span>
                <span className="chip bg-[var(--surface-2)]">{it.format}</span>
                <span className="min-w-0 flex-1 truncate">{it.topic || it.hook}</span>
                <input
                  type="date"
                  value={(it.scheduled_date || "").slice(0, 10)}
                  onChange={(e) => reschedule(it.id, e.target.value)}
                  title="Reschedule this idea"
                  className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 text-[11px]"
                />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ClientCard({
  client,
  busy,
  onDone,
  onOpen,
  onRevoke,
  onDelete,
}: {
  client: CampaignProspect;
  busy: boolean;
  onDone?: () => void;
  onOpen?: () => void;
  onRevoke?: () => void;
  onDelete?: () => void;
}) {
  const contact = (client.contacts || [])[0];
  const timing = client.timing?.label;
  const who = contact ? [contact.name, contact.role].filter(Boolean).join(" · ") : "";
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  return (
    <div
      onClick={onOpen}
      title="Click for the strategy to win this client"
      className={`flex cursor-pointer flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 transition hover:border-[var(--brand-red)] ${busy ? "opacity-60" : ""}`}
    >
      <div className="flex items-start gap-2.5">
        <Avatar name={client.company} size={32} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-sm font-medium">{client.company}</span>
              {client.company_linkedin ? (
                <a
                  href={client.company_linkedin}
                  target="_blank"
                  rel="noreferrer"
                  onClick={stop}
                  title="Find this company on LinkedIn"
                  className="shrink-0 text-muted transition hover:text-[var(--brand-red)]"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05 4 0 4.74 2.6 4.74 5.98V21h-4v-5.3c0-1.27-.02-2.9-1.77-2.9-1.77 0-2.04 1.38-2.04 2.8V21H9z" /></svg>
                </a>
              ) : null}
            </div>
            <span className="shrink-0 rounded-full bg-[var(--brand-navy)] px-2 py-0.5 text-[11px] font-semibold text-cream">
              {Math.round(client.fit_score)}
            </span>
          </div>
          {client.segment ? <p className="truncate text-[11px] text-muted">{client.segment}</p> : null}
        </div>
      </div>
      {client.hiring_signal ? (
        <p className="mt-2 line-clamp-2 text-xs text-muted">{client.hiring_signal}</p>
      ) : null}
      {(who || contact?.linkedin) && (
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className="truncate text-muted">{who || "Decision-maker"}</span>
          {contact?.linkedin ? (
            <a href={contact.linkedin} target="_blank" rel="noreferrer" onClick={stop} className="shrink-0 text-[var(--brand-red)] hover:underline">
              Search LinkedIn
            </a>
          ) : null}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {timing ? (
            <span className={`chip ${timing === "Reach now" ? "bg-emerald-400/10 text-emerald-300" : "bg-[var(--surface-2)] text-muted"}`}>
              {timing}
            </span>
          ) : null}
          {client.source === "ai_suggested" ? (
            <span className="chip bg-amber-400/10 text-amber-300" title="AI-suggested — verify before outreach">verify</span>
          ) : null}
        </div>
        {onDone ? (
          <button
            onClick={(e) => { stop(e); onDone(); }}
            disabled={busy}
            className="btn-ghost shrink-0 !px-3 !py-1.5 !text-xs"
            title="Mark handled — replace with a fresh client"
          >
            {busy ? "Replacing…" : "Done"}
          </button>
        ) : (
          <div className="flex shrink-0 items-center gap-1.5">
            <span className="chip bg-emerald-400/10 text-emerald-300">Done ✓</span>
            {onRevoke ? (
              <button
                onClick={(e) => { stop(e); onRevoke(); }}
                title="Revoke — move back to Active"
                aria-label="Revoke"
                className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted transition hover:text-[var(--brand-red)]"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></svg>
                Revoke
              </button>
            ) : null}
            {onDelete ? (
              <button
                onClick={(e) => { stop(e); onDelete(); }}
                title="Remove from history"
                aria-label="Remove from history"
                className="rounded-md p-1 text-muted transition hover:text-[var(--brand-red)]"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
              </button>
            ) : null}
          </div>
        )}
      </div>
      <div className="mt-2 border-t border-[var(--border)] pt-2 text-[11px] font-medium text-[var(--brand-red)]">
        View the strategy to win this client →
      </div>
    </div>
  );
}

function StrategyModal({ client, onClose }: { client: CampaignProspect; onClose: () => void }) {
  const [strategy, setStrategy] = useState<ClientStrategy | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setStrategy(null);
    setError(false);
    getCampaignProspectStrategy(client.id)
      .then((r) => alive && setStrategy(r.strategy || {}))
      .catch(() => alive && setError(true));
    return () => {
      alive = false;
    };
  }, [client.id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted">How to win this client</div>
            <h3 className="font-heading text-lg font-semibold">{client.company}</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>

        {strategy === null && !error && (
          <div className="flex items-center gap-2 py-10 text-sm text-muted">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
            Building a tailored strategy for {client.company}…
          </div>
        )}
        {error && <p className="py-10 text-sm text-muted">Couldn&apos;t build the strategy right now — try again.</p>}
        {strategy && (
          <div className="space-y-4 text-sm">
            {strategy.why_fit ? (
              <StratSection title="Why they're a fit"><p className="text-muted">{strategy.why_fit}</p></StratSection>
            ) : null}
            {strategy.approach ? (
              <StratSection title="Winning approach"><p className="text-muted">{strategy.approach}</p></StratSection>
            ) : null}
            {strategy.pain_points?.length ? (
              <StratSection title="Their likely pain points"><StratBullets items={strategy.pain_points} /></StratSection>
            ) : null}
            {strategy.talking_points?.length ? (
              <StratSection title="Talking points"><StratBullets items={strategy.talking_points} /></StratSection>
            ) : null}
            {strategy.recommended_services?.length ? (
              <StratSection title="Recommended Talentrupt services">
                <div className="flex flex-wrap gap-1.5">
                  {strategy.recommended_services.map((s, i) => (
                    <span key={i} className="chip bg-[var(--surface-2)] text-muted">{s}</span>
                  ))}
                </div>
              </StratSection>
            ) : null}
            {strategy.first_touch ? (
              <StratSection title="Suggested first message">
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                  <p className="whitespace-pre-wrap text-muted">{strategy.first_touch}</p>
                  <button
                    onClick={() => navigator.clipboard.writeText(strategy.first_touch || "")}
                    className="mt-2 text-[11px] text-[var(--brand-red)] hover:underline"
                  >
                    Copy message
                  </button>
                </div>
              </StratSection>
            ) : null}
            {!strategy.why_fit && !strategy.approach && !strategy.talking_points?.length && (
              <p className="py-6 text-sm text-muted">No strategy details available — try again.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StratSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">{title}</div>
      {children}
    </div>
  );
}

function StratBullets({ items }: { items: string[] }) {
  return (
    <ul className="ml-4 list-disc space-y-1 text-muted">
      {items.map((t, i) => <li key={i}>{t}</li>)}
    </ul>
  );
}

// --- Internal campaign: name it, then chat to generate the content folder -------------------------
function NewInternalCampaign({ onCreated }: { onCreated: (c: CampaignDetail) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  async function create() {
    const n = name.trim();
    if (!n || busy) return;
    setBusy(true);
    try {
      onCreated(await createInternalCampaign(n, description.trim()));
    } catch {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-xl pt-12">
      <h2 className="text-center font-heading text-2xl font-semibold">New internal campaign</h2>
      <p className="mt-2 text-center text-sm text-muted">
        Name it and describe what it&apos;s about. That brief grounds everything you generate in this
        folder — posts, visuals, decks and PDFs.
      </p>
      <div className="mt-6 space-y-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          placeholder="Campaign name (e.g. Cricket Tournament, Magazine Launch)"
          className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={12}
          placeholder="What's this campaign about? Paste the full brief — theme, objectives, content pillars, tone, hashtags. e.g. “Promote Talentrupt's internal cricket tournament — fun, team-spirited posts for LinkedIn & Instagram celebrating our culture.”"
          className="min-h-[260px] w-full resize-y rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm leading-relaxed outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
        />
        <button onClick={create} disabled={busy || !name.trim()} className="btn-primary w-full">
          {busy ? "Creating…" : "Create campaign"}
        </button>
      </div>
    </div>
  );
}

const CAMPAIGN_GREETING: ChatMessage = {
  role: "assistant",
  content:
    "I've got this campaign's brief. Tell me what to make — a post image, captions, a deck, a PDF — one thing at a time, and it lands in this folder. Tap a starter or just ask.",
};

const CAMPAIGN_STARTERS = [
  "An on-brand post image",
  "A social post caption",
  "An announcement graphic",
  "A short deck",
  "A one-page teaser PDF",
];

// On a NEW campaign we auto-generate a starter pack FROM THE BRIEF; the chat is then for edits.
const CAMPAIGN_SEED =
  "Create a starter set of on-brand posts for this campaign — an image and a caption for each, all on the campaign's theme. Your call on the style.";
// Campaign ids already auto-seeded this session (module-level so a dev remount can't double-fire it).
const _seededCampaigns = new Set<number>();

// An AssetCard with a small delete (trash) control overlaid in the corner — used in the campaign folder.
function DeletableAsset({ asset, onDelete }: { asset: Asset; onDelete: (a: Asset) => void }) {
  return (
    <div className="relative">
      <button
        onClick={() => onDelete(asset)}
        type="button"
        title="Delete"
        aria-label="Delete"
        className="absolute right-2 top-2 z-10 rounded-lg border border-[var(--border)] bg-[var(--surface)]/90 p-1.5 text-muted shadow-sm backdrop-blur transition hover:border-[var(--brand-red)] hover:text-[var(--brand-red)]"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M10 11v6M14 11v6" />
        </svg>
      </button>
      <AssetCard asset={asset} />
    </div>
  );
}

// Edit the campaign brief (the context that grounds generation). Saving updates Campaign.goal so every
// future post/image/deck/PDF is generated from the new description.
function BriefEditor({
  initial,
  onSave,
  onClose,
}: {
  initial: string;
  onSave: (text: string) => Promise<void>;
  onClose: () => void;
}) {
  const [text, setText] = useState(initial);
  const [saving, setSaving] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <span className="font-heading text-sm font-semibold">Campaign brief</span>
          <button onClick={onClose} type="button" aria-label="Close" className="rounded-lg p-1.5 text-muted transition hover:text-foreground">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <p className="mb-2 text-xs text-muted">
            This brief grounds everything generated in this folder. Edit it and save — future posts,
            images, decks and PDFs will use the updated description.
          </p>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={16}
            autoFocus
            placeholder="Describe the campaign — theme, objectives, content pillars, tone, hashtags…"
            className="min-h-[320px] w-full resize-y rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5 text-sm leading-relaxed outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
          />
        </div>
        <div className="flex justify-end gap-2 border-t border-[var(--border)] px-5 py-3">
          <button onClick={onClose} type="button" className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-muted transition hover:text-foreground">
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              try {
                await onSave(text.trim());
                onClose();
              } catch {
                setSaving(false);
              }
            }}
            className="btn-primary px-4 py-2 text-sm disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save brief"}
          </button>
        </div>
      </div>
    </div>
  );
}

function InternalCampaignView({ detail }: { detail: CampaignDetail }) {
  const campaignId = detail.id;
  const [tab, setTab] = useState<"chat" | "gallery">("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(detail.conversation_id ?? null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [assets, setAssets] = useState<Asset[]>(detail.assets ?? []);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attaching, setAttaching] = useState(0);
  const [brief, setBrief] = useState(detail.goal ?? "");
  const [editingBrief, setEditingBrief] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const genRef = useRef(0);

  // Restore the saved thread (with its asset cards). On a brand-new campaign with a brief, AUTO-GENERATE
  // the starter pack from that brief (chat is then for edits); otherwise greet.
  useEffect(() => {
    let live = true;
    getCampaignMessages(campaignId)
      .then((d) => {
        if (!live) return;
        if (d.conversation_id) setConversationId(d.conversation_id);
        const msgs: ChatMessage[] = (d.messages || []).map((m) => ({
          role: m.role === "user" ? "user" : "assistant",
          content: m.content,
          assets: m.assets || [],
        }));
        if (msgs.length) {
          setMessages(msgs);
        } else if ((detail.goal || "").trim() && !_seededCampaigns.has(campaignId)) {
          _seededCampaigns.add(campaignId);
          setMessages([]);
          send(CAMPAIGN_SEED); // generate from the description at creation
        } else {
          setMessages([CAMPAIGN_GREETING]);
        }
      })
      .catch(() => setMessages([CAMPAIGN_GREETING]));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, status]);

  function refreshGallery() {
    getCampaign(campaignId).then((d) => setAssets(d.assets ?? [])).catch(() => {});
  }

  async function handleDeleteAsset(a: Asset) {
    if (!window.confirm("Delete this from the campaign? This can't be undone.")) return;
    try {
      await deleteAsset(a.id);
    } catch {
      return; // leave it in place if the delete failed
    }
    // Drop it from the folder AND from any chat message that showed it.
    setAssets((prev) => prev.filter((x) => x.id !== a.id));
    setMessages((prev) =>
      prev.map((m) => (m.assets ? { ...m, assets: m.assets.filter((x) => x.id !== a.id) } : m)),
    );
  }

  async function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const seen = new Set(attachments.map((a) => a.name));
    for (const f of files) {
      if (seen.has(f.name)) continue;
      seen.add(f.name);
      setAttaching((n) => n + 1);
      try {
        const meta = await uploadAttachment(f);
        setAttachments((a) =>
          a.some((x) => x.name === meta.filename)
            ? a
            : [...a, { id: meta.id, name: meta.filename, text: meta.text, kind: meta.kind, chars: meta.chars }],
        );
      } catch {
        /* ignore one bad file */
      } finally {
        setAttaching((n) => n - 1);
      }
    }
    e.target.value = "";
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy || attaching > 0) return;
    const myGen = (genRef.current += 1);
    const live = () => genRef.current === myGen;
    const atts = attachments.map((a) => ({ name: a.name, text: a.text, id: a.id, kind: a.kind }));
    let gotAsset = false;
    setBusy(true);
    setStatus("");
    setInput("");
    setMessages((m) => [
      ...m,
      { role: "user", content: trimmed },
      { role: "assistant", content: "", pending: true },
    ]);
    try {
      await streamChat(
        trimmed,
        conversationId,
        {
          onMeta: (meta) => { if (live()) setConversationId((id) => id ?? meta.conversation_id); },
          onStatus: (t) => { if (live()) setStatus(t); },
          onToken: (tok) => {
            if (!live()) return;
            setMessages((m) => {
              const last = m[m.length - 1];
              if (last?.role !== "assistant") return m;
              return [...m.slice(0, -1), { ...last, content: last.content + tok }];
            });
          },
          onAsset: (a: Asset) => {
            if (!live()) return;
            gotAsset = true;
            setAssets((prev) => [a, ...prev.filter((x) => x.id !== a.id)]);
            setMessages((m) => {
              const last = m[m.length - 1];
              if (last?.role !== "assistant") return m;
              return [...m.slice(0, -1), { ...last, assets: [...(last.assets ?? []), a] }];
            });
          },
          onChips: (items) => {
            if (!live()) return;
            setStatus("");
            setMessages((m) => {
              const last = m[m.length - 1];
              if (last?.role !== "assistant") return m;
              return [...m.slice(0, -1), { ...last, chips: items, pending: false }];
            });
          },
          onDone: (final) => {
            if (!live()) return;
            setStatus("");
            setMessages((m) => {
              const last = m[m.length - 1];
              if (!last) return m;
              return [...m.slice(0, -1), { ...last, content: final || last.content, pending: false }];
            });
          },
          onError: (err) => {
            if (!live()) return;
            setStatus("");
            setMessages((m) => {
              const last = m[m.length - 1];
              if (last?.role !== "assistant") return m;
              const content = last.content ? `${last.content}\n\n⚠️ ${err}` : `⚠️ ${err}`;
              return [...m.slice(0, -1), { ...last, content, pending: false }];
            });
          },
        },
        `/api/campaigns/${campaignId}/stream`,
        atts,
      );
    } finally {
      if (live()) {
        setBusy(false);
        setStatus("");
        setAttachments([]);
        if (gotAsset) refreshGallery();
      }
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  const onlyGreeting = messages.length === 1 && messages[0] === CAMPAIGN_GREETING;

  return (
    <div className="flex h-full flex-col">
      {/* Header: campaign name + brief + Chat / Generated content tabs */}
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate font-heading text-lg font-semibold">{detail.name}</h2>
          <button
            onClick={() => setEditingBrief(true)}
            type="button"
            title="View / edit the campaign brief"
            className="flex shrink-0 items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-[11px] text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
            Brief
          </button>
        </div>
        <div className="flex shrink-0 rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium">
          <button
            onClick={() => setTab("chat")}
            className={`rounded-md px-3 py-1.5 transition ${tab === "chat" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
          >
            Chat
          </button>
          <button
            onClick={() => { setTab("gallery"); refreshGallery(); }}
            className={`rounded-md px-3 py-1.5 transition ${tab === "gallery" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
          >
            Generated content{assets.length ? ` (${assets.length})` : ""}
          </button>
        </div>
      </div>

      {tab === "gallery" ? (
        <div className="flex-1 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
          {assets.length === 0 ? (
            <p className="pt-10 text-center text-sm text-muted">
              Nothing generated yet — switch to Chat and describe what you want.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {assets.map((a) => (
                <DeletableAsset key={`${a.type}-${a.id}`} asset={a} onDelete={handleDeleteAsset} />
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
            <div className="mx-auto w-full max-w-2xl space-y-5">
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-[var(--brand-navy)] px-4 py-3 text-sm leading-relaxed text-cream">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex flex-col items-start gap-2">
                    {(m.content || m.pending) && (
                      <div className="max-w-[85%] rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm">
                        {m.content ? <Markdown content={m.content} /> : <span className="text-muted">…</span>}
                      </div>
                    )}
                    {m.chips && m.chips.length > 0 && !busy && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.chips.map((c) => (
                          <button key={c} onClick={() => send(c)} className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
                            {c}
                          </button>
                        ))}
                      </div>
                    )}
                    {m.assets && m.assets.length > 0 && (
                      <div className="grid w-full gap-2">
                        {m.assets.map((a, j) => (
                          <DeletableAsset key={`${a.type}-${a.id}-${j}`} asset={a} onDelete={handleDeleteAsset} />
                        ))}
                      </div>
                    )}
                  </div>
                ),
              )}
              {onlyGreeting && (
                <div className="flex flex-wrap gap-1.5 pl-1">
                  {CAMPAIGN_STARTERS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {status && (
                <div className="flex items-center gap-2 px-1 text-xs text-muted">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
                  {status}…
                </div>
              )}
            </div>
          </div>

          <div className="mt-3">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 focus-within:border-[var(--brand-red)]">
              {(attachments.length > 0 || attaching > 0) && (
                <div className="flex flex-wrap gap-1.5 px-1 pb-2">
                  {attachments.map((a) => (
                    <span key={a.id} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-[11px]" title={a.name}>
                      <span className="max-w-[160px] truncate">{a.name}</span>
                      <button onClick={() => setAttachments((x) => x.filter((y) => y.id !== a.id))} className="text-muted hover:text-[var(--brand-red)]" aria-label={`Remove ${a.name}`}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                      </button>
                    </span>
                  ))}
                  {attaching > 0 && <span className="text-[11px] text-muted">Reading file…</span>}
                </div>
              )}
              <div className="flex items-end gap-2">
                <input ref={fileRef} type="file" multiple onChange={onPickFiles} className="hidden" accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.md,.csv,.json" />
                <button onClick={() => fileRef.current?.click()} disabled={attaching > 0} className="shrink-0 rounded-lg p-2 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground disabled:opacity-50" aria-label="Attach a photo" title="Attach a photo (to feature a real person)">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" /></svg>
                </button>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  placeholder="Refine the content, or ask for another post / image / deck…"
                  className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted"
                />
                <button onClick={() => send(input)} disabled={busy || attaching > 0 || !input.trim()} className="btn-primary !px-3 !py-2" aria-label="Send">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </>
      )}
      {editingBrief && (
        <BriefEditor
          initial={brief}
          onClose={() => setEditingBrief(false)}
          onSave={async (text) => {
            await updateCampaignBrief(campaignId, text);
            setBrief(text);
          }}
        />
      )}
    </div>
  );
}
