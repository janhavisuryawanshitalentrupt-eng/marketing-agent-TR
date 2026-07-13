"use client";

import { useEffect, useMemo, useState } from "react";
import { deleteAsset, getAssets, regenerateAsset } from "@/lib/api";
import type { Asset } from "@/lib/types";
import { AssetCard } from "./AssetCard";
import { useToast } from "./Toast";
import { ConfirmDialog, PromptDialog } from "./Dialog";

// Everything generated across the workspace (images, decks, PDFs) — the "Your generations" gallery that
// used to live in the Create section. Self-contained: reads getAssets() directly, so it works inside Chat.
const FILTERS = [
  { key: "all", label: "All" },
  { key: "image", label: "Images" },
  { key: "deck", label: "Decks" },
  { key: "pdf", label: "Documents" },
];

type Sort = "newest" | "oldest";

/** Time for sorting/grouping; falls back to the id (assets are auto-increment) when created_at is absent. */
function assetTime(a: Asset): number {
  if (a.created_at) {
    const t = Date.parse(a.created_at);
    if (!Number.isNaN(t)) return t;
  }
  return 0;
}
function monthLabel(a: Asset): string {
  if (!a.created_at) return "Earlier";
  const d = new Date(a.created_at);
  if (Number.isNaN(d.getTime())) return "Earlier";
  return d.toLocaleString(undefined, { month: "long", year: "numeric" });
}

export function GenerationsGallery() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [working, setWorking] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState<number | null>(null);   // -> ConfirmDialog
  const [refineId, setRefineId] = useState<number | null>(null);   // -> PromptDialog
  const { toast } = useToast();

  function load() {
    setLoading(true);
    getAssets()
      .then(setAssets)
      .catch(() => {})
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  async function confirmDelete() {
    const id = deleteId;
    if (id == null) return;
    setDeleteId(null);
    setAssets((prev) => prev.filter((a) => a.id !== id)); // optimistic
    try {
      await deleteAsset(id);
      toast("Generation deleted", { kind: "success" });
    } catch {
      toast("Couldn't delete — please try again", { kind: "error" });
      load();
    }
  }

  async function regen(id: number, instruction: string) {
    setWorking(id);
    try {
      await regenerateAsset(id, { instruction });
      toast(instruction ? "Refined — new version added" : "Regenerated — new version added", { kind: "success" });
      load();
    } catch {
      toast("Generation failed — the original is unchanged", { kind: "error" });
    } finally {
      setWorking(null);
    }
  }

  // Filter -> sort (by date) -> group into months (newest month first, "Earlier" last for undated assets).
  const groups = useMemo(() => {
    const shown = filter === "all" ? assets : assets.filter((a) => a.type === filter);
    const sorted = [...shown].sort((a, b) => {
      const d = assetTime(b) - assetTime(a) || b.id - a.id; // newest first (id tiebreak)
      return sort === "newest" ? d : -d;
    });
    const out: { key: string; items: Asset[] }[] = [];
    const idx = new Map<string, number>();
    for (const a of sorted) {
      const key = monthLabel(a);
      if (!idx.has(key)) { idx.set(key, out.length); out.push({ key, items: [] }); }
      out[idx.get(key)!].items.push(a);
    }
    return out;
  }, [assets, filter, sort]);

  const total = groups.reduce((n, g) => n + g.items.length, 0);

  function ActionOverlay({ a }: { a: Asset }) {
    return (
      <div className="absolute right-2 top-2 flex gap-1 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100">
        <button
          onClick={() => regen(a.id, "")}
          disabled={working === a.id}
          title="Generate a fresh variation"
          className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted backdrop-blur-sm transition hover:text-foreground disabled:opacity-50"
        >
          {working === a.id ? "Working…" : "Regenerate"}
        </button>
        <button
          onClick={() => setRefineId(a.id)}
          disabled={working === a.id}
          title="Refine with an instruction"
          className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted backdrop-blur-sm transition hover:text-foreground disabled:opacity-50"
        >
          Refine
        </button>
        <button
          onClick={() => setDeleteId(a.id)}
          title="Delete"
          className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted backdrop-blur-sm transition hover:text-[var(--brand-red)]"
        >
          Delete
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-1 border-b border-[var(--border)] px-6 py-3">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filter === f.key ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {/* Newest / Oldest segmented sort — groups by month like a phone gallery. */}
          <div className="flex items-center rounded-lg border border-[var(--border)] p-0.5">
            {(["newest", "oldest"] as Sort[]).map((s) => (
              <button
                key={s}
                onClick={() => setSort(s)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition ${
                  sort === s ? "bg-[var(--surface-3)] text-foreground" : "text-muted hover:text-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
            title="Refresh"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-6 py-4">
          {loading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
                  <div className="skeleton h-44 w-full rounded-none" />
                  <div className="flex items-center justify-between gap-2 p-3">
                    <div className="skeleton h-3 w-1/2" />
                    <div className="skeleton h-6 w-14" />
                  </div>
                </div>
              ))}
            </div>
          ) : total === 0 ? (
            <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--surface-2)] text-muted">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
              </div>
              <p className="text-sm text-muted">Nothing here yet. Ask in the chat to generate an image, deck or PDF.</p>
            </div>
          ) : (
            groups.map((g) => (
              <section key={g.key} className="mb-6">
                {/* Sticky month header — like a phone photo gallery. */}
                <div className="sticky top-0 z-10 -mx-6 mb-3 flex items-center gap-2 bg-[var(--background)]/85 px-6 py-2 backdrop-blur-sm">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{g.key}</h3>
                  <span className="text-[11px] text-muted/70">· {g.items.length}</span>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {g.items.map((a) => (
                    <div key={a.id} className="group relative">
                      <AssetCard asset={a} />
                      <ActionOverlay a={a} />
                    </div>
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
      </div>

      {deleteId != null && (
        <ConfirmDialog
          title="Delete this generation?"
          message="This removes it from your gallery. This can't be undone."
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setDeleteId(null)}
        />
      )}
      {refineId != null && (
        <PromptDialog
          title="Refine this generation"
          message="Describe the change — the original stays, a new version is added."
          placeholder="e.g. make it punchier, use a different background, shorten it…"
          confirmLabel="Refine"
          onConfirm={(v) => {
            const id = refineId;
            setRefineId(null);
            if (id != null && v) regen(id, v);
          }}
          onCancel={() => setRefineId(null)}
        />
      )}
    </div>
  );
}
