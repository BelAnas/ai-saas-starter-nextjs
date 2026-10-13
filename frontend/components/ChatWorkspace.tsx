"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, streamChat } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { AccountUsage, Conversation, Message, Quota, User } from "@/lib/types";
import { AppHeader } from "./AppHeader";
import { UsageMeter } from "./UsageMeter";

type Bubble = {
  key: string;
  role: "user" | "assistant";
  content: string;
  status: Message["status"] | "streaming";
};
type Notice = { kind: "limit" | "wait" | "error"; text: string };

const SUGGESTIONS = [
  "Write a product description for a hand-thrown ceramic mug",
  "Reply to a customer whose parcel is three days late",
  "Write an FAQ entry about our returns policy",
];

const toBubble = (m: Message): Bubble => ({ key: `m${m.id}`, role: m.role, content: m.content, status: m.status });

const fetchQuota = () =>
  api<AccountUsage>("/api/account/usage").then((usage) => usage.quota).catch(() => null);

export function ChatWorkspace({ user }: { user: User }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [quota, setQuota] = useState<Quota | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null);
  const router = useRouter();
  const abortRef = useRef<AbortController | null>(null);
  const sequence = useRef(0); // gives the not-yet-saved bubbles a stable React key
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const refreshQuota = () => fetchQuota().then((q) => q && setQuota(q));

  useEffect(() => {
    api<Conversation[]>("/api/conversations").then(setConversations).catch(() => undefined);
    void fetchQuota().then((q) => q && setQuota(q));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [bubbles]);

  /** Change the answer that is being written (always the last bubble). */
  const updateLast = (change: (bubble: Bubble) => Bubble | null) =>
    setBubbles((prev) => {
      const last = prev[prev.length - 1];
      if (!last) return prev;
      const next = change(last);
      return next ? [...prev.slice(0, -1), next] : prev.slice(0, -1);
    });

  async function openConversation(id: number) {
    if (streaming) return;
    setNotice(null);
    const detail = await api<{ messages: Message[] }>(`/api/conversations/${id}`);
    setActiveId(id);
    setBubbles(detail.messages.map(toBubble));
  }

  function newChat() {
    if (streaming) return;
    setActiveId(null);
    setBubbles([]);
    setNotice(null);
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;
    setNotice(null);
    setInput("");
    setStreaming(true);
    const stamp = (sequence.current += 1);
    // Show the question and an empty answer at once; the answer fills in as events arrive.
    setBubbles((prev) => [
      ...prev,
      { key: `u${stamp}`, role: "user", content: message, status: "complete" },
      { key: `a${stamp}`, role: "assistant", content: "", status: "streaming" },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        { message, conversation_id: activeId },
        {
          onMeta: (meta) => {
            setActiveId(meta.conversation_id);
            const now = new Date().toISOString();
            setConversations((prev) => {
              const known = prev.find((c) => c.id === meta.conversation_id);
              const entry = known
                ? { ...known, updated_at: now }
                : { id: meta.conversation_id, title: meta.title, created_at: now, updated_at: now };
              return [entry, ...prev.filter((c) => c.id !== meta.conversation_id)];
            });
          },
          onDelta: (piece) => updateLast((b) => ({ ...b, content: b.content + piece })),
          onDone: (end) => {
            updateLast((b) => ({ ...b, status: "complete" }));
            if (end.quota) setQuota(end.quota);
          },
          onError: (end) => {
            updateLast((b) => (b.content ? { ...b, status: "error" } : null));
            setNotice({ kind: "error", text: end.detail ?? "The model provider failed." });
            if (end.quota) setQuota(end.quota);
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) {
        // Stop button: keep what arrived. The server saves the same partial text.
        updateLast((b) => (b.content ? { ...b, status: "stopped" } : null));
        setTimeout(() => void refreshQuota(), 400);
      } else {
        // Nothing was accepted: take the two optimistic bubbles away and give the text back.
        setBubbles((prev) => prev.slice(0, -2));
        setInput(message);
        if (err instanceof ApiError && err.status === 429) {
          // Only a daily limit is worth an upgrade hint; a burst limit clears by itself.
          setNotice({ kind: err.body.code === "burst" ? "wait" : "limit", text: err.message });
          if (err.body.quota) setQuota(err.body.quota as Quota);
        } else if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
        } else {
          setNotice({ kind: "error", text: err instanceof Error ? err.message : "The request failed." });
        }
      }
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  }

  async function saveTitle() {
    if (!editing) return;
    const title = editing.title.trim();
    setEditing(null);
    if (!title) return;
    const saved = await api<Conversation>(`/api/conversations/${editing.id}`, { method: "PATCH", json: { title } });
    setConversations((prev) => prev.map((c) => (c.id === saved.id ? { ...c, title: saved.title } : c)));
  }

  async function remove(id: number) {
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) newChat();
  }

  const limitReached = quota !== null && quota.messages_used >= quota.messages_limit;

  return (
    <div className="flex h-screen flex-col">
      <AppHeader user={user}>
        <UsageMeter quota={quota} />
      </AppHeader>
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 flex-col border-r border-line bg-panel md:flex">
          <div className="p-3">
            <button onClick={newChat} className="w-full rounded-md border border-line px-3 py-2 text-sm font-medium hover:bg-surface">
              + New conversation
            </button>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" data-testid="conversation-list">
            {conversations.length === 0 && <li className="px-2 py-3 text-sm text-muted">No saved conversations yet.</li>}
            {conversations.map((c) => (
              <li key={c.id} data-testid="conversation-item"
                className={`group flex items-center gap-1 rounded-md px-2 ${c.id === activeId ? "bg-accent-soft" : "hover:bg-surface"}`}>
                {editing?.id === c.id ? (
                  <input
                    autoFocus value={editing.title} maxLength={120} aria-label="Conversation title"
                    onChange={(e) => setEditing({ id: c.id, title: e.target.value })}
                    onBlur={saveTitle}
                    onKeyDown={(e) => { if (e.key === "Enter") void saveTitle(); if (e.key === "Escape") setEditing(null); }}
                    className="my-1 w-full rounded border border-accent bg-panel px-2 py-1 text-sm outline-none"
                  />
                ) : (
                  <>
                    <button onClick={() => void openConversation(c.id)} className="min-w-0 flex-1 truncate py-2 text-left text-sm" title={c.title}>
                      {c.title}
                    </button>
                    <button onClick={() => setEditing({ id: c.id, title: c.title })} aria-label="Rename conversation"
                      className="rounded px-1 text-xs text-muted hidden hover:text-ink group-focus-within:inline group-hover:inline">
                      Rename
                    </button>
                    <button onClick={() => void remove(c.id)} aria-label="Delete conversation"
                      className="rounded px-1 text-xs text-muted hidden hover:text-danger group-focus-within:inline group-hover:inline">
                      Delete
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
              {bubbles.length === 0 && (
                <div className="py-16 text-center">
                  <h1 className="text-2xl font-semibold">What do you need to write today?</h1>
                  <p className="mt-2 text-muted">Pick an example or type your own request.</p>
                  <div className="mt-6 flex flex-col items-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button key={s} onClick={() => void send(s)} disabled={streaming}
                        className="rounded-full border border-line bg-panel px-4 py-2 text-sm hover:border-accent">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {bubbles.map((b) => (
                <div key={b.key} className={b.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div data-testid={`message-${b.role}`} data-status={b.status}
                    className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
                      b.role === "user" ? "bg-accent text-white" : "border border-line bg-panel"}`}>
                    <span className={b.status === "streaming" ? "streaming-caret" : ""}>{b.content}</span>
                    {b.status === "stopped" && <p className="mt-2 text-xs text-muted">Stopped. The partial answer was saved.</p>}
                    {b.status === "error" && <p className="mt-2 text-xs text-danger">The answer was cut short by an error.</p>}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>

          <div className="border-t border-line bg-panel">
            <div className="mx-auto max-w-3xl px-4 py-3">
              {notice && (
                <div role="alert" data-testid="notice"
                  className={`mb-3 rounded-md px-3 py-2 text-sm ${notice.kind === "error" ? "bg-red-50 text-danger" : "bg-warn-soft text-warn"}`}>
                  {notice.text}
                  {notice.kind === "limit" && quota && (
                    <> Your allowance resets at {formatTime(quota.resets_at)}. An administrator can move you to the Pro plan.</>
                  )}
                </div>
              )}
              <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
                <textarea
                  data-testid="composer" value={input} rows={2} maxLength={4000}
                  placeholder={limitReached ? "Daily limit reached" : "Describe what you need. Enter sends, Shift+Enter adds a line."}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); }
                  }}
                  className="min-h-[52px] flex-1 resize-none rounded-xl border border-line bg-surface px-3 py-2 outline-none focus:border-accent"
                />
                {streaming ? (
                  <button type="button" data-testid="stop" onClick={() => abortRef.current?.abort()}
                    className="h-[52px] rounded-xl border border-line px-5 font-medium hover:bg-surface">
                    Stop
                  </button>
                ) : (
                  <button type="submit" data-testid="send" disabled={!input.trim()}
                    className="h-[52px] rounded-xl bg-accent px-5 font-medium text-white hover:opacity-90 disabled:opacity-50">
                    Send
                  </button>
                )}
              </form>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
