"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthGate";
import { Avatar } from "./Avatar";
import { MyraMark } from "./MyraLogo";
import { AiStatus } from "./AiStatus";
import { useToast } from "./Toast";
import { fileToAvatarDataUrl, getAvatar, setAvatar, setAvatarUser, subscribeAvatar } from "@/lib/avatar";
import { ChatPanel } from "./ChatPanel";
import { CampaignsView } from "./CampaignsView";
import { MagazineView } from "./MagazineView";
import { BusinessView } from "./BusinessView";
import { FoldersView } from "./FoldersView";
import { TasksView } from "./TasksView";
import { AnalyticsView } from "./AnalyticsView";

type NavItem = { href: string; label: string; icon: string; adminOnly?: boolean };

// Tasks & Analytics are ADMIN-ONLY — hidden for non-admin members (and their APIs are admin-gated too).
const NAV: NavItem[] = [
  { href: "/", label: "Chat", icon: "M4 4h16v12H7l-3 3V4z" },
  { href: "/campaigns", label: "Campaigns", icon: "M3 9h18M7 3v3M17 3v3M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1z" },
  { href: "/magazine", label: "Magazine", icon: "M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z" },
  { href: "/business", label: "Business Dev", icon: "M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6" },
  { href: "/folders", label: "Folders", icon: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" },
  { href: "/tasks", label: "Tasks", icon: "M9 11l3 3L20 6M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7", adminOnly: true },
  { href: "/analytics", label: "Analytics", icon: "M4 20V10M10 20V4M16 20v-7M3 20h18", adminOnly: true },
];

export function Shell() {
  const pathname = usePathname();
  const { logout, role, username } = useAuth();
  const isAdmin = role === "admin";
  const nav = NAV.filter((item) => !item.adminOnly || isAdmin);
  const displayName = (username.split("@")[0] || "User").replace(/^\w/, (c) => c.toUpperCase());
  const [theme, setTheme] = useState<"dark" | "light">("light");

  useEffect(() => {
    const saved = (typeof window !== "undefined" && localStorage.getItem("tr_theme")) as
      | "dark"
      | "light"
      | null;
    const system = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    setTheme(saved || (document.documentElement.dataset.theme as "dark" | "light") || system);
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

  // Profile photo (frontend-only, stored locally per user). A `self` <Avatar> shows it everywhere.
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [hasPhoto, setHasPhoto] = useState(false);
  useEffect(() => {
    setAvatarUser(username);
    const update = () => setHasPhoto(!!getAvatar());
    update();
    return subscribeAvatar(update);
  }, [username]);

  async function onPickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    try {
      setAvatar(await fileToAvatarDataUrl(file));
      toast("Profile photo updated", { kind: "success" });
    } catch (err) {
      toast((err as Error)?.message || "Couldn't set that photo", { kind: "error" });
    }
  }
  function removePhoto() {
    setAvatar(null);
    setViewPhoto(false);
    toast("Profile photo removed", { kind: "info" });
  }

  // Click the photo to VIEW it enlarged.
  const [viewPhoto, setViewPhoto] = useState(false);
  useEffect(() => {
    if (!viewPhoto) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setViewPhoto(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [viewPhoto]);

  // Account dropdown (avatar -> name, email, theme, sign out): close on outside-click / Escape.
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  // All four views stay MOUNTED here (in the persistent Shell), so an in-progress task
  // (a discovery, a generation, a draft) survives switching sections. The route's pathname
  // just decides which one is visible.
  const views = [
    { key: "/", active: pathname === "/" || pathname.startsWith("/create"), node: <ChatPanel /> },
    { key: "/campaigns", active: pathname.startsWith("/campaigns"), node: <CampaignsView /> },
    { key: "/magazine", active: pathname.startsWith("/magazine"), node: <MagazineView /> },
    { key: "/business", active: pathname.startsWith("/business"), node: <BusinessView /> },
    { key: "/folders", active: pathname.startsWith("/folders"), node: <FoldersView /> },
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
      {/* Top nav bar (glassmorphism) */}
      <header className="glass sticky top-0 z-40 flex shrink-0 items-center gap-3 border-b px-5 py-2.5">
        {/* Brand (left) */}
        <div className="flex flex-1 items-center gap-3">
          <MyraMark className="h-9 w-9 shrink-0" />
          <div className="hidden leading-tight sm:block">
            <div className="font-heading text-sm font-semibold">Myra</div>
            <div className="text-[10px] uppercase tracking-wider text-muted">Marketing Agent</div>
          </div>
        </div>

        {/* Primary nav (centered, horizontal — pages stay on top) */}
        <nav className="flex items-center justify-center gap-1">
          {nav.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  active
                    ? "text-white"
                    : "text-foreground hover:bg-[var(--surface-2)]"
                }`}
                style={active ? { background: "var(--grad-navy)" } : undefined}
              >
                <svg
                  width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
                  className={active ? "text-white" : ""}
                >
                  <path d={item.icon} />
                </svg>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right: theme toggle + AI status + account menu */}
        <div className="flex flex-1 items-center justify-end gap-3">
          {/* Animated theme switch — sun (light) / moon (dark), 300ms slide */}
          <button
            onClick={toggleTheme}
            role="switch"
            aria-checked={theme === "dark"}
            aria-label="Toggle dark mode"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            className="relative inline-flex h-7 w-[52px] shrink-0 items-center rounded-full border border-[var(--border)] bg-[var(--surface-2)] transition-colors duration-300"
          >
            <svg className="pointer-events-none absolute left-[7px] h-3.5 w-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4" /></svg>
            <svg className="pointer-events-none absolute right-[7px] h-3.5 w-3.5 text-[var(--brand-coral)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" /></svg>
            <span
              className="absolute h-5 w-5 rounded-full shadow-md transition-transform duration-300 ease-in-out"
              style={{ background: theme === "dark" ? "var(--grad-red)" : "#ffffff", transform: theme === "dark" ? "translateX(27px)" : "translateX(3px)" }}
            />
          </button>
          <AiStatus />
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Account menu"
              className="rounded-full transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]"
            >
              <Avatar name={displayName} size={34} self />
            </button>
            {/* Hidden picker shared by the camera badge + "Change photo" item. */}
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPickPhoto} />
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg"
              >
                <div className="flex items-center gap-3 border-b border-[var(--border)] px-3 py-3">
                  {/* Click the avatar to VIEW the photo (or add one if none); the camera badge changes it. */}
                  <div className="relative shrink-0">
                    <button
                      onClick={() => (hasPhoto ? setViewPhoto(true) : fileRef.current?.click())}
                      className={`block rounded-full transition hover:opacity-90 ${hasPhoto ? "cursor-zoom-in" : ""}`}
                      title={hasPhoto ? "View photo" : "Add photo"}
                      aria-label={hasPhoto ? "View profile photo" : "Add profile photo"}
                    >
                      <Avatar name={displayName} size={44} self />
                    </button>
                    <button
                      onClick={() => fileRef.current?.click()}
                      className="absolute -bottom-0.5 -right-0.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-[var(--surface)] bg-[var(--brand-red)] text-white transition hover:opacity-90"
                      title="Change photo"
                      aria-label="Change profile photo"
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" /><circle cx="12" cy="13" r="4" /></svg>
                    </button>
                  </div>
                  <div className="min-w-0 leading-tight">
                    <div className="truncate text-sm font-medium">{displayName}</div>
                    <div className="truncate text-[11px] text-muted">{username || ""}</div>
                  </div>
                </div>
                {hasPhoto && (
                  <button
                    role="menuitem"
                    onClick={() => setViewPhoto(true)}
                    className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></svg>
                    <span>View photo</span>
                  </button>
                )}
                <button
                  role="menuitem"
                  onClick={() => fileRef.current?.click()}
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" /><circle cx="12" cy="13" r="4" /></svg>
                  <span>{hasPhoto ? "Change photo" : "Add photo"}</span>
                </button>
                {hasPhoto && (
                  <button
                    role="menuitem"
                    onClick={removePhoto}
                    className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-[var(--brand-red)]"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6M10 11v6M14 11v6" /></svg>
                    <span>Remove photo</span>
                  </button>
                )}
                <button
                  role="menuitem"
                  onClick={toggleTheme}
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground"
                >
                  {theme === "dark" ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" /></svg>
                  )}
                  <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
                </button>
                <button
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2.5 border-t border-[var(--border)] px-3 py-2.5 text-left text-sm text-muted transition hover:bg-[var(--surface-2)] hover:text-[var(--brand-red)]"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Profile-photo viewer — click the avatar photo to see it enlarged. */}
      {viewPhoto && getAvatar() && (
        <div
          className="fixed inset-0 z-[115] flex items-center justify-center bg-black/70 p-4"
          onClick={() => setViewPhoto(false)}
        >
          <div className="relative" onClick={(e) => e.stopPropagation()}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={getAvatar()!}
              alt={`${displayName}'s profile photo`}
              className="max-h-[72vh] max-w-[82vw] rounded-2xl border border-[var(--border)] object-contain shadow-2xl"
            />
            <button
              onClick={() => setViewPhoto(false)}
              aria-label="Close photo"
              className="absolute -right-3 -top-3 flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface)] text-muted shadow-lg transition hover:text-foreground"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
      )}

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
