"use client";

import { useEffect, useRef, useState } from "react";
import { deleteAsset, getAssets, getKnowledgeStatus, regenerateAsset, uploadBrandFile } from "@/lib/api";
import type { Asset, KnowledgeStatus } from "@/lib/types";
import { useAuth } from "./AuthGate";
import { useCreate } from "./ChatProvider";
import { AssetCard } from "./AssetCard";
import { Avatar } from "./Avatar";
import { MyraAvatar } from "./MyraLogo";
import { ReplyActions } from "./ReplyActions";
import { RefineChips } from "./RefineChips";
import { Markdown } from "./Markdown";
import { EmptyState } from "./EmptyState";
import { useAtMentions, AtMenu } from "@/lib/atMentions";

const SUGGESTIONS = [
  "Create an image for data-driven hiring",
  "Design a visual about RPO reliability",
  "Build a pitch deck for staffing agencies",
  "Make a one-pager PDF on our RPO services",
];

const FILTERS = [
  { key: "all", label: "All" },
  { key: "image", label: "Images" },
  { key: "deck", label: "Decks" },
  { key: "pdf", label: "Documents" },
];

export function CreateView() {
  const {
    messages,
    status,
    busy,
    conversationId,
    conversations,
    send,
    newChat,
    openConversation,
    deleteConversation,
    attach,
    attachments,
    removeAttachment,
    attaching,
  } = useCreate();
  const { username } = useAuth();
  const displayName = (username.split("@")[0] || "You").replace(/^\w/, (c) => c.toUpperCase());
  const [tab, setTab] = useState<"generate" | "past" | "brand">("generate");
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // "@" palette: mention a teammate from the Folders library (feature their real photo) or a quick action.
  const { atMenu, showAtMenu, menuSel, setMenuSel, pickCommand, handleAtKey, onInputChange } =
    useAtMentions(input, setInput, busy, taRef);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, status]);

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const seen = new Set(attachments.map((a) => a.name));
    files.forEach((f) => { if (!seen.has(f.name)) attach(f); }); // upload each new file
    if (fileRef.current) fileRef.current.value = ""; // allow re-picking the same file
  }

  function submit(text: string) {
    if (busy || attaching) return; // a task/upload is in flight — don't no-op-send and clear the input
    send(text);
    setInput("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (handleAtKey(e)) return; // "@" menu handled navigation/selection
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  // Start fresh (explicit) — separate from simply returning to the conversation view.
  function startNew() {
    newChat();
    setTab("generate");
  }

  // Reopen a past generation session — loads its conversation + the asset it produced.
  function open(id: number) {
    openConversation(id);
    setTab("generate");
  }

  const empty = messages.length === 0;
  const tabCls = (active: boolean) =>
    `rounded-lg px-3 py-1.5 text-xs transition ${active ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"}`;

  return (
    <div className="flex h-full">
      {/* History rail — past generation sessions (conversation + the image/deck it made) */}
      <div className="rail hidden w-56 shrink-0 flex-col border-r border-[var(--border)] md:flex">
        <div className="p-3">
          <button onClick={startNew} className="btn-primary w-full">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted">History</div>
          {conversations.length === 0 && (
            <p className="px-2 py-2 text-xs text-muted">No generations yet.</p>
          )}
          {conversations.map((c) => (
            <div key={c.id} className="group relative">
              <button
                onClick={() => open(c.id)}
                className={`mb-0.5 block w-full truncate rounded-lg px-3 py-2 pr-8 text-left text-sm transition ${
                  conversationId === c.id && tab === "generate"
                    ? "bg-[var(--brand-navy)] text-cream"
                    : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
                }`}
                title={c.title}
              >
                {c.title}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Delete this generation session?")) deleteConversation(c.id);
                }}
                title="Delete from history"
                aria-label="Delete from history"
                className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-end border-b border-[var(--border)] px-6 py-2.5">
        <div className="flex items-center gap-1">
          <button onClick={() => setTab("generate")} className={tabCls(tab === "generate")}>
            Generate
          </button>
          <button onClick={() => setTab("past")} className={tabCls(tab === "past")}>
            Your past generations
          </button>
          <button onClick={() => setTab("brand")} className={tabCls(tab === "brand")}>
            Brand kit
          </button>
          <button
            onClick={startNew}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground md:hidden"
          >
            New
          </button>
        </div>
      </header>

      {tab === "brand" ? (
        <BrandKitPanel />
      ) : tab === "past" ? (
        <PastGenerations />
      ) : (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto w-full max-w-3xl space-y-5">
              {empty && (
                <div className="pt-6">
                  <EmptyState
                    title="What should we design?"
                    subtitle="On-brand images and presentations, ready to download."
                    icon={
                      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 5h16v14H4zM4 14l4-4 4 4 3-3 5 5" />
                      </svg>
                    }
                  >
                    <div className="mx-auto grid max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
                      {SUGGESTIONS.map((s) => (
                        <button
                          key={s}
                          onClick={() => submit(s)}
                          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-left text-sm text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </EmptyState>
                </div>
              )}

              {messages.map((m, i) => {
                if (m.role === "user") {
                  return (
                    <div key={i} className="flex items-start justify-end gap-2.5">
                      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-[var(--brand-navy)] px-4 py-3 text-sm leading-relaxed text-cream">
                        {m.content}
                      </div>
                      <Avatar name={displayName} size={30} />
                    </div>
                  );
                }
                const img = m.assets?.find((a) => a.type === "image") || null;
                return (
                  <div key={i} className="flex items-start gap-2.5">
                    <MyraAvatar />
                    <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
                      {(m.content || m.pending) && (
                        <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm shadow-sm">
                          {m.content ? <Markdown content={m.content} /> : <Dots />}
                        </div>
                      )}
                      {m.assets && m.assets.length > 0 && (
                        <div className="grid w-full max-w-2xl gap-2 sm:grid-cols-2">
                          {m.assets.map((a, j) => (
                            <AssetCard key={`${a.type}-${a.id}-${j}`} asset={a} />
                          ))}
                        </div>
                      )}
                      {m.content && !m.pending && (
                        <ReplyActions
                          text={m.content}
                          downloadUrl={img?.file_url}
                          downloadName={(img?.file_url || "").split("/").pop() || undefined}
                        />
                      )}
                      {m.chips && m.chips.length > 0 && i === messages.length - 1 && (
                        <div className="flex max-w-2xl flex-wrap gap-1.5">
                          {m.chips.map((c, j) => (
                            <button
                              key={`${i}-${j}`}
                              type="button"
                              disabled={busy}
                              onClick={() => submit(c)}
                              className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-50"
                            >
                              {c}
                            </button>
                          ))}
                        </div>
                      )}
                      {!m.pending && img && i === messages.length - 1 && (
                        <RefineChips onPick={submit} disabled={busy} />
                      )}
                    </div>
                  </div>
                );
              })}

              {status && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-2 px-4 text-xs text-muted">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
                    {status}…
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-[var(--border)] px-6 py-4">
            <div className="mx-auto w-full max-w-3xl">
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 focus-within:border-[var(--brand-red)]">
                {(attachments.length > 0 || attaching) && (
                  <div className="flex flex-wrap gap-1.5 px-1 pb-2">
                    {attachments.map((a) => (
                      <span
                        key={a.id}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-[11px]"
                        title={a.kind === "image" ? `${a.name} · photo (I'll use this exact face)` : a.name}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                          {a.kind === "image" ? (
                            <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></>
                          ) : (
                            <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" />
                          )}
                        </svg>
                        <span className="max-w-[160px] truncate">{a.name}</span>
                        <button
                          onClick={() => removeAttachment(a.id)}
                          className="text-muted hover:text-[var(--brand-red)]"
                          aria-label={`Remove ${a.name}`}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                        </button>
                      </span>
                    ))}
                    {attaching && (
                      <span className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-[11px] text-muted">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
                        Reading file…
                      </span>
                    )}
                  </div>
                )}
                <div className="relative flex items-end gap-2">
                  {showAtMenu && (
                    <AtMenu atMenu={atMenu} menuSel={menuSel} setMenuSel={setMenuSel} pickCommand={pickCommand} />
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    onChange={onPickFiles}
                    className="hidden"
                    accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.md,.csv,.json"
                  />
                  <button
                    onClick={() => fileRef.current?.click()}
                    disabled={attaching}
                    className="shrink-0 rounded-lg p-2 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground disabled:opacity-50"
                    aria-label="Attach a photo"
                    title="Attach an employee's photo, then tell me their name"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" />
                    </svg>
                  </button>
                  <textarea
                    ref={taRef}
                    value={input}
                    onChange={(e) => { setInput(e.target.value); onInputChange(); }}
                    onKeyDown={onKeyDown}
                    rows={1}
                    placeholder="Describe the image(s) or presentation… or type @ to feature a teammate"
                    className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted"
                  />
                  <button
                    onClick={() => submit(input)}
                    disabled={busy || attaching || !input.trim()}
                    className="btn-primary !px-3 !py-2"
                    aria-label="Send"
                    title={attaching ? "Finishing upload…" : "Send"}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                    </svg>
                  </button>
                </div>
              </div>
              <p className="mt-2 text-center text-[11px] text-muted">
                Attach an employee&apos;s photo + name them to feature their real face — or just describe an image/deck.
              </p>
            </div>
          </div>
        </>
      )}
      </div>
    </div>
  );
}

function PastGenerations() {
  // Read the create task's live state so this tab reflects a generation that's still running
  // in the background (the task itself runs in the provider, not here — switching tabs never
  // interrupts it). We just surface progress + pull in the result when it lands.
  const { busy, status } = useCreate();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState("all");
  const wasBusy = useRef(busy);

  const load = () =>
    getAssets()
      .then((a) => setAssets(a.filter((x) => ["image", "deck", "pdf"].includes(x.type))))
      .catch(() => {});

  useEffect(() => {
    load();
  }, []);

  // When a background generation finishes (busy true -> false), refresh so the new asset
  // appears here live — no manual page refresh needed.
  useEffect(() => {
    if (wasBusy.current && !busy) load();
    wasBusy.current = busy;
  }, [busy]);

  const [working, setWorking] = useState<number | null>(null);

  async function remove(id: number) {
    if (!confirm("Delete this generation?")) return;
    await deleteAsset(id);
    setAssets((prev) => prev.filter((a) => a.id !== id));
  }

  // Regenerate (fresh variation) or Refine (with an instruction). Saves a NEW asset; original kept.
  async function regen(id: number, withInstruction: boolean) {
    let instruction = "";
    if (withInstruction) {
      const v = window.prompt("Describe the change (e.g. “make it punchier”, “shorten it”, “a new variation”):");
      if (v == null) return; // cancelled
      instruction = v.trim();
    }
    setWorking(id);
    try {
      await regenerateAsset(id, { instruction });
      await load();
    } catch {
      /* ignore — leave the original in place */
    } finally {
      setWorking(null);
    }
  }

  const shown = filter === "all" ? assets : assets.filter((a) => a.type === filter);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {busy && (
        <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--surface-2)] px-6 py-2 text-xs text-muted">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
          {status ? `${status}…` : "Working on your request…"} It&apos;ll appear here when it&apos;s ready.
        </div>
      )}
      <div className="flex gap-1 border-b border-[var(--border)] px-6 py-3">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-lg px-3 py-1.5 text-xs transition ${filter === f.key ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)]"}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {shown.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted">
              {busy
                ? "Your new generation will appear here as soon as it's ready."
                : "Nothing here yet. Generate an image or a deck."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((a) => (
              <div key={a.id} className="group relative">
                <AssetCard asset={a} />
                <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition group-hover:opacity-100">
                  <button
                    onClick={() => regen(a.id, false)}
                    disabled={working === a.id}
                    title="Generate a fresh variation"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-foreground disabled:opacity-50"
                  >
                    {working === a.id ? "Working…" : "Regenerate"}
                  </button>
                  <button
                    onClick={() => regen(a.id, true)}
                    disabled={working === a.id}
                    title="Refine with an instruction"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-foreground disabled:opacity-50"
                  >
                    Refine
                  </button>
                  <button
                    onClick={() => remove(a.id)}
                    title="Delete"
                    className="rounded-md bg-[var(--background)]/85 px-2 py-1 text-[10px] text-muted transition hover:text-[var(--brand-red)]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function BrandKitPanel() {
  const [st, setSt] = useState<KnowledgeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => getKnowledgeStatus().then(setSt).catch(() => {});
  useEffect(() => { load(); }, []);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setBusy(true);
    setNote("");
    let ok = 0;
    for (const f of files) {
      try {
        await uploadBrandFile(f);
        ok++;
      } catch (err) {
        setNote(`⚠️ ${(err as Error).message}`);
      }
    }
    await load();
    setBusy(false);
    if (ok) setNote(`Added ${ok} file${ok === 1 ? "" : "s"} to the brand library.`);
  }

  const folders = st?.by_folder ?? {};
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto w-full max-w-2xl">
        <h2 className="font-heading text-lg font-semibold">Brand library</h2>
        <p className="mt-1 text-sm text-muted">
          Add brand assets (PDFs, images, text). They&apos;re embedded and used to ground generated
          copy, images, and decks — so new content sounds and looks more like Talentrupt.
        </p>
        <div className="mt-4 rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] p-6 text-center">
          <input
            ref={fileRef}
            type="file"
            multiple
            onChange={onPick}
            className="hidden"
            accept=".pdf,.png,.jpg,.jpeg,.txt,.md,.csv,.json,.html,.htm,.rtf"
          />
          <button onClick={() => fileRef.current?.click()} disabled={busy} className="btn-primary mx-auto disabled:opacity-50">
            {busy ? "Uploading…" : "Upload brand files"}
          </button>
          <p className="mt-2 text-[11px] text-muted">PDF, image, or text · up to 25 MB each</p>
          {note && <p className="mt-2 text-xs text-muted">{note}</p>}
        </div>
        {st && (
          <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wide text-muted">Indexed library</span>
              <button onClick={load} className="text-[11px] text-muted hover:text-foreground">Refresh</button>
            </div>
            <div className="flex flex-wrap gap-4 text-muted">
              <span><span className="font-medium text-foreground">{st.source_files}</span> files</span>
              <span><span className="font-medium text-foreground">{st.brand_chunks}</span> chunks</span>
              <span>vision {st.vision_enabled ? "on" : "off"}</span>
            </div>
            {Object.keys(folders).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {Object.entries(folders).map(([f, n]) => (
                  <span key={f} className="chip bg-[var(--surface-2)]">{f}: {n}</span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Dots() {
  return (
    <span className="inline-flex gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" />
    </span>
  );
}
