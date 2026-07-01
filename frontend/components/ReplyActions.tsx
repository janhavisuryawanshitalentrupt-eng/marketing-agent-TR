"use client";

import { useState } from "react";

/**
 * Compact action row under an assistant reply (copy + quick feedback) — the controls shown in the
 * chat design. Copy is real (writes the reply text to the clipboard); the thumbs are a local visual
 * acknowledgement only (no backend). Kept intentionally light so it doesn't compete with the message.
 */
export function ReplyActions({ text }: { text: string }) {
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

  const btn = "rounded-md p-1.5 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground";
  return (
    <div className="flex items-center gap-0.5 pl-1">
      <button
        type="button"
        onClick={() => setVote((v) => (v === "up" ? null : "up"))}
        aria-label="Good response"
        title="Good response"
        className={`${btn} ${vote === "up" ? "text-[var(--brand-red)] hover:text-[var(--brand-red)]" : ""}`}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M7 10v11M2 13v6a2 2 0 002 2h13.4a2 2 0 002-1.6l1.4-7A2 2 0 0018.8 10H13V4a2 2 0 00-2-2L7 10z" /></svg>
      </button>
      <button
        type="button"
        onClick={() => setVote((v) => (v === "down" ? null : "down"))}
        aria-label="Bad response"
        title="Bad response"
        className={`${btn} ${vote === "down" ? "text-[var(--brand-red)] hover:text-[var(--brand-red)]" : ""}`}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M17 14V3M22 11V5a2 2 0 00-2-2H6.6a2 2 0 00-2 1.6l-1.4 7A2 2 0 005.2 14H11v6a2 2 0 002 2l4-8z" /></svg>
      </button>
      <button type="button" onClick={copy} aria-label={copied ? "Copied" : "Copy reply"} title={copied ? "Copied" : "Copy"} className={btn}>
        {copied ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
        )}
      </button>
    </div>
  );
}
