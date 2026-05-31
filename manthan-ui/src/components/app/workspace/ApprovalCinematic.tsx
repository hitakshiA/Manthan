/**
 * ApprovalCinematic - the takeover after the operator hits Approve.
 *
 * Editorial / "feels alive" requirement from the sketch:
 *   - Clear out the page chrome.
 *   - Animate each action one at a time.
 *   - Each action holds the canvas for a minimum of 3 seconds, even if
 *     it completes faster - the operator needs to feel each action land,
 *     not see a blur of green checkmarks.
 *   - Show the source it touched + a single-line description of what
 *     the agent is doing.
 *   - After the last one settles, fade out and the parent flips to the
 *     Closed Brief view.
 *
 * Driven by:
 *   - `actions[]` - the drafted actions in execution order
 *   - real `action.status` transitions arriving via the case SSE stream
 *
 * Sketch fidelity:
 *
 *   ┌──────────────────────────────────────────────┐
 *   │           ● ● ● ○ ○ ○        2 of 6          │
 *   │                                              │
 *   │              [ source icon ]                 │
 *   │             ┌──────────────┐                 │
 *   │             │ Action title │                 │
 *   │             └──────────────┘                 │
 *   │                                              │
 *   │              now firing · - · fired ✓        │
 *   └──────────────────────────────────────────────┘
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";

import { SourceIcon } from "@/components/ui/SourceIcon";
import { getSource } from "@/lib/sources";
import type { ActionStatus, WorkspaceAction } from "./types";

/** Minimum dwell per action so each one actually registers visually. */
const MIN_DWELL_MS = 3000;

/** Max time we wait for a real completion before forcing an advance.
 *  Prevents the cinematic from getting stuck if the actor worker hangs. */
const HARD_TIMEOUT_MS = 18_000;

/** Time between final-action complete and onAllComplete firing. Gives
 *  the operator a beat to see the last green check before the layout
 *  flips back to the Brief. */
const TRAILING_HOLD_MS = 900;

const TERMINAL_STATUSES = new Set<ActionStatus>([
  "succeeded",
  "failed",
  "drift",
]);

export interface ApprovalCinematicProps {
  actions: WorkspaceAction[];
  /** Called once the cinematic has walked through every action and the
      trailing hold has elapsed. The parent transitions to the Closed
      Brief view. */
  onAllComplete: () => void;
}

export function ApprovalCinematic({
  actions,
  onAllComplete,
}: ApprovalCinematicProps) {
  // Filter out actions the operator denied - only fire-actions belong
  // in the cinematic.
  const playable = useMemo(
    () => actions.filter((a) => a.status !== "denied" && a.status !== "drafted-skipped"),
    [actions],
  );

  const [currentIdx, setCurrentIdx] = useState(0);
  const [minElapsed, setMinElapsed] = useState(false);
  const [hardTimedOut, setHardTimedOut] = useState(false);
  const completedRef = useRef(false);

  const current = playable[currentIdx];

  // Reset per-action timers when currentIdx advances.
  useEffect(() => {
    setMinElapsed(false);
    setHardTimedOut(false);
    if (currentIdx >= playable.length) return;
    const tMin = window.setTimeout(() => setMinElapsed(true), MIN_DWELL_MS);
    const tHard = window.setTimeout(
      () => setHardTimedOut(true),
      HARD_TIMEOUT_MS,
    );
    return () => {
      window.clearTimeout(tMin);
      window.clearTimeout(tHard);
    };
  }, [currentIdx, playable.length]);

  // Advance when (min dwell elapsed AND real status terminal) OR (hard
  // timeout). The hard timeout shouldn't normally fire - it's a safety
  // net so the UI doesn't get stuck if the actor worker hangs.
  const realDone =
    current?.status !== undefined && TERMINAL_STATUSES.has(current.status);

  useEffect(() => {
    if (currentIdx >= playable.length) return;
    if (!minElapsed) return;
    if (!realDone && !hardTimedOut) return;
    const t = window.setTimeout(() => {
      setCurrentIdx((i) => i + 1);
    }, 350);
    return () => window.clearTimeout(t);
  }, [currentIdx, playable.length, minElapsed, realDone, hardTimedOut]);

  // When we run out of actions, fire onAllComplete once.
  useEffect(() => {
    if (completedRef.current) return;
    if (currentIdx < playable.length) return;
    completedRef.current = true;
    const t = window.setTimeout(onAllComplete, TRAILING_HOLD_MS);
    return () => window.clearTimeout(t);
  }, [currentIdx, playable.length, onAllComplete]);

  // Edge case: 0 playable actions (e.g. user approved but the actor
  // wrote no actions). Skip straight to the closed view.
  useEffect(() => {
    if (playable.length === 0 && !completedRef.current) {
      completedRef.current = true;
      onAllComplete();
    }
  }, [playable.length, onAllComplete]);

  return (
    <section
      className="flex-1 min-h-0 flex flex-col items-center justify-center px-10 py-10 relative"
      style={{ background: "var(--color-bg)" }}
    >
      {/* Progress dots - one per action. */}
      <div
        className="absolute top-8 left-0 right-0 flex items-center justify-center gap-2"
        aria-label={`Action ${Math.min(currentIdx + 1, playable.length)} of ${playable.length}`}
      >
        {playable.map((a, i) => (
          <ProgressDot
            key={a.id ?? i}
            index={i}
            currentIdx={currentIdx}
            status={a.status}
          />
        ))}
        <span
          className="ml-3 text-[10.5px] tabular-nums"
          style={{
            color: "var(--color-ink-faint)",
            letterSpacing: "0.04em",
          }}
        >
          {Math.min(currentIdx + 1, playable.length)} of {playable.length}
        </span>
      </div>

      {/* The featured action. AnimatePresence handles the cross-fade. */}
      <div className="w-full max-w-[640px] mx-auto">
        <AnimatePresence mode="wait">
          {current ? (
            <motion.div
              key={current.id ?? currentIdx}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.32 }}
              className="flex flex-col items-center text-center"
            >
              <ActionStage action={current} />
            </motion.div>
          ) : (
            <motion.div
              key="done"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="text-center"
            >
              <p
                className="font-display italic text-[18px]"
                style={{ color: "var(--color-ink-strong)" }}
              >
                All actions fired.
              </p>
              <p
                className="mt-2 text-[12px]"
                style={{ color: "var(--color-ink-faint)" }}
              >
                Wrapping up…
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

function ActionStage({ action }: { action: WorkspaceAction }) {
  const sourceId = action.source ?? "stripe";
  const sourceMeta = getSource(sourceId);
  const sourceName = sourceMeta?.name ?? sourceId;
  const phase = derivePhase(action);

  return (
    <>
      {/* Step eyebrow */}
      <div
        className="eyebrow mb-5"
        style={{ color: "var(--color-ink-faint)" }}
      >
        Firing action
      </div>

      {/* The hero glyph: source icon in a tile, with a slow ripple while
          the action is running. */}
      <SourceTile sourceId={sourceId} phase={phase} />

      {/* Action title - italic display, big enough to read across the room. */}
      <h2
        className="mt-6 font-display text-[clamp(1.4rem,1.1rem+0.8vw,1.85rem)] leading-[1.18]"
        style={{ color: "var(--color-ink-strong)" }}
      >
        {action.title}
      </h2>

      {/* Target line - what the agent is actually calling. */}
      <p
        className="mt-2 font-mono text-[11.5px] tabular-nums"
        style={{ color: "var(--color-ink-faint)" }}
      >
        {action.target}
      </p>

      {/* Footer: phase + source name */}
      <div className="mt-8 flex items-center gap-3">
        <PhaseChip phase={phase} />
        <span
          className="text-[11px] tracking-[0.04em] uppercase"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          via {sourceName}
        </span>
      </div>

      {/* If the action carries an external_ref, surface it as proof the
          fire actually landed. */}
      {action.externalRef && phase === "fired" && (
        <p
          className="mt-3 text-[10.5px] tabular-nums"
          style={{ color: "var(--color-ink-faint)" }}
        >
          ref · <span className="font-mono">{action.externalRef}</span>
        </p>
      )}

      {/* Failure: show the error message so the operator sees why. */}
      {phase === "failed" && action.errorMessage && (
        <p
          className="mt-3 text-[12px] max-w-md"
          style={{ color: "var(--color-danger)" }}
        >
          {action.errorMessage}
        </p>
      )}
    </>
  );
}

type Phase = "queued" | "firing" | "fired" | "failed";

function derivePhase(action: WorkspaceAction): Phase {
  const s = action.status;
  if (s === "succeeded") return "fired";
  if (s === "failed") return "failed";
  if (s === "drift") return "failed";
  if (s === "executing" || s === "approved") return "firing";
  return "queued";
}

/** Big source-icon tile with a soft pulse while the action is firing. */
function SourceTile({
  sourceId,
  phase,
}: {
  sourceId: string;
  phase: Phase;
}) {
  const firing = phase === "firing" || phase === "queued";
  return (
    <div className="relative" style={{ width: 96, height: 96 }}>
      {firing && (
        <motion.span
          aria-hidden
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--color-accent) 0%, transparent 70%)",
            opacity: 0.18,
          }}
          animate={{ scale: [1, 1.18, 1], opacity: [0.18, 0.28, 0.18] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
      <div
        className="absolute inset-3 flex items-center justify-center"
        style={{
          background: "var(--color-surface-2)",
          border: `1px solid ${
            phase === "failed"
              ? "var(--color-danger)"
              : phase === "fired"
                ? "var(--color-accent)"
                : "var(--color-rule)"
          }`,
          borderRadius: "var(--radius-md)",
          transition: "border-color 220ms var(--ease-out-quart)",
        }}
      >
        <SourceIcon id={sourceId} size={36} tinted />
      </div>
      {phase === "fired" && (
        <motion.div
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="absolute -bottom-1 -right-1 flex items-center justify-center"
          style={{
            width: 26,
            height: 26,
            borderRadius: 999,
            background: "var(--color-accent)",
            color: "var(--color-accent-ink)",
            border: "2px solid var(--color-bg)",
          }}
        >
          <Check size={14} strokeWidth={3} />
        </motion.div>
      )}
      {phase === "failed" && (
        <motion.div
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="absolute -bottom-1 -right-1 flex items-center justify-center"
          style={{
            width: 26,
            height: 26,
            borderRadius: 999,
            background: "var(--color-danger)",
            color: "var(--color-ink-on-danger, #fff)",
            border: "2px solid var(--color-bg)",
          }}
        >
          <AlertTriangle size={13} strokeWidth={2.5} />
        </motion.div>
      )}
    </div>
  );
}

function PhaseChip({ phase }: { phase: Phase }) {
  const label =
    phase === "queued"
      ? "queued"
      : phase === "firing"
        ? "firing"
        : phase === "fired"
          ? "fired"
          : "failed";
  const color =
    phase === "failed"
      ? "var(--color-danger)"
      : phase === "fired"
        ? "var(--color-accent)"
        : "var(--color-amber)";

  return (
    <span
      className="inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.14em]"
      style={{ color }}
    >
      {phase === "firing" && <Loader2 size={10} className="animate-spin" />}
      {phase === "fired" && <Check size={10} />}
      {phase === "failed" && <AlertTriangle size={10} />}
      {phase === "queued" && (
        <span
          className="inline-block rounded-full"
          style={{
            width: 6,
            height: 6,
            background: "var(--color-amber)",
          }}
        />
      )}
      {label}
    </span>
  );
}

function ProgressDot({
  index,
  currentIdx,
  status,
}: {
  index: number;
  currentIdx: number;
  status?: ActionStatus;
}) {
  const isPast = index < currentIdx;
  const isCurrent = index === currentIdx;
  const failed = status === "failed" || status === "drift";

  let bg = "var(--color-rule)";
  if (isPast) bg = failed ? "var(--color-danger)" : "var(--color-accent)";
  if (isCurrent) bg = failed ? "var(--color-danger)" : "var(--color-amber)";

  return (
    <motion.span
      animate={{
        scale: isCurrent ? 1.15 : 1,
      }}
      transition={{ duration: 0.3 }}
      className="inline-block rounded-full"
      style={{
        width: 7,
        height: 7,
        background: bg,
      }}
      aria-current={isCurrent ? "step" : undefined}
    />
  );
}
