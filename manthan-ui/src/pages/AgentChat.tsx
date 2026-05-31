/**
 * AgentChat - talk to Manthan across all cases.
 *
 * Editorial form: a single column of typeset paragraphs, not chat
 * bubbles. The agent's reply is set in Spectral, the operator's prompt
 * in Geist - same way you'd typeset an interview transcript.
 */

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";

import {
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import { sendAgentChat } from "@/lib/api";

interface ChatMsg {
  role: "user" | "assistant" | "error";
  text: string;
  ts: number;
}

const SUGGESTIONS = [
  "Which cases are sitting in awaiting_approval right now?",
  "Which customers cost us the most in refunds this month?",
  "Did we fight or fold on Quill Logistics?",
  "How many cases did policy auto-resolve without a human?",
];

export default function AgentChat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setMessages((m) => [...m, { role: "user", text: trimmed, ts: Date.now() }]);
    setInput("");
    setSending(true);
    try {
      const r = await sendAgentChat(trimmed);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: r.reply, ts: Date.now() },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "error",
          text: `Something broke: ${(e as Error).message}`,
          ts: Date.now(),
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <PageBody width="narrow" className="flex flex-col min-h-[calc(100vh-3rem)]">
      <PageHeader
        eyebrow="Workspace chat"
        title="Talk to Manthan"
        meta="Cross-case questions grounded in your last twenty cases."
      />

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto -mx-2 px-2">
        {messages.length === 0 && (
          <Section eyebrow="Try">
            <ul className="space-y-1">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    onClick={() => send(s)}
                    disabled={sending}
                    className="w-full text-left py-2.5 text-[14px] italic font-display hover:opacity-90 transition-opacity"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    “{s}”
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {messages.length > 0 && (
          <div className="space-y-7 py-4">
            {messages.map((m, i) => (
              <Transcript key={i} msg={m} />
            ))}
            {sending && (
              <div
                className="text-[12px] tracking-[0.02em]"
                style={{ color: "var(--color-ink-faint)" }}
              >
                Thinking<span className="animate-pulse-dot">…</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div
        className="border-t pt-4 mt-4"
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-end gap-3 border-b pb-2"
          style={{ borderColor: "var(--color-rule)" }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask Manthan about your cases…"
            rows={1}
            disabled={sending}
            className="flex-1 bg-transparent text-[14px] outline-none resize-none py-1 max-h-32"
            style={{
              color: "var(--color-ink-strong)",
              caretColor: "var(--color-accent)",
            }}
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="h-7 w-7 inline-flex items-center justify-center shrink-0 hover:opacity-90 disabled:opacity-40"
            style={{
              background: "var(--color-ink-strong)",
              color: "var(--color-bg)",
              borderRadius: "var(--radius-xs)",
            }}
          >
            {sending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ArrowUp className="h-3.5 w-3.5" />
            )}
          </button>
        </form>
        <p
          className="mt-2 text-[10.5px] tracking-[0.02em] text-center italic font-display"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          Grounded in your case queue · powered by Gemini Flash Lite
        </p>
      </div>
    </PageBody>
  );
}

function Transcript({ msg }: { msg: ChatMsg }) {
  if (msg.role === "user") {
    return (
      <div>
        <div
          className="eyebrow mb-1.5"
          style={{ color: "var(--color-ink-faint)" }}
        >
          You
        </div>
        <p
          className="text-[14px] leading-relaxed whitespace-pre-wrap"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {msg.text}
        </p>
      </div>
    );
  }
  if (msg.role === "error") {
    return (
      <div>
        <div
          className="eyebrow mb-1.5"
          style={{ color: "var(--color-danger)" }}
        >
          Error
        </div>
        <p
          className="text-[13px] leading-relaxed"
          style={{ color: "var(--color-danger)" }}
        >
          {msg.text}
        </p>
      </div>
    );
  }
  return (
    <div>
      <div
        className="eyebrow mb-1.5"
        style={{ color: "var(--color-accent)" }}
      >
        Manthan
      </div>
      <p
        className="font-display text-[16px] leading-[1.55] whitespace-pre-wrap max-w-[72ch]"
        style={{ color: "var(--color-ink-strong)" }}
      >
        {msg.text}
      </p>
    </div>
  );
}
