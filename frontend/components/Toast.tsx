"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type ToastKind = "success" | "error" | "info";
interface ToastAction {
  label: string;
  onClick: () => void;
}
interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  action?: ToastAction;
}
interface ToastApi {
  toast: (
    message: string,
    opts?: { kind?: ToastKind; action?: ToastAction; duration?: number },
  ) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** App-wide toast notifications. Purely presentational — never changes any generation/API flow. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  // Safe no-op if used outside the provider (so a component can't crash on a missing provider).
  return ctx ?? { toast: () => {} };
}

const ACCENT: Record<ToastKind, string> = {
  success: "#1E7A46",
  error: "var(--brand-red)",
  info: "var(--brand-navy)",
};

function Icon({ kind }: { kind: ToastKind }) {
  const common = {
    width: 16, height: 16, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
  };
  if (kind === "success") return (<svg {...common}><path d="M20 6L9 17l-5-5" /></svg>);
  if (kind === "error") return (<svg {...common}><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>);
  return (<svg {...common}><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg>);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const remove = useCallback((id: number) => {
    setItems((x) => x.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback<ToastApi["toast"]>(
    (message, opts = {}) => {
      const id = ++idRef.current;
      const kind = opts.kind ?? "info";
      setItems((x) => [...x, { id, kind, message, action: opts.action }]);
      const dur = opts.duration ?? (opts.action ? 6000 : 3500);
      window.setTimeout(() => remove(id), dur);
    },
    [remove],
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-[120] flex w-full max-w-[92vw] -translate-x-1/2 flex-col items-center gap-2 sm:max-w-md">
        {items.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex w-full items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] py-2.5 pl-3 pr-2.5 shadow-lg"
            style={{ borderLeft: `4px solid ${ACCENT[t.kind]}`, animation: "tr-toast-in .18s ease-out" }}
            role="status"
          >
            <span style={{ color: ACCENT[t.kind] }}><Icon kind={t.kind} /></span>
            <span className="min-w-0 flex-1 text-sm">{t.message}</span>
            {t.action && (
              <button
                onClick={() => { t.action!.onClick(); remove(t.id); }}
                className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-[var(--brand-red)] transition hover:bg-[var(--surface-2)]"
              >
                {t.action.label}
              </button>
            )}
            <button
              onClick={() => remove(t.id)}
              aria-label="Dismiss"
              className="shrink-0 rounded-lg p-1 text-muted transition hover:text-foreground"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
