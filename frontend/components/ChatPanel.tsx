"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthGate";
import { useChat } from "./ChatProvider";
import { AssetCard } from "./AssetCard";
import { MyraAvatar } from "./MyraLogo";
import { ReplyActions } from "./ReplyActions";
import { UserMessage } from "./UserMessage";
import { RefineChips } from "./RefineChips";
import { GenerationsGallery } from "./GenerationsGallery";
import { ImageLightbox } from "./ImageLightbox";
import { Markdown } from "./Markdown";
import { useAtMentions, AtMenu, type AtCommand } from "@/lib/atMentions";

// Popular starter tasks — an icon + a title/subtitle, matching the reference empty-state design. `prompt`
// is what gets sent when the card is tapped (unchanged behaviour).
type Suggestion = {
  icon: "image" | "deck" | "pdf" | "people";
  title: string;
  subtitle: string;
  prompt: string;
  color: string;
  tint: string;
};
const SUGGESTIONS: Suggestion[] = [
  { icon: "image", title: "Create an image", subtitle: "for a data-driven hiring post", color: "#ff7a52", tint: "rgba(255,122,82,0.16)", prompt: "Create an image for a data-driven hiring post" },
  { icon: "deck", title: "Build a pitch deck", subtitle: "for staffing agencies", color: "#3b82f6", tint: "rgba(59,130,246,0.14)", prompt: "Build a pitch deck for staffing agencies" },
  { icon: "pdf", title: "Make a one-pager PDF", subtitle: "on our RPO services", color: "#22a45d", tint: "rgba(34,164,93,0.15)", prompt: "Make a one-pager PDF on our RPO services" },
  { icon: "people", title: "Find 5 US healthcare", subtitle: "staffing agencies for RPO", color: "#8b7ef0", tint: "rgba(139,126,240,0.16)", prompt: "Find 5 US healthcare staffing agencies for RPO" },
];

function TaskIcon({ name, color }: { name: Suggestion["icon"]; color: string }) {
  const p = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (name === "image") return (<svg {...p}><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>);
  if (name === "deck") return (<svg {...p}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 20h20M9 16v4M15 16v4" /></svg>);
  if (name === "pdf") return (<svg {...p}><path d="M6 2h9l5 5v15H6zM14 2v6h6" /></svg>);
  return (<svg {...p}><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></svg>);
}

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
    stop,
    attach,
    removeAttachment,
    editMessage,
    regenerate,
    newChat,
    openConversation,
    deleteConversation,
  } = useChat();
  const [input, setInput] = useState("");
  const [tab, setTab] = useState<"chat" | "generations">("chat");
  const [attPreview, setAttPreview] = useState<{ url: string; name: string } | null>(null); // attachment lightbox
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
                className={`mb-0.5 flex w-full items-center gap-2 rounded-lg px-3 py-2 pr-8 text-left text-sm transition ${
                  conversationId === c.id
                    ? "bg-[var(--brand-navy)] text-cream"
                    : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
                }`}
                title={c.title}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-80"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" /></svg>
                <span className="min-w-0 flex-1 truncate">{c.title}</span>
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
        <header className="flex items-center gap-3 border-b border-[var(--border)] px-6 py-2.5">
          <button
            onClick={newChat}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground md:hidden"
          >
            New chat
          </button>
          <div className="ml-auto flex shrink-0 rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium">
            <button
              onClick={() => setTab("chat")}
              className={`rounded-md px-3 py-1.5 transition ${tab === "chat" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              Chat
            </button>
            <button
              onClick={() => setTab("generations")}
              className={`rounded-md px-3 py-1.5 transition ${tab === "generations" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              Your generations
            </button>
          </div>
        </header>

        {tab === "generations" ? (
          <GenerationsGallery />
        ) : (
        <>
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
                <div className="mx-auto mt-8 mb-3 flex items-center justify-center gap-1.5 text-xs font-medium text-muted">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" className="text-[var(--brand-red)]"><path d="M12 2l1.9 5.8L20 9.7l-5 3.6L16.8 20 12 16.3 7.2 20 9 13.3l-5-3.6 6.1-1.9z" /></svg>
                  Popular tasks
                </div>
                <div className="mx-auto grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s.prompt}
                      onClick={() => submit(s.prompt)}
                      className="group flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 text-left transition hover:border-[var(--brand-red)] hover:shadow-[var(--shadow-card)]"
                    >
                      <span
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                        style={{ background: s.tint }}
                      >
                        <TaskIcon name={s.icon} color={s.color} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-heading text-sm font-semibold text-foreground">{s.title}</span>
                        <span className="block truncate text-xs text-muted">{s.subtitle}</span>
                      </span>
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--border)] text-muted transition group-hover:border-[var(--brand-red)] group-hover:text-[var(--brand-red)]">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => {
              if (m.role === "user") {
                return (
                  <UserMessage
                    key={i}
                    content={m.content}
                    attachments={m.attachments}
                    displayName={displayName}
                    busy={busy}
                    onEdit={(text) => editMessage(i, text)}
                    onPreviewAttachment={setAttPreview}
                  />
                );
              }
              const img = m.assets?.find((a) => a.type === "image") || null;
              // A person/employee post drives the AI-portrait engine, so offer look-oriented refine chips.
              const isPersonPost =
                !!img && ((img.meta?.kind as string) === "team" ||
                  (img.body?.kind as string) === "team" || !!img.body?.person);
              return (
                <div key={i} className="flex items-start gap-2.5">
                  <MyraAvatar />
                  <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
                    {(m.content || m.pending) && (
                      <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm shadow-sm">
                        {m.content ? <Markdown content={m.content} /> : <Dots />}
                      </div>
                    )}
                    {m.chips && m.chips.length > 0 && !busy && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.chips.map((c) => (
                          <button
                            key={c}
                            onClick={() => submit(c)}
                            className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
                          >
                            {c}
                          </button>
                        ))}
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
                        onRegenerate={(() => {
                          for (let k = i - 1; k >= 0; k--) {
                            if (messages[k].role === "user" && messages[k].content) {
                              const prompt = messages[k].content;
                              return () => submit(prompt); // re-run the same prompt for a fresh result
                            }
                          }
                          return undefined;
                        })()}
                        regenerating={busy}
                      />
                    )}
                    {!m.pending && img && i === messages.length - 1 && (
                      <RefineChips onPick={submit} disabled={busy} kind={isPersonPost ? "person" : "image"} />
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
                  placeholder="Ask anything, or describe what to create…  (type / to create, @ for teammates)"
                  className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted"
                />
                {!busy && messages.some((m) => m.role === "user") && (
                  <button
                    onClick={regenerate}
                    disabled={attaching}
                    className="shrink-0 rounded-lg p-2 text-muted transition hover:bg-[var(--surface-2)] hover:text-[var(--brand-red)] disabled:opacity-50"
                    aria-label="Regenerate last request"
                    title="Regenerate the last request from scratch"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M23 4v6h-6M1 20v-6h6" />
                      <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
                    </svg>
                  </button>
                )}
                {busy ? (
                  <button
                    onClick={stop}
                    className="btn-primary !bg-[var(--brand-red)] !px-3 !py-2"
                    aria-label="Stop generating"
                    title="Stop"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <rect x="6" y="6" width="12" height="12" rx="2.5" />
                    </svg>
                  </button>
                ) : (
                  <button
                    onClick={() => submit(input)}
                    disabled={attaching || !input.trim()}
                    className="btn-primary !px-3 !py-2"
                    aria-label="Send"
                    title={attaching ? "Finishing file upload…" : "Send"}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted">
              Enter to send · Shift+Enter for a new line · 📎 attach files for context
            </p>
          </div>
        </div>
        </>
        )}
      </div>

      {attPreview && (
        <ImageLightbox url={attPreview.url} title={attPreview.name} onClose={() => setAttPreview(null)} />
      )}
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
