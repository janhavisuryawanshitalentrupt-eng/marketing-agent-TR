"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  bulkOpportunities,
  clearOpportunities,
  deleteOpportunity,
  discoverProspects,
  vibeDiscover,
  enrichContacts,
  exportOpportunities,
  generateOutreach,
  getOpportunities,
  getTasks,
  intakeCompany,
  setOpportunitySaved,
  trackOutreach,
  updateOpportunity,
  updateTask,
} from "@/lib/api";
import type { BizTask, Opportunity } from "@/lib/types";
import { useAuth } from "./AuthGate";
import { Avatar } from "./Avatar";
import { EmptyState } from "./EmptyState";

const STATUSES = ["new", "contacted", "replied", "meeting"];

// Pipeline status colors (text + subtle bg)
const STATUS_STYLE: Record<string, string> = {
  new: "text-slate-300 bg-slate-400/10",
  contacted: "text-amber-300 bg-amber-400/10",
  replied: "text-sky-300 bg-sky-400/10",
  meeting: "text-emerald-300 bg-emerald-400/10",
};

export function BusinessView() {
  const { health } = useAuth();
  const enrichmentReady = !!health?.enrichment_ready;
  const [query, setQuery] = useState("");
  const [icp, setIcp] = useState<Record<string, string> | null>(null); // how the last vibe was interpreted
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tasks, setTasks] = useState<BizTask[]>([]);
  const [loading, setLoading] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [savedOnly, setSavedOnly] = useState(false);
  const [sortBy, setSortBy] = useState<"newest" | "fit" | "company" | "saved">("newest");
  const [picked, setPicked] = useState<Set<number>>(new Set()); // multi-select for bulk actions

  const setFilter = (key: string, value: string) =>
    setFilters((f) => {
      const next = { ...f };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });

  const selected = useMemo(
    () => opps.find((o) => o.id === selectedId) ?? null,
    [opps, selectedId],
  );

  // The list reflects the active filters (no filters => everything), the Saved toggle, and the
  // chosen sort order. Default "newest" preserves the just-generated-on-top behavior.
  const filteredOpps = useMemo(() => {
    const ind = filters.industry;
    const kw = (filters.keywords || "").toLowerCase().trim();
    const title = (filters.title || "").toLowerCase().trim();
    const list = opps.filter((o) => {
      if (savedOnly && !o.saved) return false;
      if (ind && !industryMatch(o.segment, ind)) return false;
      const hay = `${o.company} ${o.segment} ${o.hiring_signal} ${o.recommended_service} ${o.why?.why_now || ""}`.toLowerCase();
      if (kw && !hay.includes(kw)) return false;
      if (title) {
        const roles = (o.why?.contacts || []).map((c) => (c.role || "").toLowerCase()).join(" ");
        if (!roles.includes(title) && !hay.includes(title)) return false;
      }
      return true;
    });
    const byNewest = (a: Opportunity, b: Opportunity) =>
      (b.created_at || "").localeCompare(a.created_at || "") || b.fit_score - a.fit_score || b.id - a.id;
    return [...list].sort((a, b) => {
      if (sortBy === "fit") return b.fit_score - a.fit_score || byNewest(a, b);
      if (sortBy === "company") return a.company.localeCompare(b.company);
      if (sortBy === "saved") return Number(!!b.saved) - Number(!!a.saved) || byNewest(a, b);
      return byNewest(a, b); // "newest"
    });
  }, [opps, filters, savedOnly, sortBy]);

  const savedCount = useMemo(() => opps.filter((o) => o.saved).length, [opps]);
  const filtersActive = Object.keys(filters).length > 0 || savedOnly;

  useEffect(() => {
    refreshOpps();
    getTasks().then(setTasks).catch(() => {});
  }, []);

  // Deep-link from the Tasks view ("/business?prospect=<opportunity_id>") — select that prospect.
  // Distinct param from Campaigns' "?open" so the two persistent views don't cross-talk.
  const prospectParam = useSearchParams().get("prospect");
  useEffect(() => {
    const id = Number(prospectParam);
    if (prospectParam && Number.isFinite(id) && id > 0) {
      setSelectedId(id);
      setSavedOnly(false); // make sure a filter doesn't hide the linked prospect from the list
      setFilters({});
    }
  }, [prospectParam]);

  function refreshOpps() {
    getOpportunities().then(setOpps).catch(() => {});
  }

  async function find() {
    if (loading) return; // re-entry guard: ignore Enter/clicks while a search is in flight
    setLoading("Searching LinkedIn & the web for companies that are hiring…");
    try {
      const res = await discoverProspects(
        null,
        query,
        8,
        Object.keys(filters).length ? filters : undefined,
      );
      setOpps((prev) => mergeById(res.opportunities, prev));
      if (res.opportunities[0]) setSelectedId(res.opportunities[0].id);
    } finally {
      setLoading("");
    }
  }

  // VIBE match: interpret the freeform "ideal client" into a sharp ICP, then discover + rank real firms.
  async function vibeFind() {
    if (loading || !query.trim()) return;
    setLoading("Reading your vibe, then finding companies that match…");
    try {
      const res = await vibeDiscover(query.trim(), 8);
      setIcp(res.icp && Object.keys(res.icp).length ? res.icp : null);
      setOpps((prev) => mergeById(res.opportunities, prev));
      if (res.opportunities[0]) setSelectedId(res.opportunities[0].id);
    } finally {
      setLoading("");
    }
  }

  async function analyze() {
    const name = query.trim();
    if (!name) return;
    setLoading(`Analyzing ${name}…`);
    try {
      const o = await intakeCompany(name);
      setOpps((prev) => mergeById([o], prev));
      setSelectedId(o.id);
      setQuery("");
    } finally {
      setLoading("");
    }
  }

  async function setStatus(id: number, status: string) {
    const o = await updateOpportunity(id, status);
    setOpps((prev) => prev.map((x) => (x.id === id ? o : x)));
  }

  async function toggleSaved(id: number, saved: boolean) {
    // optimistic
    setOpps((prev) => prev.map((x) => (x.id === id ? { ...x, saved } : x)));
    try {
      const o = await setOpportunitySaved(id, saved);
      setOpps((prev) => prev.map((x) => (x.id === id ? o : x)));
    } catch {
      setOpps((prev) => prev.map((x) => (x.id === id ? { ...x, saved: !saved } : x)));
    }
  }

  async function doOutreach(id: number) {
    setLoading("Writing personalized outreach…");
    try {
      const o = await generateOutreach(id);
      setOpps((prev) => prev.map((x) => (x.id === id ? o : x)));
      getTasks().then(setTasks).catch(() => {});
    } finally {
      setLoading("");
    }
  }

  async function track(id: number, patch: Parameters<typeof trackOutreach>[1]) {
    const o = await trackOutreach(id, patch);
    setOpps((prev) => prev.map((x) => (x.id === id ? o : x)));
  }

  async function enrich(id: number) {
    setLoading("Looking up verified contacts…");
    try {
      const o = await enrichContacts(id);
      setOpps((prev) => prev.map((x) => (x.id === id ? o : x)));
    } finally {
      setLoading("");
    }
  }

  async function taskAction(taskId: number, patch: Parameters<typeof updateTask>[1]) {
    await updateTask(taskId, patch);
    getTasks().then(setTasks).catch(() => {});
  }

  function exportCsv() {
    exportOpportunities({ saved: savedOnly || undefined }).catch(() => {});
  }

  function togglePick(id: number) {
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function runBulk(action: "status" | "save" | "unsave" | "delete", status?: string) {
    const ids = [...picked];
    if (!ids.length) return;
    if (action === "delete" && !confirm(`Remove ${ids.length} prospect(s)? Saved ones included.`)) return;
    await bulkOpportunities({ ids, action, status });
    setPicked(new Set());
    const remaining = await getOpportunities();
    setOpps(remaining);
    if (!remaining.some((o) => o.id === selectedId)) setSelectedId(null);
    getTasks().then(setTasks).catch(() => {});
  }

  async function remove(id: number) {
    if (!confirm("Remove this prospect?")) return;
    await deleteOpportunity(id);
    setOpps((prev) => prev.filter((x) => x.id !== id));
    setPicked((prev) => { const n = new Set(prev); n.delete(id); return n; });
    if (selectedId === id) setSelectedId(null);
    getTasks().then(setTasks).catch(() => {}); // its follow-ups are gone now
  }

  async function clearAll() {
    if (!confirm("Remove all UNSAVED prospects? Your saved (★) ones are kept.")) return;
    setLoading("Clearing unsaved prospects…");
    try {
      await clearOpportunities();
      const remaining = await getOpportunities();
      setOpps(remaining);
      if (!remaining.some((o) => o.id === selectedId)) setSelectedId(null);
      getTasks().then(setTasks).catch(() => {}); // refresh so cleared follow-ups don't linger
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Composer: ONE search bar — Find prospects (criteria) or Analyze (a single named company) */}
      <div className="border-b border-[var(--border)] px-6 py-4">
        <div className="card p-4">
          <div className="mb-2.5 flex items-center justify-between gap-2">
            <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted">
              Find or analyze companies
            </span>
            <FilterBar
              filters={filters}
              setFilter={setFilter}
              onClear={() => setFilters({})}
              filtersActive={filtersActive}
            />
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && vibeFind()}
              placeholder="Describe your ideal client — the vibe (e.g. 'US healthcare groups scaling clinical hiring fast') — or a company name to analyze"
              className="field flex-1"
            />
            <div className="flex gap-2">
              <button onClick={vibeFind} disabled={!!loading || !query.trim()} className="btn-primary justify-center whitespace-nowrap">
                ✨ Vibe match
              </button>
              <button onClick={find} disabled={!!loading} className="btn-ghost justify-center whitespace-nowrap">
                Find
              </button>
              <button
                onClick={analyze}
                disabled={!!loading || !query.trim()}
                className="btn-ghost justify-center whitespace-nowrap"
              >
                Analyze
              </button>
            </div>
          </div>
          {icp && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[11px]">
              <span className="shrink-0 font-semibold text-foreground">Read your vibe as:</span>
              {icp.summary ? (
                <span className="text-muted">{icp.summary}</span>
              ) : (
                [icp.industry, icp.company_size, icp.location, icp.signal, icp.keywords]
                  .filter(Boolean)
                  .map((v, i) => (
                    <span key={i} className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-muted">{v}</span>
                  ))
              )}
            </div>
          )}
          <p className="mt-2 text-[11px] text-muted">
            <span className="font-medium text-foreground">✨ Vibe match</span> reads your description, sharpens it into a target profile, and returns a scored list of real companies.{" "}
            <span className="font-medium text-foreground">Find</span> runs a plain search; <span className="font-medium text-foreground">Analyze</span> evaluates one named company.
          </p>
          {loading && (
            <p className="mt-2 flex items-center gap-2 text-xs text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
              {loading}
            </p>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* Opportunity list */}
        <div className="w-72 shrink-0 overflow-y-auto border-r border-[var(--border)] p-3">
          {opps.length > 0 && (
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <span className="text-[11px] text-muted">
                {filtersActive ? `${filteredOpps.length} of ${opps.length}` : opps.length} prospect{opps.length === 1 ? "" : "s"}
              </span>
              <div className="flex items-center gap-2.5">
                <button
                  onClick={() => setSavedOnly((s) => !s)}
                  title="Show only saved (★) prospects"
                  className={`flex items-center gap-1 text-[11px] transition ${savedOnly ? "text-[var(--brand-red)]" : "text-muted hover:text-foreground"}`}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill={savedOnly ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l3 6.5 7 .9-5 4.8 1.3 7L12 18l-6.3 3.2L7 14.2 2 9.4l7-.9z" /></svg>
                  Saved{savedCount > 0 ? ` ${savedCount}` : ""}
                </button>
                <button
                  onClick={exportCsv}
                  className="text-[11px] text-muted transition hover:text-foreground"
                  title="Download the prospect list as CSV"
                >
                  Export
                </button>
                <button
                  onClick={clearAll}
                  className="text-[11px] text-muted transition hover:text-[var(--brand-red)]"
                  title="Remove unsaved prospects (saved ★ are kept)"
                >
                  Clear
                </button>
              </div>
            </div>
          )}
          {picked.size > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--brand-red)]/40 bg-[var(--surface-2)] px-2 py-1.5">
              <span className="text-[11px] font-medium">{picked.size} selected</span>
              <div className="ml-auto flex items-center gap-1.5">
                <select
                  onChange={(e) => { if (e.target.value) { runBulk("status", e.target.value); e.target.value = ""; } }}
                  defaultValue=""
                  title="Set pipeline status for selected"
                  className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-1 py-0.5 text-[11px]"
                >
                  <option value="">Set status…</option>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <button onClick={() => runBulk("save")} className="text-[11px] text-muted hover:text-foreground" title="Save selected">Save</button>
                <button onClick={() => runBulk("unsave")} className="text-[11px] text-muted hover:text-foreground" title="Unsave selected">Unsave</button>
                <button onClick={() => runBulk("delete")} className="text-[11px] text-muted hover:text-[var(--brand-red)]" title="Delete selected">Delete</button>
                <button onClick={() => setPicked(new Set())} className="text-[11px] text-muted hover:text-foreground" title="Clear selection">✕</button>
              </div>
            </div>
          )}
          {opps.length > 0 && (
            <div className="mb-2 flex items-center gap-1.5 px-1">
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted">Sort</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                title="Sort the prospects list"
                className="flex-1 rounded-md border border-[var(--border)] bg-[var(--surface)] px-1.5 py-1 text-[11px] text-foreground"
              >
                <option value="newest">Newest first</option>
                <option value="fit">Top fit</option>
                <option value="company">Company A–Z</option>
                <option value="saved">Saved first</option>
              </select>
            </div>
          )}
          {opps.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted">
              No prospects yet. Set filters and Find prospects.
            </p>
          ) : filteredOpps.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted">
              No prospects match these filters.{" "}
              <button onClick={() => setFilters({})} className="text-[var(--brand-red)] hover:underline">Clear filters</button>
            </p>
          ) : null}
          {filteredOpps.map((o) => (
            <div
              key={o.id}
              onClick={() => setSelectedId(o.id)}
              className={`group relative mb-1.5 cursor-pointer rounded-xl border p-3 transition ${
                selectedId === o.id
                  ? "border-[var(--brand-red)] bg-[var(--surface-2)]"
                  : "border-[var(--border)] hover:bg-[var(--surface-2)]"
              } ${picked.has(o.id) ? "ring-1 ring-[var(--brand-red)]" : ""}`}
            >
              <button
                onClick={(e) => { e.stopPropagation(); togglePick(o.id); }}
                title="Select for bulk actions"
                aria-label={picked.has(o.id) ? "Deselect" : "Select"}
                className={`absolute left-1 top-1 z-10 flex h-4 w-4 items-center justify-center rounded border text-[9px] leading-none transition ${
                  picked.has(o.id)
                    ? "border-[var(--brand-red)] bg-[var(--brand-red)] text-white opacity-100"
                    : "border-[var(--border)] bg-[var(--surface)] text-transparent opacity-0 group-hover:opacity-100"
                }`}
              >
                ✓
              </button>
              <div className="flex items-center gap-2.5">
                <Avatar name={o.company} size={34} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleSaved(o.id, !o.saved); }}
                        title={o.saved ? "Saved — click to remove from shortlist" : "Save to shortlist"}
                        aria-label={o.saved ? "Unsave" : "Save"}
                        className={`shrink-0 transition ${o.saved ? "text-[var(--brand-red)]" : "text-muted opacity-40 hover:opacity-100"}`}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill={o.saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l3 6.5 7 .9-5 4.8 1.3 7L12 18l-6.3 3.2L7 14.2 2 9.4l7-.9z" /></svg>
                      </button>
                      <span className="truncate text-sm font-medium">{o.company}</span>
                    </div>
                    <span className="shrink-0 rounded-full bg-[var(--brand-navy)] px-2 py-0.5 text-[11px] font-semibold text-cream transition group-hover:opacity-0">
                      {Math.round(o.fit_score)}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="truncate text-[11px] text-muted">{o.segment}</span>
                    <span className={`chip ${STATUS_STYLE[o.status] ?? STATUS_STYLE.new}`}>
                      {o.status}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); remove(o.id); }}
                className="absolute right-2 top-2.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
                aria-label={`Remove ${o.company}`}
                title="Remove prospect"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
              </button>
            </div>
          ))}
        </div>

        {/* Detail */}
        <div className="min-w-0 flex-1 overflow-y-auto p-6">
          {!selected ? (
            <EmptyState
              title="Select a prospect"
              subtitle="Choose a company from the list to see hiring signals, the decision-maker, and outreach."
              icon={
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6" />
                </svg>
              }
            />
          ) : (
            <OppDetail
              opp={selected}
              tasks={tasks.filter((t) => t.opportunity_id === selected.id)}
              onStatus={(s) => setStatus(selected.id, s)}
              onOutreach={() => doOutreach(selected.id)}
              onDelete={() => remove(selected.id)}
              onToggleSave={() => toggleSaved(selected.id, !selected.saved)}
              onTrack={(p) => track(selected.id, p)}
              onEnrich={() => enrich(selected.id)}
              onTaskAction={taskAction}
              enrichmentReady={enrichmentReady}
              busy={!!loading}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function mergeById(incoming: Opportunity[], prev: Opportunity[]): Opportunity[] {
  const map = new Map(prev.map((o) => [o.id, o]));
  for (const o of incoming) map.set(o.id, o);
  // Newest first (just-generated clients on top), then by fit score, then id — matches the backend.
  return [...map.values()].sort((a, b) => {
    const t = (b.created_at || "").localeCompare(a.created_at || "");
    if (t !== 0) return t;
    return b.fit_score - a.fit_score || b.id - a.id;
  });
}

function OppDetail({
  opp,
  tasks,
  onStatus,
  onOutreach,
  onDelete,
  onToggleSave,
  onTrack,
  onEnrich,
  onTaskAction,
  enrichmentReady,
  busy,
}: {
  opp: Opportunity;
  tasks: BizTask[];
  onStatus: (s: string) => void;
  onOutreach: () => void;
  onDelete: () => void;
  onToggleSave: () => void;
  onTrack: (patch: { channel?: string; sent_at?: string; replied_at?: string; meeting_at?: string; notes?: string }) => void;
  onEnrich: () => void;
  onTaskAction: (taskId: number, patch: { status?: "pending" | "done" | "snoozed"; snooze_days?: number }) => void;
  enrichmentReady: boolean;
  busy: boolean;
}) {
  const w = opp.why || {};
  const outreach = w.outreach;
  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="font-heading text-xl font-semibold">{opp.company}</h2>
            <span className="rounded-full bg-[var(--brand-navy)] px-2.5 py-0.5 text-xs text-cream">
              Fit {Math.round(opp.fit_score)}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {opp.segment}
            {w.website ? (
              <>
                {" · "}
                <a href={prefixUrl(w.website)} target="_blank" rel="noreferrer" className="text-[var(--brand-red)] underline">
                  {w.website}
                </a>
              </>
            ) : null}
            {opp.company_linkedin ? (
              <>
                {" · "}
                <a href={opp.company_linkedin} target="_blank" rel="noreferrer" className="text-[var(--brand-red)] underline">
                  LinkedIn
                </a>
              </>
            ) : null}
            {w.source ? (
              <span className={`ml-2 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                w.source === "web_research" ? "bg-[var(--surface-2)]" : "bg-amber-400/10 text-amber-300"
              }`}>
                {w.source === "web_research" ? "live web" : "unverified · verify"}
              </span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            onClick={onToggleSave}
            title={opp.saved ? "Saved — click to remove from shortlist" : "Save to shortlist"}
            aria-label={opp.saved ? "Unsave" : "Save"}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition ${
              opp.saved
                ? "border-[var(--brand-red)] text-[var(--brand-red)]"
                : "border-[var(--border)] text-muted hover:text-foreground"
            }`}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill={opp.saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l3 6.5 7 .9-5 4.8 1.3 7L12 18l-6.3 3.2L7 14.2 2 9.4l7-.9z" /></svg>
            {opp.saved ? "Saved" : "Save"}
          </button>
          <button onClick={onDelete} className="rounded-lg border border-[var(--border)] p-2 text-muted hover:text-[var(--brand-red)]" title="Remove" aria-label="Remove">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
          </button>
        </div>
      </div>

      {/* Pipeline */}
      <div className="mt-4 flex gap-1">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => onStatus(s)}
            className={`rounded-lg px-3 py-1.5 text-xs capitalize transition ${
              opp.status === s
                ? "bg-[var(--brand-navy)] text-cream"
                : "border border-[var(--border)] text-muted hover:bg-[var(--surface-2)]"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Outreach tracking (track-only — the app never sends) */}
      <TrackingCard log={w.outreach_log} onTrack={onTrack} />

      {/* Timing — is now a good moment to reach out? */}
      <TimingBanner timing={w.timing} />

      {/* Signal / why */}
      <div className="mt-4 space-y-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
        <Field label="Hiring signal" value={opp.hiring_signal} />
        <Field label="Why now" value={w.why_now} />
        <Field label="Why Talentrupt fits" value={w.why_fit} />
        <Field label="Recommended service" value={opp.recommended_service} />
        {opp.pain_point ? <Field label="Pain points" value={opp.pain_point} /> : null}
      </div>

      {/* Decision-makers & contacts */}
      <Contacts w={w} enrichmentReady={enrichmentReady} onEnrich={onEnrich} busy={busy} />

      {/* Outreach */}
      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-heading text-sm font-semibold text-muted">Outreach</h3>
          <button onClick={onOutreach} disabled={busy} className="btn-primary !px-3 !py-1.5 !text-xs">
            {outreach ? "Regenerate" : "Generate outreach"}
          </button>
        </div>
        {!outreach ? (
          <p className="text-sm text-muted">No outreach yet. Generate a personalized email + LinkedIn message.</p>
        ) : (
          <div className="space-y-3">
            <CopyBlock title="Email" text={`${outreach.email_subject ?? ""}\n\n${outreach.email_body ?? ""}`}>
              <p className="font-medium">{outreach.email_subject}</p>
              <p className="mt-1 whitespace-pre-wrap text-muted">{outreach.email_body}</p>
            </CopyBlock>
            <CopyBlock title="LinkedIn message" text={outreach.linkedin_message ?? ""}>
              <p className="whitespace-pre-wrap text-muted">{outreach.linkedin_message}</p>
            </CopyBlock>
            {outreach.talking_points && outreach.talking_points.length > 0 && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4 text-sm">
                <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">Talking points</p>
                <ul className="ml-4 list-disc space-y-1 text-muted">
                  {outreach.talking_points.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Follow-ups */}
      {tasks.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 font-heading text-sm font-semibold text-muted">Scheduled follow-ups</h3>
          <div className="space-y-1.5">
            {tasks.map((t) => (
              <div key={t.id} className={`flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm ${t.status === "done" ? "opacity-50" : ""}`}>
                <span className="rounded-md bg-[var(--brand-navy)] px-2 py-0.5 text-[11px] text-cream">
                  {t.due_at?.slice(0, 10)}
                </span>
                <span className={`text-muted ${t.status === "done" ? "line-through" : ""}`}>{t.title}</span>
                <div className="ml-auto flex shrink-0 items-center gap-2">
                  {t.status !== "done" && (
                    <>
                      <button onClick={() => onTaskAction(t.id, { snooze_days: 3 })} className="text-[11px] text-muted hover:text-foreground" title="Snooze 3 days">Snooze</button>
                      <button onClick={() => onTaskAction(t.id, { status: "done" })} className="text-[11px] text-[var(--brand-red)] hover:underline" title="Mark done">Done</button>
                    </>
                  )}
                  {t.status === "done" && <span className="text-[11px] text-emerald-300">✓ done</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TrackingCard({
  log,
  onTrack,
}: {
  log?: Opportunity["why"]["outreach_log"];
  onTrack: (patch: { channel?: string; sent_at?: string; replied_at?: string; meeting_at?: string }) => void;
}) {
  const l = log || {};
  const [channel, setChannel] = useState(l.channel || "email");
  const fmt = (d?: string | null) => (d ? d.slice(0, 10) : "");
  const btn = (label: string, field: "sent_at" | "replied_at" | "meeting_at", val?: string | null) => (
    <button
      onClick={() => onTrack({ [field]: "now", channel })}
      title={val ? `Recorded ${fmt(val)} — click to update` : `Record ${label.toLowerCase()} (now)`}
      className={`rounded-lg border px-2.5 py-1.5 text-xs transition ${
        val
          ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
          : "border-[var(--border)] text-muted hover:border-[var(--brand-red)] hover:text-foreground"
      }`}
    >
      {val ? `${label} · ${fmt(val)}` : `Mark ${label.toLowerCase()}`}
    </button>
  );
  return (
    <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted">Outreach tracking</span>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          title="Channel for the next recorded action"
          className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 text-[11px]"
        >
          <option value="email">Email</option>
          <option value="linkedin">LinkedIn</option>
          <option value="phone">Phone</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {btn("Sent", "sent_at", l.sent_at)}
        {btn("Replied", "replied_at", l.replied_at)}
        {btn("Meeting", "meeting_at", l.meeting_at)}
      </div>
      {l.history && l.history.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-[var(--border)] pt-2 text-[11px] text-muted">
          {l.history.slice(-5).map((h, i) => (
            <li key={i}>
              <span className="capitalize text-foreground">{h.event}</span> · {fmt(h.at)}
              {h.channel ? ` · ${h.channel}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const TIMING_STYLE: Record<string, string> = {
  "Reach now": "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  Monitor: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  Hold: "border-rose-400/30 bg-rose-400/10 text-rose-300",
};

function TimingBanner({ timing }: { timing?: Opportunity["why"]["timing"] }) {
  if (!timing || (!timing.label && !timing.reason)) return null;
  const label = timing.label || (timing.reach_now ? "Reach now" : "Monitor");
  const dot = label === "Reach now" ? "bg-emerald-400" : label === "Hold" ? "bg-rose-400" : "bg-amber-400";
  return (
    <div className={`mt-4 flex items-start gap-3 rounded-xl border p-3 text-sm ${TIMING_STYLE[label] ?? TIMING_STYLE.Monitor}`}>
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} />
      <div>
        <div className="font-semibold">Best time to reach: {label}</div>
        {timing.reason && <div className="mt-0.5 text-muted">{timing.reason}</div>}
      </div>
    </div>
  );
}

function Contacts({
  w,
  enrichmentReady,
  onEnrich,
  busy,
}: {
  w: Opportunity["why"];
  enrichmentReady: boolean;
  onEnrich: () => void;
  busy: boolean;
}) {
  // Prefer the multi-contact array; fall back to the legacy single decision-maker.
  const contacts =
    w.contacts && w.contacts.length > 0
      ? w.contacts
      : w.decision_maker || w.decision_maker_linkedin || w.decision_maker_email
        ? [{
            name: "",
            role: w.decision_maker,
            linkedin: w.decision_maker_linkedin,
            email: w.decision_maker_email,
          }]
        : [];
  const verified = w.verified_contacts || [];
  if (contacts.length === 0 && verified.length === 0 && !enrichmentReady) return null;
  return (
    <div className="mt-6">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="font-heading text-sm font-semibold text-muted">
          Decision-makers ({contacts.length})
        </h3>
        {enrichmentReady && (
          <button
            onClick={onEnrich}
            disabled={busy}
            title="Fetch real, provider-verified contacts"
            className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-50"
          >
            {verified.length ? "Re-enrich" : "Enrich contacts"}
          </button>
        )}
      </div>
      {verified.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[11px] font-medium text-emerald-300">Verified contacts</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {verified.map((c, i) => (
              <ContactCard key={`v${i}`} c={c} verified />
            ))}
          </div>
        </div>
      )}
      {contacts.length > 0 && (
        <>
          <p className="mb-2 text-[11px] text-muted">
            No guessed names. &ldquo;Search LinkedIn&rdquo; appears only when it can reliably find the right person.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {contacts.map((c, i) => (
              <ContactCard key={i} c={c} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ContactCard({
  c,
  verified,
}: {
  c: { name?: string; role?: string; linkedin?: string; email?: string };
  verified?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const display = c.name || c.role || "Contact";
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3">
      <div className="text-sm font-medium">{display}</div>
      {c.name && c.role ? <div className="text-xs text-muted">{c.role}</div> : null}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {c.linkedin && (
          <a
            href={c.linkedin}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2 py-1 text-xs text-[var(--brand-red)] transition hover:bg-[var(--surface-2)]"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4.98 3.5a2.5 2.5 0 11-.02 5 2.5 2.5 0 01.02-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05 4 0 4.74 2.6 4.74 5.98V21h-4v-5.3c0-1.27-.02-2.9-1.77-2.9-1.77 0-2.04 1.38-2.04 2.8V21H9z" />
            </svg>
            {verified ? "LinkedIn" : "Search LinkedIn"}
          </a>
        )}
        {c.email && (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2 py-1 text-xs">
            <span className="truncate text-muted">{c.email}</span>
            <button
              onClick={() =>
                navigator.clipboard.writeText(c.email!).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                })
              }
              className="text-muted transition hover:text-foreground"
            >
              {copied ? "✓" : "Copy"}
            </button>
          </span>
        )}
        {c.email && (
          <span className={`chip ${verified ? "bg-emerald-400/10 text-emerald-300" : "bg-amber-400/10 text-amber-300"}`}>
            {verified ? "verified" : "unverified"}
          </span>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}

function CopyBlock({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-muted">{title}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(text).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
          className="text-[11px] text-muted hover:text-foreground"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {children}
    </div>
  );
}

function prefixUrl(u: string): string {
  return u.startsWith("http") ? u : `https://${u}`;
}

// --- Find-prospects filters (LinkedIn-style: icon + dropdown) -------------
const INDUSTRIES = [
  "Staffing & Recruiting", "Healthcare", "IT & Software", "Engineering",
  "Finance & Fintech", "Manufacturing", "Life Sciences", "Professional Services",
  "Retail & E-commerce", "Other",
];
const SIZES: (string | { label: string; value: string })[] = [
  { label: "Up to 500 — ideal for RPO", value: "1-500" },
  "1-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10000+",
];
const SIGNALS = [
  "Actively hiring",
  "Hiring at volume",
  "Newly funded",
  "High-growth / scaling",
  "Overloaded recruiting team",
  "Lacks internal recruiters",
  "Opened a new office / location",
];

// Quick-pick suggestions for the (free-text) Location filter. US-centric because discovery
// defaults to the US; the user can still type anything (these only pre-fill the box).
const LOCATIONS = [
  "United States",
  "Remote (US)",
  "New York, NY",
  "San Francisco Bay Area",
  "Los Angeles, CA",
  "Chicago, IL",
  "Dallas–Fort Worth, TX",
  "Houston, TX",
  "Austin, TX",
  "Atlanta, GA",
  "Boston, MA",
  "Seattle, WA",
  "Denver, CO",
  "Miami, FL",
  "Phoenix, AZ",
  "Washington, DC",
];

const INDUSTRY_KEYWORDS: Record<string, string[]> = {
  "Staffing & Recruiting": ["staffing", "recruit", "rpo", "talent", "workforce"],
  Healthcare: ["health", "clinical", "medical", "nurse", "care", "hospital"],
  "IT & Software": ["software", "saas", "tech", "cloud", "ai ", "data", "developer", "it ", "fintech"],
  Engineering: ["engineer", "manufactur", "industrial", "construction"],
  "Finance & Fintech": ["finance", "fintech", "bank", "financial", "insurance"],
  Manufacturing: ["manufactur", "industrial", "factory"],
  "Life Sciences": ["life science", "biotech", "pharma", "clinical"],
  "Professional Services": ["consult", "professional services", "agency", "services"],
  "Retail & E-commerce": ["retail", "e-commerce", "ecommerce", "commerce"],
  Other: [],
};

function industryMatch(segment: string, industry: string): boolean {
  if (industry === "Other") return true;
  const seg = (segment || "").toLowerCase();
  const kws = INDUSTRY_KEYWORDS[industry] || [industry.toLowerCase().split(/[ &]/)[0]];
  return kws.some((k) => seg.includes(k.trim()));
}

type FilterCfg = {
  key: string;
  title: string;
  kind: "text" | "select";
  options?: (string | { label: string; value: string })[];
  suggestions?: string[]; // quick-pick chips for a free-text filter (typing still allowed)
  placeholder?: string;
  icon: string;
};

const FILTERS: FilterCfg[] = [
  { key: "signal", title: "Buying signal", kind: "select", options: SIGNALS, icon: "M13 2L3 14h9l-1 8 10-12h-9l1-8z" },
  { key: "title", title: "Title / Role", kind: "text", placeholder: "e.g. VP Talent Acquisition", icon: "M3 7h18v13H3zM8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" },
  { key: "industry", title: "Industry", kind: "select", options: INDUSTRIES, icon: "M3 21h18M4 21V8l6-4 6 4M4 11h12M9 21v-4h2v4M19 21V11l-3-2" },
  { key: "company_size", title: "Company size", kind: "select", options: SIZES, icon: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87" },
  { key: "location", title: "Location", kind: "text", suggestions: LOCATIONS, placeholder: "e.g. United States, Remote", icon: "M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0zM12 13a3 3 0 100-6 3 3 0 000 6z" },
];

function FilterBar({
  filters,
  setFilter,
  onClear,
  filtersActive,
}: {
  filters: Record<string, string>;
  setFilter: (key: string, value: string) => void;
  onClear: () => void;
  filtersActive: boolean;
}) {
  return (
    <div className="flex items-center gap-1">
      {FILTERS.map((f) => (
        <FilterControl key={f.key} cfg={f} value={filters[f.key] || ""} onChange={(v) => setFilter(f.key, v)} />
      ))}
      {filtersActive && (
        <button
          onClick={onClear}
          title="Clear filters"
          aria-label="Clear filters"
          className="rounded-lg border border-[var(--border)] p-1.5 text-muted transition hover:border-[var(--brand-red)] hover:text-[var(--brand-red)]"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

function FilterControl({
  cfg,
  value,
  onChange,
  wide,
  noDot,
}: {
  cfg: FilterCfg;
  value: string;
  onChange: (v: string) => void;
  wide?: boolean;
  noDot?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const active = !!value;
  const highlight = active && !noDot;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={cfg.title}
        aria-label={cfg.title}
        className={`relative flex items-center gap-1 rounded-lg border p-1.5 text-[11px] transition ${
          highlight
            ? "border-[var(--brand-red)] text-foreground"
            : "border-[var(--border)] text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
        }`}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d={cfg.icon} />
        </svg>
        {active && <span className={`truncate ${wide ? "max-w-[150px]" : "max-w-[72px]"}`}>{value}</span>}
        {active && !noDot && <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-[var(--brand-red)]" />}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-2 shadow-xl">
            <div className="mb-1.5 px-1 text-[11px] uppercase tracking-wide text-muted">{cfg.title}</div>
            {cfg.kind === "select" ? (
              <div className="max-h-56 overflow-y-auto">
                {(cfg.options ?? []).map((opt) => {
                  const o = typeof opt === "string" ? { label: opt, value: opt } : opt;
                  return (
                    <button
                      key={o.value}
                      onClick={() => { onChange(o.value); setOpen(false); }}
                      className={`block w-full rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-[var(--surface-2)] ${value === o.value ? "text-[var(--brand-red)]" : ""}`}
                    >
                      {o.label}
                    </button>
                  );
                })}
              </div>
            ) : (
              <>
                <input
                  autoFocus
                  className="field"
                  value={value}
                  onChange={(e) => onChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") setOpen(false); }}
                  placeholder={cfg.placeholder}
                />
                {cfg.suggestions && cfg.suggestions.length > 0 && (() => {
                  const q = value.trim().toLowerCase();
                  const matches = cfg.suggestions.filter((s) => s.toLowerCase().includes(q));
                  return matches.length > 0 ? (
                    <div className="mt-1.5 max-h-44 overflow-y-auto">
                      {matches.map((s) => (
                        <button
                          key={s}
                          onClick={() => { onChange(s); setOpen(false); }}
                          className={`block w-full rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-[var(--surface-2)] ${value === s ? "text-[var(--brand-red)]" : ""}`}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  ) : null;
                })()}
              </>
            )}
            {active && (
              <button onClick={() => { onChange(""); setOpen(false); }} className="mt-1.5 w-full px-2 py-1 text-left text-xs text-muted hover:text-[var(--brand-red)]">
                Clear
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
