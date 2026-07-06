"use client";

import { useState } from "react";
import { downloadFile, fileUrl } from "@/lib/api";

// Outline (default) + solid (reacted) thumb glyphs — swapping to the solid fill makes a click obvious.
const THUMB_UP_OUTLINE = "M7 10v11M2 13v6a2 2 0 002 2h13.4a2 2 0 002-1.6l1.4-7A2 2 0 0018.8 10H13V4a2 2 0 00-2-2L7 10z";
const THUMB_DOWN_OUTLINE = "M17 14V3M22 11V5a2 2 0 00-2-2H6.6a2 2 0 00-2 1.6l-1.4 7A2 2 0 005.2 14H11v6a2 2 0 002 2l4-8z";
const THUMB_UP_SOLID = "M7.493 18.75c-.425 0-.82-.236-.974-.632A7.48 7.48 0 016 15.375c0-1.75.599-3.358 1.602-4.634.151-.192.373-.309.6-.397.473-.183.89-.514 1.212-.924a9.042 9.042 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75 2.25 2.25 0 012.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H14.23c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23h-.777ZM2.331 10.977a11.969 11.969 0 00-.831 4.398 12 12 0 00.52 3.507c.26.85 1.084 1.368 1.973 1.368H4.9c.445 0 .72-.498.523-.898a8.963 8.963 0 01-.924-3.977c0-1.708.476-3.305 1.302-4.666.245-.403-.028-.959-.5-.959H4.25c-.832 0-1.612.453-1.918 1.227Z";
const THUMB_DOWN_SOLID = "M15.73 5.25h1.035A7.465 7.465 0 0118 9.375a7.465 7.465 0 01-1.235 4.125h-.148c-.806 0-1.534.446-2.031 1.08a9.04 9.04 0 01-2.861 2.4c-.723.384-1.35.956-1.653 1.715a4.498 4.498 0 00-.322 1.672V21a.75.75 0 01-.75.75 2.25 2.25 0 01-2.25-2.25c0-1.152.26-2.243.723-3.218.266-.558-.107-1.282-.725-1.282H3.622c-1.026 0-1.945-.694-2.054-1.715A12.134 12.134 0 011.5 11.25c0-2.848.992-5.464 2.649-7.521C4.537 3.247 5.136 3 5.754 3H9.77a4.5 4.5 0 011.423.23l3.114 1.04a4.5 4.5 0 001.423.23ZM21.669 13.023c.536-1.362.831-2.845.831-4.398 0-1.22-.182-2.398-.52-3.507-.26-.85-1.084-1.368-1.973-1.368H19.1c-.445 0-.72.498-.523.898.591 1.2.924 2.55.924 3.977a8.958 8.958 0 01-1.302 4.666c-.245.403.028.959.5.959h1.053c.832 0 1.612-.453 1.918-1.227Z";

function Thumb({ dir, active, onToggle }: { dir: "up" | "down"; active: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      aria-label={dir === "up" ? "Good response" : "Bad response"}
      title={dir === "up" ? "Good response" : "Bad response"}
      className={`rounded-md p-1.5 transition active:scale-90 ${
        active
          ? "text-[var(--brand-red)]"
          : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
      }`}
    >
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke={active ? "none" : "currentColor"}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={dir === "up" ? (active ? THUMB_UP_SOLID : THUMB_UP_OUTLINE) : active ? THUMB_DOWN_SOLID : THUMB_DOWN_OUTLINE} />
      </svg>
    </button>
  );
}

/**
 * Compact action row under an assistant reply — quick feedback (👍/👎), copy, regenerate (re-run the same
 * prompt), and download when the reply produced a file. The thumbs are a local reaction the user can toggle
 * on/off; copy writes the reply to the clipboard; regenerate re-runs the turn (hidden when not available or
 * while a turn is in flight); download saves the asset.
 */
export function ReplyActions({
  text,
  downloadUrl,
  downloadName,
  onRegenerate,
  regenerating,
}: {
  text: string;
  downloadUrl?: string | null;
  downloadName?: string;
  onRegenerate?: () => void;
  regenerating?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<"up" | "down" | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — no-op */
    }
  }

  const btn = "rounded-md p-1.5 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground active:scale-90";
  return (
    <div className="flex items-center gap-0.5 pl-1">
      <Thumb dir="up" active={vote === "up"} onToggle={() => setVote((v) => (v === "up" ? null : "up"))} />
      <Thumb dir="down" active={vote === "down"} onToggle={() => setVote((v) => (v === "down" ? null : "down"))} />
      <button type="button" onClick={copy} aria-label={copied ? "Copied" : "Copy reply"} title={copied ? "Copied" : "Copy"} className={btn}>
        {copied ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
        )}
      </button>
      {onRegenerate && (
        <button
          type="button"
          onClick={onRegenerate}
          disabled={regenerating}
          aria-label="Regenerate"
          title="Regenerate"
          className={`${btn} disabled:opacity-40`}
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={regenerating ? "animate-spin" : ""}
          >
            <path d="M23 4v6h-6M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
        </button>
      )}
      {downloadUrl && (
        <button
          type="button"
          onClick={() => downloadFile(fileUrl(downloadUrl), downloadName || "download").catch(() => {})}
          aria-label="Download"
          title="Download"
          className={btn}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
        </button>
      )}
    </div>
  );
}
