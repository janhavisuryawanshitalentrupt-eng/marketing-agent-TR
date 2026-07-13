"use client";

import { useEffect } from "react";

// Reusable in-app image lightbox — opens a preview in THE SAME tab (a modal overlay), never a new browser
// tab. Click the backdrop or press Escape to close. Mirrors AssetCard's MediaPreviewModal so every image
// preview in the app looks and behaves the same.
export function ImageLightbox({
  url,
  title,
  onClose,
}: {
  url: string;
  title?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[92vh] w-auto max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-2.5">
          <span className="min-w-0 truncate font-heading text-sm font-semibold">{title || "Attachment"}</span>
          <button
            onClick={onClose}
            type="button"
            aria-label="Close preview"
            className="rounded-lg p-1.5 text-muted transition hover:text-foreground"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="flex items-center justify-center overflow-auto bg-[var(--surface-2)] p-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt={title || "attachment"} className="max-h-[78vh] w-auto rounded-lg" />
        </div>
      </div>
    </div>
  );
}
