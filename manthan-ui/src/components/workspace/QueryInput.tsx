import { useState, useRef, useCallback } from "react";
import { Send } from "lucide-react";
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
    <div className="px-6 py-4 border-b border-border">
      <div
        className={cn(
          "flex items-end gap-3 rounded-lg border border-border bg-surface-0 px-4 py-3 transition-colors duration-150",
          "focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/20",
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
              ? "Ask a question about your data..."
              : "Select a dataset first"
          }
          disabled={!activeDatasetId || busy}
          rows={1}
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary resize-none outline-none leading-relaxed min-h-[24px] max-h-[120px]"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <button
          onClick={send}
          disabled={!value.trim() || !activeDatasetId || busy}
          className={cn(
            "shrink-0 w-8 h-8 flex items-center justify-center rounded-md transition-colors duration-150",
            value.trim() && activeDatasetId && !busy
              ? "bg-accent text-accent-text hover:bg-accent-hover"
              : "text-text-tertiary",
          )}
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}
