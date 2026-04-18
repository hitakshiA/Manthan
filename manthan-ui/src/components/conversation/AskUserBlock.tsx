import { useState, useRef, useCallback } from "react";
import { MessageCircle, Send, Check, ArrowRight } from "lucide-react";
import type { AskUserBlock as AskUserType } from "@/types/conversation";
import { post } from "@/api/client";
import { cn } from "@/lib/utils";
import { useSmoothText } from "@/lib/smooth-text";

export function AskUserBlock({ block }: { block: AskUserType }) {
  const [selected, setSelected] = useState<string | null>(block.answer ?? null);
  const [freeText, setFreeText] = useState("");
  const [answered, setAnswered] = useState(!!block.answered);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Smooth-reveal for the analyst-email tone: the interpretation is
  // the key sentence the exec has to read and react to, so letting
  // it type in feels less like a popup and more like the agent
  // talking to them. ``why`` rides the same engine (keyed off the
  // same question id) for consistency.
  const interp = useSmoothText(block.interpretation ?? "", {
    streamKey: `ask-${block.question_id}-interp`,
    isStreaming: !answered,
    bypass: answered,
  });
  const whyLine = useSmoothText(block.why ?? "", {
    streamKey: `ask-${block.question_id}-why`,
    isStreaming: !answered,
    bypass: answered,
  });

  const submit = useCallback(async (answer: string) => {
    if (answered || submitting) return;
    setSubmitting(true);
    setSelected(answer);
    try {
      await post(`/ask_user/${block.question_id}/answer`, { answer });
    } catch { /* timeout fallback in backend */ }
    setAnswered(true);
    setSubmitting(false);
  }, [block.question_id, answered, submitting]);

  if (answered) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-faint font-body py-1">
        <Check size={12} className="text-success" />
        Answered: <span className="text-text-secondary">{selected || freeText}</span>
      </div>
    );
  }

  const hasProposal = !!block.interpretation;

  // Propose-first layout — analyst's email, not a form
  if (hasProposal) {
    return (
      <div className="rounded-xl border border-border bg-surface-raised p-4 font-body shadow-xs">
        <div className="flex items-center gap-2 text-[11px] text-text-faint font-semibold uppercase tracking-wider mb-3">
          <MessageCircle size={12} />
          Checking with you
        </div>

        {/* Working interpretation — prominent */}
        <div className="mb-3">
          <p className="text-[11px] text-text-faint mb-1">I&apos;ll read this as:</p>
          <p className="text-[15px] text-text-primary leading-relaxed">
            {interp.visibleText}
            {interp.isAnimating && (
              <span
                className="inline-block w-[2px] h-[1em] ml-[2px] align-[-2px] bg-accent animate-pulse"
                aria-hidden
              />
            )}
          </p>
        </div>

        {/* Why it matters — optional, smaller */}
        {block.why && (
          <p className="text-[12px] text-text-tertiary italic leading-relaxed mb-4 pl-3 border-l-2 border-border">
            {whyLine.visibleText}
            {whyLine.isAnimating && (
              <span
                className="inline-block w-[2px] h-[1em] ml-[2px] align-[-2px] bg-text-faint animate-pulse"
                aria-hidden
              />
            )}
          </p>
        )}

        {/* Silent-accept affordance */}
        <button
          onClick={() => submit(block.interpretation!)}
          disabled={submitting}
          className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-accent text-accent-text text-[13px] font-medium hover:bg-accent-hover disabled:opacity-50 transition-all mb-3 group"
        >
          <span>Yes, go with that</span>
          <ArrowRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
        </button>

        {/* Alternative interpretations */}
        {block.options.length > 0 && (
          <>
            <p className="text-[11px] text-text-faint mb-2">Or redirect me:</p>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {block.options.map((opt) => (
                <button
                  key={opt}
                  onClick={() => submit(opt)}
                  disabled={submitting}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-[12px] transition-all border",
                    selected === opt
                      ? "bg-accent-soft text-accent border-accent/40"
                      : "bg-surface-1 text-text-secondary border-border hover:border-border-strong hover:text-text-primary",
                  )}
                >
                  {opt}
                </button>
              ))}
            </div>
          </>
        )}

        {/* Free-text redirect */}
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && freeText.trim()) submit(freeText.trim()); }}
            placeholder="Or tell me what you&apos;re really worried about…"
            className="flex-1 px-3 py-1.5 rounded-lg text-[12px] bg-surface-1 border border-border text-text-primary placeholder:text-text-faint focus:outline-none focus:border-border-strong"
          />
          <button
            onClick={() => freeText.trim() && submit(freeText.trim())}
            disabled={!freeText.trim() || submitting}
            className="p-1.5 rounded-lg bg-text-primary text-surface-0 disabled:opacity-40 transition-opacity"
          >
            <Send size={12} />
          </button>
        </div>
      </div>
    );
  }

  // Fallback — original flat layout for ask_user calls without interpretation
  return (
    <div className="rounded-xl border border-accent/20 bg-accent-soft/30 p-4 font-body">
      <div className="flex items-center gap-2 text-xs text-accent font-semibold mb-2">
        <MessageCircle size={13} />
        Your input needed
      </div>
      <p className="text-sm text-text-primary mb-3">{block.prompt}</p>

      {block.options.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {block.options.map((opt) => (
            <button
              key={opt}
              onClick={() => submit(opt)}
              disabled={submitting}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                selected === opt
                  ? "bg-accent text-accent-text border-accent"
                  : "bg-surface-raised text-text-secondary border-border hover:border-accent/50 hover:text-text-primary",
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && freeText.trim()) submit(freeText.trim()); }}
          placeholder="Or type a custom answer..."
          className="flex-1 px-3 py-1.5 rounded-lg text-xs bg-surface-raised border border-border text-text-primary placeholder:text-text-faint focus:outline-none focus:border-accent/50"
        />
        <button
          onClick={() => freeText.trim() && submit(freeText.trim())}
          disabled={!freeText.trim() || submitting}
          className="p-1.5 rounded-lg bg-accent text-accent-text disabled:opacity-40 transition-opacity"
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  );
}
