"use client";

import { useEffect, useState } from "react";
import { deleteAsset, getAssets, regenerateAsset } from "@/lib/api";
import type { Asset } from "@/lib/types";
import { AssetCard } from "./AssetCard";

// Everything generated across the workspace (images, decks, PDFs) — the "Your generations" gallery that
// used to live in the Create section. Self-contained: reads getAssets() directly, so it works inside Chat.
const FILTERS = [
  { key: "all", label: "All" },
  { key: "image", label: "Images" },
  { key: "deck", label: "Decks" },
  { key: "pdf", label: "Documents" },
];

export function GenerationsGallery() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState("all");
  const [working, setWorking] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    getAssets()
      .then(setAssets)
      .catch(() => {})
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, []);

  async function remove(id: number) {
    if (!confirm("Delete this generation?")) return;
    await deleteAsset(id);
    setAssets((prev) => prev.filter((a) => a.id !== id));
  }

  // Regenerate (fresh variation) or Refine (with an instruction). Saves a NEW asset; the original stays.
  async function regen(id: number, withInstruction: boolean) {
    let instruction = "";
    if (withInstruction) {
      const v = window.prompt("Describe the change (e.g. “make it punchier”, “shorten it”, “a new variation”):");
      if (v == null) return;
      instruction = v.trim();
    }
    setWorking(id);
    try {
      await regenerateAsset(id, { instruction });
      load();
    } catch {
      /* ignore — leave the original in place */
    } finally {
      setWorking(null);
    }
  }

  const shown = filter === "all" ? assets : assets.filter((a) => a.type === filter);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-1 border-b border-[var(--border)] px-6 py-3">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-lg px-3 py-1.5 text-xs transition ${
              filter === f.key ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)]"
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={load}
          className="ml-auto rounded-lg px-3 py-1.5 text-xs text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
          title="Refresh"
        >
          Refresh
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex h-full items-center justify-center"><p className="text-sm text-muted">Loading your generations…</p></div>
        ) : shown.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted">Nothing here yet. Ask in the chat to generate an image, deck or PDF.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((a) => (
              <div key={a.id} className="group relative">
                <AssetCard asset={a} />
                <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition group-hover:opacity-100">
                  <button
                    onClick={() => regen(a.id, false)}
                    disabled={working === a.id}
                    title="Generate a fresh variation"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-foreground disabled:opacity-50"
                  >
                    {working === a.id ? "Working…" : "Regenerate"}
                  </button>
                  <button
                    onClick={() => regen(a.id, true)}
                    disabled={working === a.id}
                    title="Refine with an instruction"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-foreground disabled:opacity-50"
                  >
                    Refine
                  </button>
                  <button
                    onClick={() => remove(a.id)}
                    title="Delete"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-[var(--brand-red)]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
