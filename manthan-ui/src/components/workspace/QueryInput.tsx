import { useState, useRef, useCallback, useEffect } from "react";
import { Send, Loader2 } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { queryStream } from "@/api/agent";
import { cn } from "@/lib/utils";

export function QueryInput() {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const phase = useAgentStore((s) => s.phase);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const { sessionId, activeDatasetId, addQuery } = useSessionStore();
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);

  const busy = phase !== "idle" && phase !== "done" && phase !== "error";

  // Auto-focus on mount and dataset change
  useEffect(() => {
    if (activeDatasetId && !busy) {
      inputRef.current?.focus();
    }
  }, [activeDatasetId, busy]);

  // Cmd+K global shortcut to focus
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
      pushEvent({
        type: "error",
        message: e instanceof Error ? e.message : "Connection failed",
        recoverable: false,
      });
    }
  }, [value, activeDatasetId, busy, sessionId, pushEvent, reset, addQuery]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="px-6 py-3 border-t border-border">
      <div
        className={cn(
          "flex items-end gap-3 rounded-lg border border-border bg-surface-0 px-4 py-3",
          "transition-all duration-200",
          "focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--color-accent-soft)]",
          busy && "opacity-60",
        )}
      >
        {activeDs && (
          <span className="shrink-0 text-xs font-medium text-accent bg-accent-soft px-2 py-1 rounded mb-0.5">
            {activeDs.name}
          </span>
        )}
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
            "flex-1 bg-transparent text-sm text-text-primary",
            "placeholder:text-text-tertiary resize-none outline-none",
            "leading-relaxed min-h-[24px] max-h-[120px]",
          )}
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <button
          onClick={send}
          disabled={!value.trim() || !activeDatasetId || busy}
          aria-label={busy ? "Analysis in progress" : "Send query"}
          className={cn(
            "shrink-0 w-8 h-8 flex items-center justify-center rounded-md",
            "transition-all duration-150",
            "focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1",
            value.trim() && activeDatasetId && !busy
              ? "bg-accent text-accent-text hover:bg-accent-hover hover:scale-105 active:scale-95"
              : "text-text-tertiary",
          )}
        >
          {busy ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Send size={15} />
          )}
        </button>
      </div>
      {activeDatasetId && !busy && (
        <p className="text-[11px] text-text-tertiary mt-1.5 pl-1">
          <kbd className="px-1 py-0.5 rounded bg-surface-2 text-[10px] font-mono">⌘K</kbd> to focus · <kbd className="px-1 py-0.5 rounded bg-surface-2 text-[10px] font-mono">Enter</kbd> to send
        </p>
      )}
    </div>
  );
}
