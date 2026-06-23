"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { deleteTask, getOpportunities, getTasks, updateTask } from "@/lib/api";
import type { BizTask } from "@/lib/types";
import { EmptyState } from "./EmptyState";

export function TasksView() {
  const [tasks, setTasks] = useState<BizTask[]>([]);
  const [companies, setCompanies] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();

  function load() {
    getTasks()
      .then(setTasks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  // All views stay mounted in the Shell, so this view never remounts on navigation. Re-fetch
  // whenever it becomes active so changes made elsewhere (e.g. Snooze/Done in Business Dev)
  // appear immediately — no manual Refresh needed.
  useEffect(() => {
    if (pathname !== "/tasks") return;
    load();
    getOpportunities()
      .then((os) => {
        const m: Record<number, string> = {};
        os.forEach((o) => (m[o.id] = o.company));
        setCompanies(m);
      })
      .catch(() => {});
  }, [pathname]);

  async function act(id: number, patch: { status?: "done"; snooze_days?: number }) {
    await updateTask(id, patch);
    load();
  }

  async function remove(id: number) {
    if (!window.confirm("Delete this follow-up task? This can't be undone.")) return;
    setTasks((prev) => prev.filter((t) => t.id !== id)); // optimistic
    try {
      await deleteTask(id);
    } catch {
      load(); // re-sync if the delete failed
    }
  }

  const startToday = new Date();
  startToday.setHours(0, 0, 0, 0);
  const endToday = new Date();
  endToday.setHours(23, 59, 59, 999);
  const due = (t: BizTask) => (t.due_at ? new Date(t.due_at).getTime() : 0);

  const pending = tasks.filter((t) => t.status !== "done");
  const done = tasks.filter((t) => t.status === "done");
  const overdue = pending.filter((t) => due(t) < startToday.getTime());
  const today = pending.filter((t) => due(t) >= startToday.getTime() && due(t) <= endToday.getTime());
  const upcoming = pending.filter((t) => due(t) > endToday.getTime());

  function Row({ t, muted }: { t: BizTask; muted?: boolean }) {
    const company = t.opportunity_id != null ? companies[t.opportunity_id] : "";
    const msg = (t.payload?.message as string) || "";
    return (
      <div className={`hover-row flex items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm ${muted ? "opacity-60" : ""}`}>
        <span className="mt-0.5 shrink-0 rounded-md bg-[var(--brand-navy)] px-2 py-0.5 text-[11px] text-cream">
          {t.due_at ? t.due_at.slice(0, 10) : "—"}
        </span>
        <div className="min-w-0 flex-1">
          <div className={`truncate ${muted ? "line-through text-muted" : ""}`}>{t.title}</div>
          {company ? (
            <Link
              href={t.opportunity_id != null ? `/business?prospect=${t.opportunity_id}` : "/business"}
              className="text-[11px] text-[var(--brand-red)] hover:underline"
            >
              {company}
            </Link>
          ) : null}
          {msg ? <p className="mt-0.5 line-clamp-2 text-[11px] text-muted">{msg}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {t.status !== "done" && (
            <>
              <button onClick={() => act(t.id, { snooze_days: 1 })} className="text-[11px] text-muted hover:text-foreground" title="Snooze 1 day">1d</button>
              <button onClick={() => act(t.id, { snooze_days: 3 })} className="text-[11px] text-muted hover:text-foreground" title="Snooze 3 days">3d</button>
              <button onClick={() => act(t.id, { snooze_days: 7 })} className="text-[11px] text-muted hover:text-foreground" title="Snooze 7 days">7d</button>
              <button onClick={() => act(t.id, { status: "done" })} className="text-[11px] text-[var(--brand-red)] hover:underline" title="Mark done">Done</button>
            </>
          )}
          <button
            onClick={() => remove(t.id)}
            className="rounded p-0.5 text-[13px] leading-none text-muted transition hover:text-[var(--brand-red)]"
            title="Delete task"
            aria-label="Delete task"
          >
            ✕
          </button>
        </div>
      </div>
    );
  }

  function Group({ title, items, accent }: { title: string; items: BizTask[]; accent?: string }) {
    if (items.length === 0) return null;
    return (
      <div className="mb-5">
        <h3 className={`mb-2 text-[11px] font-semibold uppercase tracking-wide ${accent ?? "text-muted"}`}>
          {title} ({items.length})
        </h3>
        <div className="space-y-1.5">
          {items.map((t) => <Row key={t.id} t={t} muted={t.status === "done"} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
        <div>
          <h1 className="font-heading text-base font-semibold">Tasks</h1>
          <p className="text-xs text-muted">Your follow-up reminders — overdue, today, and upcoming.</p>
        </div>
        <button onClick={load} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
          Refresh
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto w-full max-w-2xl">
          {loading ? (
            <p className="py-8 text-center text-sm text-muted">Loading…</p>
          ) : tasks.length === 0 ? (
            <EmptyState
              title="No follow-ups yet"
              subtitle="Generate outreach for a prospect in Business Dev and its follow-up reminders will appear here."
              icon={
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                </svg>
              }
            />
          ) : (
            <>
              <Group title="Overdue" items={overdue} accent="text-[var(--brand-red)]" />
              <Group title="Today" items={today} accent="text-amber-300" />
              <Group title="Upcoming" items={upcoming} />
              <Group title="Done" items={done} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
