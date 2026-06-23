"use client";

import { useState } from "react";
import { login, setToken } from "@/lib/api";

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const [username, setUsername] = useState("Admin@talentrupt.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(username, password);
      setToken(res.token);
      onAuthed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div
            className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl"
            style={{ background: "var(--grad-navy)", boxShadow: "0 10px 30px rgba(11,53,89,0.5)" }}
          >
            <span className="font-heading text-2xl font-bold text-[var(--brand-red)]">TR</span>
          </div>
          <h1 className="font-heading text-2xl font-semibold">Talentrupt AI</h1>
          <p className="mt-1 text-sm text-muted">Your internal marketing department</p>
        </div>

        <form onSubmit={submit} className="card space-y-4 p-6">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Email</label>
            <input
              type="email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="field"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-[var(--brand-red)]/10 px-3 py-2 text-xs text-[var(--brand-red)]">
              {error}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
