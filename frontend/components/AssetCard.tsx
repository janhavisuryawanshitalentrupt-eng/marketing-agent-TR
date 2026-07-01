"use client";

import { useState } from "react";
import Link from "next/link";
import { downloadFile, getDeckPreview, fileUrl } from "@/lib/api";
import type { Asset } from "@/lib/types";
import type { DeckSlide } from "@/lib/api";

function dlName(asset: Asset): string {
  return (asset.file_url || "").split("/").pop() || asset.title || "download";
}

export function AssetCard({ asset }: { asset: Asset }) {
  switch (asset.type) {
    case "post":
      return <PostCard asset={asset} />;
    case "image":
      return <ImageCard asset={asset} />;
    case "video":
      return <VideoCard asset={asset} />;
    case "deck":
      return <FileCard asset={asset} label="Presentation" ext="PPTX" icon="deck" />;
    case "pdf":
      return <FileCard asset={asset} label="Document" ext="PDF" icon="pdf" />;
    case "campaign":
      return <CampaignCard asset={asset} />;
    default:
      return null;
  }
}

function EyeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-[var(--brand-navy)]/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-cream">
      {children}
    </span>
  );
}

function PostCard({ asset }: { asset: Asset }) {
  const b = asset.body as Record<string, unknown>;
  const hashtags = Array.isArray(b.hashtags) ? (b.hashtags as string[]) : [];
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
      <div className="mb-2 flex items-center gap-2">
        <Chip>{String(b.platform ?? "Post")}</Chip>
        {b.content_type ? <span className="text-[11px] text-muted">{String(b.content_type)}</span> : null}
      </div>
      <p className="font-heading text-sm font-semibold">{String(b.hook ?? asset.title)}</p>
      {b.caption ? (
        <p className="mt-1.5 whitespace-pre-wrap text-sm text-muted">{String(b.caption)}</p>
      ) : null}
      {b.cta ? (
        <p className="mt-2 text-sm text-[var(--brand-red)]">{String(b.cta)}</p>
      ) : null}
      {hashtags.length > 0 && (
        <p className="mt-2 text-xs text-muted">{hashtags.join("  ")}</p>
      )}
      {b.visual_concept ? (
        <p className="mt-2 border-t border-[var(--border)] pt-2 text-[11px] text-muted">
          Visual: {String(b.visual_concept)}
        </p>
      ) : null}
    </div>
  );
}

// In-app lightbox — images/videos open here (in the same tab) instead of a new browser tab.
function MediaPreviewModal({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const url = fileUrl(asset.file_url);
  const isVideo = asset.type === "video";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[92vh] w-auto max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-2.5">
          <span className="truncate font-heading text-sm font-semibold">{asset.title}</span>
          <div className="flex shrink-0 items-center gap-1">
            <button onClick={() => downloadFile(url, dlName(asset)).catch(() => {})} type="button" title="Download" aria-label="Download" className="rounded-lg p-1.5 text-muted transition hover:text-foreground">
              <DownloadIcon />
            </button>
            <button onClick={onClose} type="button" aria-label="Close preview" className="rounded-lg p-1.5 text-muted transition hover:text-foreground">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
        <div className="flex items-center justify-center overflow-auto bg-[var(--surface-2)] p-3">
          {isVideo ? (
            <video src={url} className="max-h-[78vh] w-auto rounded-lg" controls autoPlay loop playsInline />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={asset.title} className="max-h-[78vh] w-auto rounded-lg" />
          )}
        </div>
      </div>
    </div>
  );
}

function ImageCard({ asset }: { asset: Asset }) {
  const url = fileUrl(asset.file_url);
  const [preview, setPreview] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
      <button type="button" onClick={() => setPreview(true)} title="View" aria-label="View image" className="block w-full">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={asset.title} className="w-full max-w-sm cursor-zoom-in" />
      </button>
      <div className="flex items-center justify-between gap-2 p-3">
        <span className="min-w-0 truncate text-xs text-muted">{asset.title}</span>
        <div className="flex shrink-0 items-center gap-1">
          <button onClick={() => setPreview(true)} type="button" title="View" aria-label="View" className="rounded-lg border border-[var(--border)] p-1.5 text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
            <EyeIcon />
          </button>
          <button onClick={() => downloadFile(url, dlName(asset)).catch(() => {})} type="button" title="Download" aria-label="Download" className="rounded-lg bg-[var(--brand-navy)] p-1.5 text-cream transition hover:opacity-90">
            <DownloadIcon />
          </button>
        </div>
      </div>
      {preview && <MediaPreviewModal asset={asset} onClose={() => setPreview(false)} />}
    </div>
  );
}

function VideoCard({ asset }: { asset: Asset }) {
  const url = fileUrl(asset.file_url);
  const [preview, setPreview] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-2)]">
      <button type="button" onClick={() => setPreview(true)} title="View" aria-label="View video" className="block w-full">
        <video src={url} className="w-full max-w-sm" autoPlay loop muted playsInline />
      </button>
      <div className="flex items-center justify-between gap-2 p-3">
        <span className="min-w-0 truncate text-xs text-muted">{asset.title}</span>
        <div className="flex shrink-0 items-center gap-1">
          <button onClick={() => setPreview(true)} type="button" title="View" aria-label="View" className="rounded-lg border border-[var(--border)] p-1.5 text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
            <EyeIcon />
          </button>
          <button onClick={() => downloadFile(url, dlName(asset)).catch(() => {})} type="button" title="Download" aria-label="Download" className="rounded-lg bg-[var(--brand-navy)] p-1.5 text-cream transition hover:opacity-90">
            <DownloadIcon />
          </button>
        </div>
      </div>
      {preview && <MediaPreviewModal asset={asset} onClose={() => setPreview(false)} />}
    </div>
  );
}

function FileCard({
  asset,
  label,
  ext,
  icon,
}: {
  asset: Asset;
  label: string;
  ext: string;
  icon: "deck" | "pdf";
}) {
  const url = fileUrl(asset.file_url);
  const [slides, setSlides] = useState<DeckSlide[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function openDeckPreview() {
    setLoading(true);
    try {
      const data = await getDeckPreview(asset.file_url || "");
      setSlides(data.slides);
    } catch {
      // fallback: open the file directly
      window.open(url, "_blank", "noreferrer");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-navy)] text-cream">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            {icon === "deck" ? (
              <path d="M4 4h16v12H4zM2 20h20M9 16v4M15 16v4" />
            ) : (
              <path d="M6 2h9l5 5v15H6zM14 2v6h6" />
            )}
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Chip>{ext}</Chip>
            <span className="text-[11px] text-muted">{label}</span>
          </div>
          <p className="mt-1 truncate text-sm">{asset.title}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {ext === "PPTX" ? (
            <button
              onClick={openDeckPreview}
              disabled={loading}
              type="button"
              title="Preview slides"
              aria-label="Preview"
              className="rounded-lg border border-[var(--border)] p-2 text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-40"
            >
              {loading ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="animate-spin">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
              ) : (
                <EyeIcon />
              )}
            </button>
          ) : (
            <a href={url} target="_blank" rel="noreferrer" title="Preview" aria-label="Preview" className="rounded-lg border border-[var(--border)] p-2 text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">
              <EyeIcon />
            </a>
          )}
          <button onClick={() => downloadFile(url, dlName(asset)).catch(() => {})} type="button" title="Download" aria-label="Download" className="rounded-lg bg-[var(--brand-red)] p-2 text-white transition hover:opacity-90">
            <DownloadIcon />
          </button>
        </div>
      </div>
      {slides && (
        <SlidePreviewModal title={asset.title} slides={slides} onClose={() => setSlides(null)} />
      )}
    </>
  );
}

function SlidePreviewModal({
  title,
  slides,
  onClose,
}: {
  title: string;
  slides: DeckSlide[];
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <div className="flex items-center gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--brand-navy)]">
              <path d="M4 4h16v12H4zM2 20h20M9 16v4M15 16v4" />
            </svg>
            <span className="font-heading text-sm font-semibold">{title}</span>
            <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[10px] text-muted">{slides.length} slides</span>
          </div>
          <button onClick={onClose} type="button" aria-label="Close preview" className="rounded-lg p-1.5 text-muted transition hover:text-foreground">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        {/* Slides */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {slides.length === 0 ? (
            <p className="text-sm text-muted">No slide text extracted.</p>
          ) : (
            slides.map((s) => (
              <div key={s.slide} className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
                <div className="mb-1 flex items-center gap-2">
                  <span className="rounded-full bg-[var(--brand-navy)] px-2 py-0.5 text-[10px] text-cream">
                    Slide {s.slide}
                  </span>
                  {s.title && (
                    <span className="font-heading text-sm font-semibold truncate">{s.title}</span>
                  )}
                </div>
                {s.text && (
                  <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{s.text}</p>
                )}
                {!s.title && !s.text && (
                  <p className="text-xs text-muted italic">No text content</p>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function CampaignCard({ asset }: { asset: Asset }) {
  const b = asset.body as Record<string, unknown>;
  return (
    <Link
      href={`/campaigns?open=${asset.campaign_id ?? asset.id}`}
      className="block rounded-xl border border-[var(--brand-red)]/40 bg-[var(--surface-2)] p-4 transition hover:border-[var(--brand-red)]"
    >
      <div className="mb-1 flex items-center gap-2">
        <Chip>Campaign</Chip>
      </div>
      <p className="font-heading text-sm font-semibold">{asset.title}</p>
      {b.key_message ? (
        <p className="mt-1 text-sm text-muted">{String(b.key_message)}</p>
      ) : null}
      <p className="mt-2 text-xs text-[var(--brand-red)]">Open campaign →</p>
    </Link>
  );
}
