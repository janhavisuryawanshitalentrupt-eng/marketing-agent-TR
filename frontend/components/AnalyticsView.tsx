"use client";

import { useEffect, useState } from "react";
import { getAnalyticsSummary } from "@/lib/api";
import type { AnalyticsSummary } from "@/lib/types";

const PIPELINE = ["new", "contacted", "replied", "meeting"];

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="card lift p-4">
      <div className={`font-heading text-2xl font-semibold ${accent ?? ""}`}>{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-muted">{label}</div>
    </div>
  );
}

function Bars({ rows, color }: { rows: { label: string; count: number }[]; color: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-32 shrink-0 truncate text-xs capitalize text-muted">{r.label}</span>
          <div className="h-4 flex-1 overflow-hidden rounded bg-[var(--surface-2)]">
            {/* A chart library could replace these CSS bars later; kept dependency-free for v1. */}
            <div className="h-full rounded" style={{ width: `${(r.count / max) * 100}%`, background: color }} />
          </div>
          <span className="w-8 shrink-0 text-right text-xs font-medium">{r.count}</span>
        </div>
      ))}
    </div>
  );
}

export function AnalyticsView() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [err, setErr] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => {
    setErr(false);
    setRefreshing(true);
    getAnalyticsSummary()
      .then(setData)
      .catch(() => setErr(true))
      .finally(() => setRefreshing(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-end border-b border-[var(--border)] px-6 py-2.5">
        <button onClick={load} disabled={refreshing} className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-60">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={refreshing ? "animate-spin" : ""}>
            <path d="M21 12a9 9 0 11-2.64-6.36M21 3v6h-6" />
          </svg>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto w-full max-w-4xl">
          {err ? (
            <p className="py-8 text-center text-sm text-muted">Couldn&apos;t load analytics. <button onClick={load} className="text-[var(--brand-red)] hover:underline">Retry</button></p>
          ) : !data ? (
            <p className="py-8 text-center text-sm text-muted">Loading…</p>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Prospects" value={data.opportunities.total} />
                <Stat label="Saved ★" value={data.opportunities.saved} accent="text-[var(--brand-red)]" />
                <Stat label="Outreach sent" value={data.outreach.sent} />
                <Stat label="Replies" value={data.outreach.replied} accent="text-emerald-300" />
                <Stat label="Campaigns" value={data.campaigns.planning} />
                <Stat label="Active clients" value={data.campaigns.active_clients} />
                <Stat label="Tasks due/overdue" value={`${data.tasks.due_soon}/${data.tasks.overdue}`} accent={data.tasks.overdue ? "text-amber-300" : ""} />
                <Stat label="Assets" value={Object.values(data.assets.by_type).reduce((a, b) => a + b, 0)} />
              </div>

              <div className="card lift p-4">
                <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-muted">Pipeline funnel</h3>
                <Bars
                  rows={PIPELINE.map((s) => ({ label: s, count: data.opportunities.by_status[s] || 0 }))}
                  color="var(--grad-navy)"
                />
              </div>

              {data.opportunities.by_sector.length > 0 && (
                <div className="card lift p-4">
                  <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-muted">Prospects by sector</h3>
                  <Bars rows={data.opportunities.by_sector.map((s) => ({ label: s.sector, count: s.count }))} color="var(--brand-red)" />
                </div>
              )}

              {Object.keys(data.assets.by_type).length > 0 && (
                <div className="card lift p-4">
                  <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-muted">Generated assets by type</h3>
                  <Bars rows={Object.entries(data.assets.by_type).map(([t, n]) => ({ label: t, count: n }))} color="var(--brand-coral)" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
