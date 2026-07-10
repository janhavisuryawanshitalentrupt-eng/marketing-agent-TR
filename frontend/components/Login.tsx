"use client";

import { useState } from "react";
import { login, forgotPassword, resetPassword, setSession } from "@/lib/api";
import { MyraMark } from "./MyraLogo";

function EyeIcon({ off }: { off?: boolean }) {
  return off ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.9 5.1A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a16 16 0 0 1-3 3.8M6.1 6.1A16 16 0 0 0 2 12s3.5 7 10 7a10.4 10.4 0 0 0 4-.8" />
      <path d="M9.5 9.5a3 3 0 0 0 4.2 4.2" />
      <path d="m2 2 20 20" />
    </svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  placeholder?: string;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-muted">{label}</label>
      <div className="relative">
        <input
          type={shown ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="field pr-10"
          autoComplete={autoComplete}
          placeholder={placeholder}
        />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? "Hide password" : "Show password"}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted transition hover:text-foreground"
          tabIndex={-1}
        >
          <EyeIcon off={shown} />
        </button>
      </div>
    </div>
  );
}

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const [mode, setMode] = useState<"login" | "forgot">("login");
  const [step, setStep] = useState<"request" | "reset">("request");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  function gotoForgot() {
    setMode("forgot");
    setStep("request");
    setError("");
    setInfo("");
    setCode("");
    setNewPassword("");
    setDevCode(null);
  }

  function gotoLogin() {
    setMode("login");
    setError("");
    setInfo("");
  }

  async function doLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(email, password);
      setSession(res.token, res.role, res.username);
      onAuthed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      const res = await forgotPassword(email);
      setInfo(res.message);
      setDevCode(res.dev_code ?? null);
      setStep("reset");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send a reset code");
    } finally {
      setLoading(false);
    }
  }

  async function doReset(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await resetPassword(email, code.trim(), newPassword);
      setSession(res.token, res.role, res.username); // reset signs you straight in
      onAuthed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <MyraMark wordmark className="mx-auto mb-3 h-24 w-24" />
          <p className="mt-1 text-sm text-muted">Your internal marketing department</p>
        </div>

        {error && (
          <p className="mb-3 rounded-lg bg-[var(--brand-red)]/10 px-3 py-2 text-xs text-[var(--brand-red)]">
            {error}
          </p>
        )}
        {info && (
          <p className="mb-3 rounded-lg bg-[var(--brand-navy)]/10 px-3 py-2 text-xs text-foreground">
            {info}
            {devCode && (
              <>
                {" "}
                <span className="font-semibold">Code: {devCode}</span>
              </>
            )}
          </p>
        )}

        {mode === "login" && (
          <form onSubmit={doLogin} className="card space-y-4 p-6">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field"
                autoComplete="username"
              />
            </div>
            <PasswordField
              label="Password"
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
            />
            <div className="flex justify-end">
              <button
                type="button"
                onClick={gotoForgot}
                className="text-xs text-muted transition hover:text-[var(--brand-red)]"
              >
                Forgot password?
              </button>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        {mode === "forgot" && step === "request" && (
          <form onSubmit={requestCode} className="card space-y-4 p-6">
            <p className="text-sm text-muted">
              Enter your account email and we&apos;ll send a reset code.
            </p>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field"
                autoComplete="username"
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? "Sending…" : "Send reset code"}
            </button>
            <button
              type="button"
              onClick={gotoLogin}
              className="w-full text-center text-xs text-muted transition hover:text-foreground"
            >
              Back to sign in
            </button>
          </form>
        )}

        {mode === "forgot" && step === "reset" && (
          <form onSubmit={doReset} className="card space-y-4 p-6">
            <p className="text-sm text-muted">Enter the code sent to {email} and choose a new password.</p>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted">Reset code</label>
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="field tracking-widest"
                placeholder="6-digit code"
                autoComplete="one-time-code"
              />
            </div>
            <PasswordField
              label="New password"
              value={newPassword}
              onChange={setNewPassword}
              autoComplete="new-password"
              placeholder="At least 6 characters"
            />
            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5">
              {loading ? "Resetting…" : "Reset & sign in"}
            </button>
            <button
              type="button"
              onClick={gotoLogin}
              className="w-full text-center text-xs text-muted transition hover:text-foreground"
            >
              Back to sign in
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
