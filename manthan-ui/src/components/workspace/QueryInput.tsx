import { useState, useRef, useCallback, useEffect } from "react";
import { Send, Loader2, Sparkles } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { queryStream } from "@/api/agent";
import { cn } from "@/lib/utils";

interface Props {
  variant?: "hero" | "compact";
}

export function QueryInput({ variant = "compact" }: Props) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const phase = useAgentStore((s) => s.phase);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const { sessionId, activeDatasetId, addQuery } = useSessionStore();
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);

  const busy = phase !== "idle" && phase !== "done" && phase !== "error";
  const isHero = variant === "hero";

  useEffect(() => {
    if (activeDatasetId && !busy && isHero) {
      inputRef.current?.focus();
    }
  }, [activeDatasetId, busy, isHero]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const send = useCallback(async () => {
    const msg = value.trim();
    if (!msg || !activeDatasetId || busy) return;
    reset();
    addQuery(msg, activeDatasetId);
    setValue("");
    try {
      await queryStream(sessionId, activeDatasetId, msg, pushEvent);
    } catch (e) {
      pushEvent({ type: "error", message: e instanceof Error ? e.message : "Connection failed", recoverable: false });
    }
  }, [value, activeDatasetId, busy, sessionId, pushEvent, reset, addQuery]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div
      className={cn(
        "rounded-2xl bg-surface-raised border border-border transition-all duration-200",
        isHero ? "shadow-input" : "shadow-xs",
        "focus-within:shadow-md focus-within:border-border-strong",
        busy && "opacity-60",
      )}
    >
      <div className={cn("flex items-end gap-3", isHero ? "px-5 py-4" : "px-4 py-2.5")}>
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            activeDatasetId
              ? "Ask a question about your data…"
              : "Select a dataset first"
          }
          aria-label="Query input"
          disabled={!activeDatasetId || busy}
          rows={1}
          className={cn(
            "flex-1 bg-transparent text-text-primary placeholder:text-text-faint resize-none outline-none leading-relaxed min-h-[24px] max-h-[120px]",
            isHero ? "text-base" : "text-sm",
          )}
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <button
          onClick={send}
          disabled={!value.trim() || !activeDatasetId || busy}
          aria-label={busy ? "Analysis in progress" : "Send query"}
          className={cn(
            "shrink-0 flex items-center justify-center rounded-xl transition-all duration-200",
            isHero ? "w-10 h-10" : "w-8 h-8",
            "focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1",
            value.trim() && activeDatasetId && !busy
              ? "bg-accent text-accent-text shadow-sm hover:bg-accent-hover hover:shadow-md hover:scale-105 active:scale-95"
              : "bg-surface-sunken text-text-faint",
          )}
        >
          {busy ? (
            <Loader2 size={isHero ? 18 : 15} className="animate-spin-slow" />
          ) : (
            <Send size={isHero ? 18 : 15} />
          )}
        </button>
      </div>

      {/* Bottom row with context */}
      {isHero && (
        <div className="flex items-center gap-3 px-5 pb-3 pt-0">
          {activeDs && (
            <span className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <Sparkles size={11} className="text-accent" />
              {activeDs.name}
            </span>
          )}
          <span className="ml-auto text-[10px] text-text-faint">
            <kbd className="px-1 py-0.5 rounded bg-surface-sunken font-mono">⌘K</kbd> to focus
          </span>
        </div>
      )}
    </div>
  );
}
