"use client";

import { useEffect, useRef, useState } from "react";
import { Avatar } from "./Avatar";
import type { Attachment } from "@/lib/types";

/**
 * A user (input) message in the transcript — the attachments + the navy bubble + the avatar, plus a hover
 * action row with COPY and EDIT (ChatGPT-style). Editing turns the bubble into an inline textarea; saving
 * calls `onEdit` with the new text (the parent removes this turn + everything after it and re-sends, so the
 * edit re-runs). Editing is blocked while a turn is in flight.
 */
export function UserMessage({
  content,
  attachments,
  displayName,
  busy,
  onEdit,
  onPreviewAttachment,
}: {
  content: string;
  attachments?: Attachment[];
  displayName: string;
  busy: boolean;
  onEdit: (text: string) => void;
  onPreviewAttachment?: (a: { url: string; name: string }) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [copied, setCopied] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      const ta = taRef.current;
      if (ta) {
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
        ta.style.height = "auto";
        ta.style.height = `${ta.scrollHeight}px`;
      }
    }
  }, [editing]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — no-op */
    }
  }

  function startEdit() {
    setDraft(content);
    setEditing(true);
  }

  function save() {
    const t = draft.trim();
    setEditing(false);
    if (t && t !== content.trim()) onEdit(t);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      save();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setEditing(false);
    }
  }

  const iconBtn =
    "rounded-md p-1.5 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground active:scale-90";

  return (
    <div className="group flex items-start justify-end gap-2.5">
      <div className="flex max-w-[85%] min-w-0 flex-col items-end gap-1.5">
        {attachments && attachments.length > 0 && (
          <div className="flex flex-wrap justify-end gap-1.5">
            {attachments.map((a) =>
              a.previewUrl && a.kind === "image" ? (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onPreviewAttachment?.({ url: a.previewUrl!, name: a.name })}
                  title={`Open ${a.name}`}
                  aria-label={`Open ${a.name}`}
                  className="block rounded-xl"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={a.previewUrl}
                    alt={a.name}
                    className="h-24 w-24 cursor-zoom-in rounded-xl border border-[var(--border)] object-cover shadow-sm transition hover:opacity-90"
                  />
                </button>
              ) : (
                <span
                  key={a.id}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-[11px]"
                  title={a.name}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" />
                  </svg>
                  <span className="max-w-[160px] truncate">{a.name}</span>
                </span>
              ),
            )}
          </div>
        )}

        {editing ? (
          <div className="w-[min(32rem,80vw)] rounded-2xl rounded-tr-sm border border-[var(--brand-red)] bg-[var(--surface)] p-2 shadow-sm">
            <textarea
              ref={taRef}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${e.target.scrollHeight}px`;
              }}
              onKeyDown={onKeyDown}
              rows={1}
              className="max-h-60 w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed outline-none"
            />
            <div className="mt-1 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-lg px-3 py-1.5 text-xs text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={!draft.trim()}
                className="btn-primary !px-3 !py-1.5 !text-xs disabled:opacity-40"
              >
                Save &amp; send
              </button>
            </div>
          </div>
        ) : (
          content && (
            <>
              <div className="whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-[var(--brand-navy)] px-4 py-3 text-sm leading-relaxed text-cream">
                {content}
              </div>
              {/* Hover actions: copy + edit (revealed on hover / keyboard focus) */}
              <div className="flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                <button
                  type="button"
                  onClick={copy}
                  aria-label={copied ? "Copied" : "Copy message"}
                  title={copied ? "Copied" : "Copy"}
                  className={iconBtn}
                >
                  {copied ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
                  )}
                </button>
                <button
                  type="button"
                  onClick={startEdit}
                  disabled={busy}
                  aria-label="Edit message"
                  title={busy ? "Wait for the reply to finish" : "Edit"}
                  className={`${iconBtn} disabled:opacity-40`}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4 12.5-12.5z" /></svg>
                </button>
              </div>
            </>
          )
        )}
      </div>
      <Avatar name={displayName} size={30} self />
    </div>
  );
}
