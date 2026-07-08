"use client";

import { useEffect, useState } from "react";
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

export function GenerationsGallery() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState("all");
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
      load(); // restore the true list
    }
  }

  // Regenerate a fresh variation (no instruction) or refine with an instruction. Saves a NEW asset; the
  // original stays. Same underlying calls as before — only the prompt/confirm UI changed.
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
        ) : shown.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--surface-2)] text-muted">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
            </div>
            <p className="text-sm text-muted">Nothing here yet. Ask in the chat to generate an image, deck or PDF.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((a) => (
              <div key={a.id} className="group relative">
                <AssetCard asset={a} />
                {/* Actions: always visible on touch; hover-reveal on desktop (sm+). */}
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
              </div>
            ))}
          </div>
        )}
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
