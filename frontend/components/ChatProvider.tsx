"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  deleteConversation as deleteConversationApi,
  getConversations,
  getMessages,
  streamChat,
  uploadAttachment,
} from "@/lib/api";
import type { Asset, Attachment, ChatMessage, Conversation } from "@/lib/types";

export interface ChatState {
  messages: ChatMessage[];
  status: string;
  busy: boolean;
  conversationId: number | null;
  conversations: Conversation[];
  attachments: Attachment[];
  attaching: boolean;
  send: (text: string) => void;
  attach: (file: File) => Promise<void>;
  removeAttachment: (id: number) => void;
  newChat: () => void;
  openConversation: (id: number) => void;
  deleteConversation: (id: number) => void;
}

/**
 * Build a chat store bound to a specific backend endpoint + conversation kind.
 * Used twice: Chat (assistant) and Create (generation). Mounted in AuthGate so
 * both survive tab switches.
 */
export function makeChatStore(endpoint: string, kind: string) {
  const Ctx = createContext<ChatState | null>(null);

  function Provider({ children }: { children: React.ReactNode }) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [status, setStatus] = useState("");
    const [busy, setBusy] = useState(false);
    const [conversationId, setConversationId] = useState<number | null>(null);
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const [inFlight, setInFlight] = useState(0); // count of uploads in progress
    const attaching = inFlight > 0;

    // Tie a stream to the turn that started it: aborting + bumping the generation makes any
    // in-flight callbacks no-op, so switching conversations mid-stream can't corrupt the new view.
    const streamRef = useRef<AbortController | null>(null);
    const genRef = useRef(0);
    const cancelStream = useCallback(() => {
      streamRef.current?.abort();
      streamRef.current = null;
      genRef.current += 1;
    }, []);

    const refresh = useCallback(() => {
      getConversations(kind).then(setConversations).catch(() => {});
    }, []);

    useEffect(() => {
      refresh();
    }, [refresh]);

    const send = useCallback(
      async (text: string) => {
        const trimmed = text.trim();
        if (!trimmed || busy || attaching) return;
        // Claim this turn: any earlier stream is superseded; stale callbacks below will no-op.
        const ac = new AbortController();
        streamRef.current = ac;
        const myGen = (genRef.current += 1);
        const live = () => genRef.current === myGen;
        setBusy(true);
        setStatus("");
        setMessages((m) => [
          ...m,
          { role: "user", content: trimmed },
          { role: "assistant", content: "", pending: true },
        ]);
        let gotAsset = false; // keep a staged photo until it's actually used in a generated asset

        try {
        await streamChat(
          trimmed,
          conversationId,
          {
            onMeta: (meta) => { if (live()) setConversationId((id) => id ?? meta.conversation_id); },
            onStatus: (t) => { if (live()) setStatus(t); },
            onToken: (tok) => {
              if (!live()) return;
              setMessages((m) => {
                const last = m[m.length - 1];
                if (last?.role !== "assistant") return m;
                return [...m.slice(0, -1), { ...last, content: last.content + tok }];
              });
            },
            onAsset: (asset: Asset) => {
              if (!live()) return;
              gotAsset = true;
              setMessages((m) => {
                const last = m[m.length - 1];
                if (last?.role !== "assistant") return m;
                return [
                  ...m.slice(0, -1),
                  { ...last, assets: [...(last.assets ?? []), asset] },
                ];
              });
            },
            onChips: (items) => {
              // Tappable quick-pick replies to show under the agent's question; clear typing state.
              if (!live()) return;
              setStatus("");
              setMessages((m) => {
                const last = m[m.length - 1];
                if (last?.role !== "assistant") return m;
                return [...m.slice(0, -1), { ...last, chips: items, pending: false }];
              });
            },
            onDone: (final) => {
              if (!live()) return;
              setStatus("");
              setMessages((m) => {
                const last = m[m.length - 1];
                if (!last) return m;
                return [
                  ...m.slice(0, -1),
                  { ...last, content: final || last.content, pending: false },
                ];
              });
            },
            onError: (err) => {
              if (!live()) return;
              setStatus("");
              setMessages((m) => {
                const last = m[m.length - 1];
                if (last?.role !== "assistant") return m;
                // Keep any text already streamed (mid-stream drop) and append the error.
                const content = last.content ? `${last.content}\n\n⚠️ ${err}` : `⚠️ ${err}`;
                return [...m.slice(0, -1), { ...last, content, pending: false }];
              });
            },
          },
          endpoint,
          attachments.map((a) => ({ name: a.name, text: a.text, id: a.id, kind: a.kind })),
          ac.signal,
        );
        } catch (e) {
          if (!live()) return; // superseded by a newer turn — don't touch the new view
          // Last-resort guard: streamChat surfaces all real stream/transport errors via onError
          // (and `finally` below clears busy/pending), so this only fires on an unexpected
          // synchronous throw. Preserve any partial reply if it ever does.
          setMessages((m) => {
            const last = m[m.length - 1];
            if (last?.role !== "assistant") return m;
            return [
              ...m.slice(0, -1),
              {
                ...last,
                content: last.content || `⚠️ ${(e as Error).message || "Connection failed"}`,
                pending: false,
              },
            ];
          });
        } finally {
          // Only clean up if this is still the live turn. If the user switched/opened/deleted a
          // conversation mid-stream, that handler already reset busy/status/attachments for the NEW
          // view — running this cleanup would clobber it (wipe staged files, flip busy off).
          if (live()) {
            setStatus("");
            setBusy(false);
            // Keep a staged photo until it's actually used in a post — so an intake question or a
            // chat reply in between doesn't lose it. Other files clear after their one turn.
            if (gotAsset || !attachments.some((a) => a.kind === "image")) setAttachments([]);
            refresh();
          }
        }
      },
      [busy, attaching, conversationId, refresh, attachments],
    );

    const attach = useCallback(async (file: File) => {
      setInFlight((n) => n + 1);
      setStatus("");
      try {
        const meta = await uploadAttachment(file);
        setAttachments((a) =>
          a.some((x) => x.name === meta.filename)
            ? a
            : [...a, { id: meta.id, name: meta.filename, text: meta.text, kind: meta.kind, chars: meta.chars }],
        );
      } catch (e) {
        setStatus(`⚠️ ${(e as Error).message}`);
      } finally {
        setInFlight((n) => n - 1);
      }
    }, []);

    const removeAttachment = useCallback(
      (id: number) => setAttachments((a) => a.filter((x) => x.id !== id)),
      [],
    );

    const newChat = useCallback(() => {
      cancelStream(); // stop any in-flight stream so its tokens don't land on the new chat
      setMessages([]);
      setConversationId(null);
      setStatus("");
      setBusy(false);
      setAttachments([]);
    }, [cancelStream]);

    const deleteConversation = useCallback(
      async (id: number) => {
        try {
          await deleteConversationApi(id);
        } catch {
          /* ignore — still drop it from the list */
        }
        setConversations((cs) => cs.filter((c) => c.id !== id));
        if (id === conversationId) {
          cancelStream();
          setConversationId(null);
          setMessages([]);
          setStatus("");
          setBusy(false);
          setAttachments([]);
        }
      },
      [conversationId, cancelStream],
    );

    const openConversation = useCallback((id: number) => {
      cancelStream(); // stop any in-flight stream before loading the opened conversation
      setStatus("");
      setBusy(false);
      setConversationId(id);
      setAttachments([]);
      getMessages(id)
        .then((msgs) =>
          setMessages(
            msgs.map((m) => ({
              role: m.role,
              content: m.content,
              assets: m.assets ?? [],
            })),
          ),
        )
        .catch(() => {});
    }, [cancelStream]);

    return (
      <Ctx.Provider
        value={{
          messages, status, busy, conversationId, conversations,
          attachments, attaching, send, attach, removeAttachment, newChat, openConversation,
          deleteConversation,
        }}
      >
        {children}
      </Ctx.Provider>
    );
  }

  function useStore(): ChatState {
    const c = useContext(Ctx);
    if (!c) throw new Error("chat store used outside its provider");
    return c;
  }

  return { Provider, useStore };
}

// Two stores: the assistant (Chat) and the generator (Create).
export const ChatStore = makeChatStore("/api/chat/stream", "chat");
export const CreateStore = makeChatStore("/api/create/stream", "create");

export const ChatProvider = ChatStore.Provider;
export const useChat = ChatStore.useStore;
export const CreateProvider = CreateStore.Provider;
export const useCreate = CreateStore.useStore;
