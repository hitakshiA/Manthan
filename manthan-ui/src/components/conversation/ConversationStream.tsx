import { useEffect, useMemo, useRef, useState } from "react";
import { useAgentStore, getLiveThinking } from "@/stores/agent-store";
import type { ConversationBlock, ThinkingGroupBlock } from "@/types/conversation";
import { ThinkingGroup } from "./ThinkingGroup";
import { AskUserBlock } from "./AskUserBlock";
import { ArtifactCardBlock } from "./ArtifactCardBlock";
import { InlineVisualBlock } from "./InlineVisualBlock";
import { FollowUpChips } from "./FollowUpChips";
import { NarrativeBlock } from "./NarrativeBlock";
import { Check, AlertCircle, Clock, Wrench } from "lucide-react";
import { ManthanLogo } from "@/components/ManthanLogo";

/** Ladder-swapping status text — cycles through progression messages
 *  while the current tool is running so a 60s forecast fit doesn't
 *  read as a frozen "Running the analysis…" label. */
function useProgressiveStatus(
  base: string,
  ladder: string[],
  startedAt: number,
  isWorking: boolean,
): string {
  const [idx, setIdx] = useState(0);

  // Reset whenever the base text or start time changes.
  useEffect(() => {
    setIdx(0);
  }, [base, startedAt]);

  // Tick forward while we're working and still have ladder entries to show.
  // First swap fires at 3s, subsequent swaps every 4s, stays on the last.
  useEffect(() => {
    if (!isWorking || ladder.length === 0) return;
    const delay = idx === 0 ? 3000 : 4000;
    const t = window.setTimeout(() => {
      setIdx((i) => Math.min(i + 1, ladder.length));
    }, delay);
    return () => window.clearTimeout(t);
  }, [idx, isWorking, ladder.length]);

  if (idx === 0 || ladder.length === 0) return base;
  return ladder[Math.min(idx - 1, ladder.length - 1)];
}

function BlockRenderer({ block }: { block: ConversationBlock }) {
  switch (block.type) {
    case "user_message":
      return (
        <div className="flex justify-end">
          <div className="max-w-[75%] px-4 py-3 rounded-2xl bg-accent text-accent-text text-sm font-body">
            {block.text}
          </div>
        </div>
      );

    case "thinking_group":
      return <ThinkingGroup group={block} />;

    case "narrative":
      return <NarrativeBlock text={block.text} />;

    case "sql_result":
      // Raw SQL payloads are no longer surfaced at the top level — they
      // live inside the expanded thinking group now. Kept in the union
      // for backward compatibility with any cached session state.
      return null;

    case "ask_user":
      return <AskUserBlock block={block} />;

    case "artifact_card":
      return <ArtifactCardBlock block={block} />;

    case "inline_visual":
      return <InlineVisualBlock block={block} />;

    case "followup_chips":
      return <FollowUpChips block={block} />;

    case "done":
      return (
        <div className="flex items-center gap-3 py-3 text-xs text-text-tertiary font-body">
          <div className="flex items-center gap-1.5 bg-success-soft px-2 py-1 rounded-md">
            <Check size={12} className="text-success" />
            Done
          </div>
          <span className="flex items-center gap-1"><Clock size={11} />{block.elapsed_seconds.toFixed(1)}s</span>
          <span className="flex items-center gap-1"><Wrench size={11} />{block.tool_calls} tools</span>
        </div>
      );

    case "error":
      return (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-error-soft text-sm text-error font-body">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          {block.message}
        </div>
      );

    default:
      return null;
  }
}

export function ConversationStream() {
  const blocks = useAgentStore((s) => s.blocks);
  const phase = useAgentStore((s) => s.phase);
  const thinkingText = useAgentStore((s) => s.thinkingText);
  const thinkingLadder = useAgentStore((s) => s.thinkingLadder);
  const thinkingStartedAt = useAgentStore((s) => s.thinkingStartedAt);
  const liveThinkingVersion = useAgentStore((s) => s.liveThinkingVersion);
  const liveThinkingStartedAt = useAgentStore((s) => s.liveThinkingStartedAt);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Whether we should auto-follow new content. Flips false the moment
  // the user scrolls up so their reading position isn't yanked back.
  const stickToBottom = useRef(true);

  const isWorking = phase !== "idle" && phase !== "done" && phase !== "error";
  const progressiveStatus = useProgressiveStatus(
    thinkingText,
    thinkingLadder,
    thinkingStartedAt,
    isWorking,
  );

  // Live phase card — snapshot the module-level buffer whenever it
  // changes (version bump). Rendered inline so the exec sees phases
  // stream in, not a blank "Thinking…" for 6 minutes.
  const liveGroup: ThinkingGroupBlock | null = useMemo(() => {
    const steps = getLiveThinking();
    if (steps.length === 0) return null;
    const toolCalls = steps.filter((s) => s.kind === "tool_call");
    const onlyVisuals = toolCalls.length > 0 && toolCalls.every((s) => s.tool === "emit_visual");
    if (onlyVisuals) return null;
    const tools = toolCalls
      .filter((s) => s.tool !== "emit_visual")
      .map((s) => s.display_label ?? s.text)
      .filter(Boolean);
    const firstReasoning = steps.find((s) => s.kind === "reasoning");
    const head = tools[0] ?? firstReasoning?.text ?? "Working on it";
    const summary = tools.length > 1
      ? `${String(head).slice(0, 80)} and ${tools.length - 1} more`
      : String(head).slice(0, 100);
    return {
      type: "thinking_group",
      summary,
      steps,
      duration_ms: liveThinkingStartedAt ? Date.now() - liveThinkingStartedAt : 0,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveThinkingVersion, liveThinkingStartedAt]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stickToBottom.current = nearBottom;
  };

  useEffect(() => {
    if (stickToBottom.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [blocks.length, thinkingText]);

  useEffect(() => {
    if (isWorking) document.title = "Analyzing... — Manthan";
    else if (phase === "done") document.title = "Done — Manthan";
    else document.title = "Manthan";
    return () => { document.title = "Manthan"; };
  }, [phase, isWorking]);

  const showJump = !stickToBottom.current && blocks.length > 0;

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-6"
      >
        {/* Outer column is wider; each block picks its own width below so
            inline visuals get the full canvas and everything else stays
            in the comfortable 2xl reading column. */}
        <div className="max-w-4xl mx-auto space-y-4">
          {blocks.map((block, i) => {
            const wide = block.type === "inline_visual";
            return (
              <div key={i} className={wide ? "" : "max-w-2xl mx-auto"}>
                <BlockRenderer block={block} />
              </div>
            );
          })}

          {/* Live phase card — the in-progress buffer streams here so
              the exec sees phases expand as the agent works, not a
              frozen "Thinking…" indicator. Auto-expanded; click the
              header to collapse. */}
          {isWorking && liveGroup && (
            <div className="max-w-2xl mx-auto">
              <ThinkingGroup group={liveGroup} live />
            </div>
          )}

          {/* Fallback sliver — only shown when we don't have a live
              group yet (e.g. right after session_start before any step
              has been pushed). */}
          {isWorking && !liveGroup && (
            <div className="max-w-2xl mx-auto flex items-start gap-3 py-3">
              <ManthanLogo size={20} className="text-accent shrink-0 mt-0.5" animate />
              {progressiveStatus ? (
                <span
                  key={progressiveStatus}
                  className="text-sm text-text-tertiary font-body leading-relaxed animate-fade-in"
                >
                  {progressiveStatus}
                </span>
              ) : (
                <span className="text-sm text-text-faint font-body animate-pulse">
                  Thinking…
                </span>
              )}
            </div>
          )}

          {/* Inline "building dashboard" chip — visible even when the
              artifact side-panel is collapsed so the exec knows the
              30s–3m repair pass is still making progress. */}
          <BuildingArtifactChip />

          <div ref={bottomRef} />
        </div>
      </div>

      {showJump && (
        <button
          onClick={() => {
            stickToBottom.current = true;
            bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
          }}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full bg-surface-raised border border-border shadow-md text-[11px] text-text-secondary hover:text-text-primary hover:border-border-strong transition-all"
        >
          Jump to latest ↓
        </button>
      )}
    </div>
  );
}

/** Chip shown while `create_artifact` is pending server-side — the
 *  validate + repair + save pipeline can take 30s–3m on large
 *  dashboards and previously the chat went silent through that gap. */
function BuildingArtifactChip() {
  const building = useAgentStore((s) => s.buildingArtifact);
  const artifact = useAgentStore((s) => s.artifact);
  const repairing = useAgentStore((s) => s.repairingArtifact);
  // Only show while in-flight — i.e. building has fired but the final
  // artifact hasn't landed yet (or landed with a different id).
  if (!building) return null;
  if (artifact && artifact.id === building.artifact_id) return null;
  const label = repairing ? "Polishing dashboard…" : "Building dashboard…";
  return (
    <div className="max-w-2xl mx-auto flex items-center gap-3 py-3">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
      </span>
      <span className="text-sm text-text-primary font-body font-medium">
        {label}
      </span>
      <span className="text-sm text-text-faint font-body truncate">
        {building.title} · this can take 1–3 min
      </span>
    </div>
  );
}
