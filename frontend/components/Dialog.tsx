"use client";

import { useEffect, useRef, useState } from "react";

/** Styled in-app dialogs replacing native window.confirm / window.prompt. Presentational only —
 * the caller keeps full control of the action, so no existing workflow changes. */
function Overlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-2xl"
        style={{ animation: "tr-toast-in .16s ease-out" }}
      >
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  danger = true,
  onConfirm,
  onCancel,
}: {
  title: string;
  message?: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Overlay onClose={onCancel}>
      <h3 className="font-heading text-base font-semibold">{title}</h3>
      {message && <p className="mt-1.5 text-sm text-muted">{message}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg px-3 py-1.5 text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="rounded-lg px-3 py-1.5 text-sm text-white transition hover:opacity-90"
          style={{ background: danger ? "var(--brand-red)" : "var(--brand-navy)" }}
        >
          {confirmLabel}
        </button>
      </div>
    </Overlay>
  );
}

export function PromptDialog({
  title,
  message,
  placeholder,
  confirmLabel = "Apply",
  onConfirm,
  onCancel,
}: {
  title: string;
  message?: string;
  placeholder?: string;
  confirmLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  const submit = () => onConfirm(value.trim());
  return (
    <Overlay onClose={onCancel}>
      <h3 className="font-heading text-base font-semibold">{title}</h3>
      {message && <p className="mt-1.5 text-sm text-muted">{message}</p>}
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        rows={3}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
        }}
        className="mt-3 w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-sm outline-none transition focus:border-[var(--brand-red)]"
      />
      <div className="mt-4 flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted">⌘/Ctrl + Enter</span>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg px-3 py-1.5 text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            className="rounded-lg bg-[var(--brand-navy)] px-3 py-1.5 text-sm text-cream transition hover:opacity-90"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Overlay>
  );
}
