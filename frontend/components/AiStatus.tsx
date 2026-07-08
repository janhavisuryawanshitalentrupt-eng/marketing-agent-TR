"use client";

import { useEffect, useState } from "react";
import { getLlmHealth } from "@/lib/api";

type State = "loading" | "ok" | "paused" | "unknown";

/** A small read-only pill in the header showing whether the AI provider is responding. When OpenAI is
 * out of credits / rate-limited, the user sees "AI paused — add credits" instead of a cryptic per-turn
 * error. Polls the /api/health/llm probe; never affects generation. */
export function AiStatus() {
  const [state, setState] = useState<State>("loading");
  const [reason, setReason] = useState<string>("");

  useEffect(() => {
    let alive = true;
    async function check() {
      try {
        const h = await getLlmHealth();
        if (!alive) return;
        setState(h.ok ? "ok" : "paused");
        setReason(h.reason || "");
      } catch {
        if (alive) setState("unknown");
      }
    }
    check();
    const t = window.setInterval(check, 60_000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);

  if (state === "loading") return null;

  const cfg =
    state === "ok"
      ? { dot: "#1E7A46", label: "AI ready", title: "AI is connected and ready." }
      : state === "paused"
      ? {
          dot: "#F5A524",
          label: reason === "out_of_credits" ? "AI paused — add credits" : "AI paused",
          title:
            reason === "out_of_credits"
              ? "The OpenAI account is out of credits — generation is paused until it's topped up."
              : reason === "rate_limited"
              ? "The AI provider is rate-limiting requests — try again shortly."
              : "The AI provider isn't responding right now.",
        }
      : { dot: "#94a3b8", label: "AI status", title: "Couldn't check AI status." };

  return (
    <div
      title={cfg.title}
      className="hidden items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-[11px] text-muted md:flex"
    >
      <span className="h-2 w-2 rounded-full" style={{ background: cfg.dot }} />
      <span className="whitespace-nowrap">{cfg.label}</span>
    </div>
  );
}
