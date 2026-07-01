"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthGate";
import { useChat } from "./ChatProvider";
import { AssetCard } from "./AssetCard";
import { Avatar } from "./Avatar";
import { MyraAvatar } from "./MyraLogo";
import { ReplyActions } from "./ReplyActions";
import { RefineChips } from "./RefineChips";
import { Markdown } from "./Markdown";
import { useAtMentions, AtMenu, type AtCommand } from "@/lib/atMentions";

const SUGGESTIONS = [
  "Find 5 US healthcare staffing agencies ready for RPO support",
  "Draft 3 LinkedIn captions about scaling recruiting",
  "Design an image for a data-driven hiring post",
  "What can this app do?",
];

// Chat understands the widest set of actions, so its "@" palette adds "post" and "prospects".
const CHAT_AT_COMMANDS: AtCommand[] = [
  { key: "image", label: "Create image", hint: "generate an image", insert: "Create an image of " },
  { key: "deck", label: "Create deck", hint: "slide deck", insert: "Create a slide deck about " },
  { key: "pdf", label: "Create PDF", hint: "document", insert: "Write a PDF document about " },
  { key: "post", label: "Write a post", hint: "social caption", insert: "Write a LinkedIn post about " },
  { key: "prospects", label: "Find prospects", hint: "target companies", insert: "Find prospects: " },
];

export function ChatPanel() {
  const { brand, username } = useAuth();
  const displayName = (username.split("@")[0] || "You").replace(/^\w/, (c) => c.toUpperCase());
  const {
    messages,
    status,
    busy,
    conversationId,
    conversations,
    attachments,
    attaching,
    send,
    attach,
    removeAttachment,
    newChat,
    openConversation,
    deleteConversation,
  } = useChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // "@" command palette (people from Folders + quick actions) — shared across every chat box.
  const { atMenu, showAtMenu, menuSel, setMenuSel, pickCommand, handleAtKey, onInputChange } =
    useAtMentions(input, setInput, busy, taRef, CHAT_AT_COMMANDS);

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const seen = new Set(attachments.map((a) => a.name));
    files.forEach((f) => {
      if (seen.has(f.name)) return; // skip files already attached
      seen.add(f.name);
      attach(f);
    });
    e.target.value = ""; // allow re-selecting the same file
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, status]);

  function submit(text: string) {
    if (busy || attaching) return; // a turn/upload is in flight — don't no-op-send and clear the input
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

  const empty = messages.length === 0;

  return (
    <div className="flex h-full">
      {/* Conversation history rail */}
      <div className="rail hidden w-56 shrink-0 flex-col border-r border-[var(--border)] md:flex">
        <div className="p-3">
          <button onClick={newChat} className="btn-primary w-full">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted">
            Conversations
          </div>
          {conversations.length === 0 && (
            <p className="px-2 py-2 text-xs text-muted">No conversations yet.</p>
          )}
          {conversations.map((c) => (
            <div key={c.id} className="group relative">
              <button
                onClick={() => openConversation(c.id)}
                className={`mb-0.5 block w-full truncate rounded-lg px-3 py-2 pr-8 text-left text-sm transition ${
                  conversationId === c.id
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
                  if (confirm("Delete this conversation?")) deleteConversation(c.id);
                }}
                title="Delete conversation"
                aria-label="Delete conversation"
                className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end border-b border-[var(--border)] px-6 py-2.5 md:hidden">
          <button
            onClick={newChat}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
          >
            New chat
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto w-full max-w-3xl space-y-5">
            {empty && (
              <div className="pt-10 text-center">
                <h2 className="font-heading text-2xl font-semibold">
                  How can I help with {brand?.name ?? "Talentrupt"}&apos;s marketing?
                </h2>
                <p className="mt-2 text-sm text-muted">
                  I find &amp; analyze prospects, generate images &amp; decks, search our brand library,
                  and write any copy. Attach a file and I&apos;ll use it as context.
                </p>
                <div className="mx-auto mt-8 grid max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
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
                      <div className="grid w-full max-w-2xl gap-2">
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
                      title={`${a.name} · ${a.chars.toLocaleString()} chars added to context`}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21.44 11.05l-9.19 9.19a5 5 0 01-7.07-7.07l9.19-9.19a3 3 0 014.24 4.24l-9.2 9.19a1 1 0 01-1.41-1.41l8.49-8.49" />
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
                  accept=".pdf,.txt,.md,.csv,.json,.log,.rtf,.html,.htm,.png,.jpg,.jpeg"
                />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={attaching}
                  className="shrink-0 rounded-lg p-2 text-muted transition hover:bg-[var(--surface-2)] hover:text-foreground disabled:opacity-50"
                  aria-label="Attach a file"
                  title="Attach a file"
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
                  placeholder="Ask anything, or describe what to find or create…  (type @ for people & quick actions)"
                  className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted"
                />
                <button
                  onClick={() => submit(input)}
                  disabled={busy || attaching || !input.trim()}
                  className="btn-primary !px-3 !py-2"
                  aria-label="Send"
                  title={attaching ? "Finishing file upload…" : "Send"}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                </button>
              </div>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted">
              Enter to send · Shift+Enter for a new line · 📎 attach files for context
            </p>
          </div>
        </div>
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
