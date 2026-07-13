"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { ApiError, clearToken, getBrand, getHealth, getMe, getRole, getToken, getUsername } from "@/lib/api";
import { MyraMark } from "./MyraLogo";
import type { Brand, Health } from "@/lib/types";
import { ChatProvider, CreateProvider } from "./ChatProvider";
import { Login } from "./Login";
import { Shell } from "./Shell";
import { ToastProvider } from "./Toast";

interface AuthState {
  brand: Brand | null;
  health: Health | null;
  role: string;
  username: string;
  logout: () => void;
  refreshHealth: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthGate");
  return ctx;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  // null = not yet determined (avoids hydration flash)
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [brand, setBrand] = useState<Brand | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  // Seed from the cached session so the nav renders correctly on first paint; /auth/me confirms it.
  const [role, setRole] = useState<string>(getRole());
  const [username, setUsername] = useState<string>(getUsername());

  const loadContext = useCallback(async () => {
    try {
      const b = await getBrand(); // authed — a 401 here means the token is invalid/expired
      setBrand(b);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        // Dead token: clear it and drop to the Login screen instead of a silent empty Shell.
        clearToken();
        setAuthed(false);
        setBrand(null);
        return;
      }
      setBrand(null); // transient/other error — keep the shell, don't force a logout
    }
    // Authoritative identity from the token (a tampered localStorage role gets corrected here).
    getMe().then((m) => { setRole(m.role); setUsername(m.username); }).catch(() => {});
    getHealth().then(setHealth).catch(() => {}); // public + non-critical
  }, []);

  useEffect(() => {
    const token = getToken();
    setAuthed(!!token);
    if (token) loadContext();
  }, [loadContext]);

  const logout = useCallback(() => {
    clearToken();
    setAuthed(false);
    setBrand(null);
    setRole("");
    setUsername("");
  }, []);

  const refreshHealth = useCallback(() => {
    getHealth().then(setHealth).catch(() => {});
  }, []);

  if (authed === null) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <MyraMark className="h-12 w-12 animate-pulse" />
        <div className="font-heading text-sm tracking-wide text-muted">Myra</div>
      </div>
    );
  }

  if (!authed) {
    return (
      <Login
        onAuthed={() => {
          setAuthed(true);
          loadContext();
        }}
      />
    );
  }

  return (
    <AuthContext.Provider value={{ brand, health, role, username, logout, refreshHealth }}>
      <ToastProvider>
        <ChatProvider>
          <CreateProvider>
            {/* Shell renders all section views (kept mounted so state survives navigation);
                the route pages render null and only drive the URL. */}
            <Shell />
            {children}
          </CreateProvider>
        </ChatProvider>
      </ToastProvider>
    </AuthContext.Provider>
  );
}
