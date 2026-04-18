import { useCallback } from "react";
import { ArrowUpRight } from "lucide-react";
import type { FollowUpChipsBlock } from "@/types/conversation";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useUIStore } from "@/stores/ui-store";
import { queryStream } from "@/api/agent";

/**
 * Three exec-voice follow-up questions rendered at the end of an analysis.
 * Tapping a chip fires the next query in the same session — turning
 * one-shot answers into a continuation.
 */
export function FollowUpChips({ block }: { block: FollowUpChipsBlock }) {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const addUserMessage = useAgentStore((s) => s.addUserMessage);
  const phase = useAgentStore((s) => s.phase);
  const setArtifactOpen = useUIStore((s) => s.setArtifactOpen);
  const setExpandedVisual = useUIStore((s) => s.setExpandedVisual);

  const busy = phase !== "idle" && phase !== "done" && phase !== "error";

  const runChip = useCallback(async (q: string) => {
    if (!activeDatasetId || busy) return;
    // Close any open side-panel view so the new work gets the stage.
    setArtifactOpen(false);
    setExpandedVisual(null);
    addQuery(q, activeDatasetId);
    addUserMessage(q);
    try {
      await queryStream(sessionId, activeDatasetId, q, pushEvent);
    } catch (e) {
      pushEvent({
        type: "error",
        message: e instanceof Error ? e.message : "Failed",
        recoverable: false,
      });
    }
  }, [activeDatasetId, sessionId, busy, addQuery, addUserMessage, pushEvent, setArtifactOpen, setExpandedVisual]);

  if (!block.chips.length) return null;

  return (
    <div className="my-3">
      <p className="text-[11px] text-text-faint uppercase tracking-wider font-medium mb-2 px-1">
        What to look at next
      </p>
      <div className="flex flex-col gap-1.5">
        {block.chips.map((chip, i) => (
          <button
            key={i}
            onClick={() => runChip(chip)}
            disabled={busy}
            className="group w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg bg-surface-raised border border-border hover:border-border-strong hover:bg-surface-1 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="text-[13px] text-text-secondary group-hover:text-text-primary font-body">
              {chip}
            </span>
            <ArrowUpRight
              size={13}
              className="text-text-faint group-hover:text-accent group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all shrink-0"
            />
          </button>
        ))}
      </div>
    </div>
  );
}
