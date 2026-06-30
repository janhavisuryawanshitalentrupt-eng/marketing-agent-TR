"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthGate";
import { Avatar } from "./Avatar";
import { MyraMark } from "./MyraLogo";
import { ChatPanel } from "./ChatPanel";
import { CreateView } from "./CreateView";
import { CampaignsView } from "./CampaignsView";
import { BusinessView } from "./BusinessView";
import { TasksView } from "./TasksView";
import { AnalyticsView } from "./AnalyticsView";

type NavItem = { href: string; label: string; icon: string; adminOnly?: boolean };

// Tasks & Analytics are ADMIN-ONLY — hidden for non-admin members (and their APIs are admin-gated too).
const NAV: NavItem[] = [
  { href: "/", label: "Chat", icon: "M4 4h16v12H7l-3 3V4z" },
  { href: "/create", label: "Create", icon: "M4 5h16v14H4zM4 14l4-4 4 4 3-3 5 5" },
  { href: "/campaigns", label: "Campaigns", icon: "M3 9h18M7 3v3M17 3v3M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" },
  { href: "/business", label: "Business Dev", icon: "M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6" },
  { href: "/tasks", label: "Tasks", icon: "M9 11l3 3L20 6M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7", adminOnly: true },
  { href: "/analytics", label: "Analytics", icon: "M4 20V10M10 20V4M16 20v-7M3 20h18", adminOnly: true },
];

export function Shell() {
  const pathname = usePathname();
  const { logout, role, username } = useAuth();
  const isAdmin = role === "admin";
  const nav = NAV.filter((item) => !item.adminOnly || isAdmin);
  const displayName = (username.split("@")[0] || "User").replace(/^\w/, (c) => c.toUpperCase());
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = (typeof window !== "undefined" && localStorage.getItem("tr_theme")) as
      | "dark"
      | "light"
      | null;
    setTheme(saved || (document.documentElement.dataset.theme as "dark" | "light") || "dark");
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("tr_theme", next);
    } catch {
      /* ignore */
    }
  }

  // All four views stay MOUNTED here (in the persistent Shell), so an in-progress task
  // (a discovery, a generation, a draft) survives switching sections. The route's pathname
  // just decides which one is visible.
  const views = [
    { key: "/", active: pathname === "/", node: <ChatPanel /> },
    { key: "/create", active: pathname.startsWith("/create"), node: <CreateView /> },
    { key: "/campaigns", active: pathname.startsWith("/campaigns"), node: <CampaignsView /> },
    { key: "/business", active: pathname.startsWith("/business"), node: <BusinessView /> },
    // Tasks & Analytics are mounted only for admins; a member who deep-links here sees the fallback.
    ...(isAdmin
      ? [
          { key: "/tasks", active: pathname.startsWith("/tasks"), node: <TasksView /> },
          { key: "/analytics", active: pathname.startsWith("/analytics"), node: <AnalyticsView /> },
        ]
      : []),
  ];

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Top nav bar */}
      <header className="flex shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)]/70 px-5 py-2.5 backdrop-blur">
        {/* Brand (left) */}
        <div className="flex flex-1 items-center gap-3">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-2xl bg-white p-1.5"
            style={{ boxShadow: "0 6px 16px rgba(11,53,89,0.25)" }}
          >
            <MyraMark className="h-full w-full" />
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="font-heading text-sm font-semibold">Myra</div>
            <div className="text-[10px] uppercase tracking-wider text-muted">Marketing Agent</div>
          </div>
        </div>

        {/* Primary nav (centered) */}
        <nav className="flex items-center justify-center gap-1">
          {nav.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${
                  active
                    ? "text-cream"
                    : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
                }`}
                style={active ? { background: "var(--grad-navy)" } : undefined}
              >
                <svg
                  width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
                  className={active ? "text-[var(--brand-red)]" : ""}
                >
                  <path d={item.icon} />
                </svg>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right: theme toggle + profile */}
        <div className="flex flex-1 items-center justify-end gap-1.5">
          <button
            onClick={toggleTheme}
            title="Toggle light / dark mode"
            aria-label="Toggle light / dark mode"
            className="rounded-xl p-2 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
          >
            {theme === "dark" ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" /></svg>
            )}
          </button>

          <div className="flex items-center gap-2.5 rounded-xl p-1.5 transition hover:bg-[var(--surface-2)]">
            <Avatar name={displayName} size={32} />
            <div className="hidden min-w-0 leading-tight lg:block">
              <div className="truncate text-sm font-medium">{displayName}</div>
              <div className="truncate text-[11px] text-muted">{username || ""}</div>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
              className="rounded-lg p-2 text-muted transition hover:bg-[var(--surface-3)] hover:text-[var(--brand-red)]"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Main — all views stay mounted; only the active one is shown */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {views.map((v) => (
          <div key={v.key} className={v.active ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
            {v.node}
          </div>
        ))}
        {!views.some((v) => v.active) && (
          <div className="flex flex-1 items-center justify-center text-sm text-muted">
            This section isn&apos;t available for your account.
          </div>
        )}
      </main>
    </div>
  );
}
