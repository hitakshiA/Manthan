/**
 * LandingHeroDemo - hero showcase, editorial-print direction.
 *
 * Design intent (per .impeccable.md):
 *   - Editorial precision: closer to a Wall Street research note than to
 *     a SaaS dashboard. Hairlines, generous whitespace, Spectral italic
 *     for emphasis, tabular nums for every number.
 *   - Restrained "adult in the room" voice. The agent has done the work;
 *     it's presenting findings to a partner.
 *   - No Mac browser chrome. No pill badges. No carousel dots. No left-
 *     stripe accents. No tilted stamps. No "LIVE" pulse.
 *
 * Continuous frame across phases - only the canvas swaps:
 *
 *   ┌─────────────────────────────────────────────┐
 *   │  CASE NWL-19284 · NORTHWIND LOGISTICS  LIVE │   header strip
 *   │  ─────────────────────────────────────────  │   hairline
 *   │                                             │
 *   │            [phase canvas - swaps]           │
 *   │                                             │
 *   │  ─────────────────────────────────────────  │   hairline
 *   │  14:21:09 UTC · STEP 3 OF 6                 │   status strip
 *   └─────────────────────────────────────────────┘
 *
 * Phases loop ~70s total, auto-paused off-screen.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useInView } from "motion/react";
import { ArrowRight, Check, Loader2, Play, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";
import { SourceIcon } from "@/components/ui/SourceIcon";

// ──────────────────────────────────────────────────────────────────────
// The case - written to feel like one a real Director would respect.
// Every finding cites a specific source + ref.
// ──────────────────────────────────────────────────────────────────────

const CASE = {
  shortId: "NWL-19284",
  customer: "Northwind Logistics",
  caseLine: "vs. a $9,200 chargeback",
  amount: "$9,200",
  tldr:
    "Northwind disputed the May Enterprise renewal claiming vendor failure. " +
    "Across eleven sources we found nineteen months of healthy usage, the " +
    "original contract signed in writing, eight closed support tickets with " +
    "an NPS of nine, and zero unfulfillment events.",
  recommendation: "Recommend fight - the evidence is overwhelmingly on our side.",
} as const;

interface SourceStop {
  src: string;
  name: string;
  question: string;     // what Manthan is asking this source, plain English
  finding: string;      // the answer Manthan brings back
  citeRef: string;      // realistic ref id used on the citation chip
}
const STOPS: SourceStop[] = [
  {
    src: "stripe",
    name: "Stripe",
    question: "what it knows about the May 22 dispute",
    finding:
      "Nineteen months of paid renewals · zero prior disputes",
    citeRef: "customers/cus_UbF7",
  },
  {
    src: "notion",
    name: "Notion",
    question: "for the original Enterprise contract",
    finding:
      "Contract signed November 4, 2024 · covers the disputed services",
    citeRef: "contract-nwl-2024",
  },
  {
    src: "posthog",
    name: "PostHog",
    question: "who has been using the product",
    finding:
      "Fourteen active users through May 23 · two days after the dispute",
    citeRef: "DAU · cohort=nwl",
  },
  {
    src: "intercom",
    name: "Intercom",
    question: "what support history looks like",
    finding:
      "Eight closed tickets · all resolved positively · NPS 9 in April",
    citeRef: "conversations",
  },
  {
    src: "sentry",
    name: "Sentry",
    question: "if anything was actually broken on our side",
    finding:
      "Zero unfulfillment events across the entire dispute window",
    citeRef: "issues",
  },
  {
    src: "hubspot",
    name: "HubSpot",
    question: "what the customer last told us",
    finding:
      "Same contact returned an NPS 9 just three weeks before disputing",
    citeRef: "nps_response_4821",
  },
];

interface ActionBeat {
  src: string;
  title: string;
  target: string;
  ref: string;
}
const ACTIONS: ActionBeat[] = [
  {
    src: "stripe",
    title: "Submit dispute evidence to Stripe",
    target: "POST /v1/disputes/du_1NXY · submit=true",
    ref: "du_1NXY",
  },
  {
    src: "notion",
    title: "Append the decision log in Notion",
    target: "notion.children.append · revenue-disputes/2025",
    ref: "page_18nwl…",
  },
  {
    src: "resend",
    title: "Email Northwind's finance contact",
    target: "POST /resend/emails · billing@northwindlog.com",
    ref: "msg_4f8a…",
  },
];

// ──────────────────────────────────────────────────────────────────────
// Phase machine + time
// ──────────────────────────────────────────────────────────────────────

type Phase = "trigger" | "investigating" | "brief" | "approving" | "closed";

const PHASE_DURATIONS: Record<Phase, number> = {
  trigger: 4,
  investigating: 42,
  brief: 8,
  approving: 16,
  closed: 8,
};
const PHASE_ORDER: Phase[] = ["trigger", "investigating", "brief", "approving", "closed"];
const TOTAL = PHASE_ORDER.reduce((s, p) => s + PHASE_DURATIONS[p], 0);

const PHASE_LABEL: Record<Phase, string> = {
  trigger: "Intake",
  investigating: "Investigating",
  brief: "Brief",
  approving: "Executing",
  closed: "Resolved",
};

/**
 * Playback state machine -
 *
 *   "idle"     · default. Poster frame visible. Play button overlaid.
 *                Loops do NOT start until the visitor opts in.
 *   "playing"  · phase machine runs through trigger → … → closed once.
 *   "finished" · run completed. Poster restored with a Replay button.
 *
 * The poster frame is the Brief canvas captured at its settled moment
 * (just before the Approve button pulse) - it's the densest, most
 * "filled-out dashboard" view in the loop and reads as proof at a
 * glance: customer, verdict, postmortem, drafted actions, citations.
 */
/**
 * Five playback states. The big change from the previous version: the
 * demo no longer plays through automatically. It auto-advances trigger
 * → investigating → brief, then PAUSES at "awaiting-approval" and
 * waits for the visitor to click the green Approve · Execute button.
 * That click is the moment of agency - they nod, and only then do the
 * actions fire.
 *
 *   idle               · poster + play button
 *   playing-pre        · trigger → investigating → brief (auto)
 *   awaiting-approval  · brief is fully rendered; Approve is live and
 *                        waiting for a real human click
 *   playing-post       · approving → closed (auto, after approve click)
 *   finished           · case resolved + "Try it on your stack" CTA
 */
type Playback =
  | "idle"
  | "playing-pre"
  | "awaiting-approval"
  | "playing-post"
  | "finished";

// Cumulative durations that mark the boundaries between auto-advancing
// segments and the manual approval pause.
const PRE_APPROVE_DURATION =
  PHASE_DURATIONS.trigger +
  PHASE_DURATIONS.investigating +
  PHASE_DURATIONS.brief;

export function LandingHeroDemo() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const inView = useInView(wrapRef, { amount: 0.15, once: false });
  const [playback, setPlayback] = useState<Playback>("idle");
  const [phase, setPhase] = useState<Phase>("trigger");
  const [elapsed, setElapsed] = useState(0);
  // Anchor timer to the moment Play was clicked, NOT to component mount,
  // so the wall-clock stamp doesn't drift while the poster is visible.
  const runStartRef = useRef<number | null>(null);

  // Phase machine - only runs during the two auto-advancing segments.
  // Pauses entirely when off-screen, when waiting for approval, when
  // finished, or when idle.
  useEffect(() => {
    const isAutoSegment =
      playback === "playing-pre" || playback === "playing-post";
    if (!isAutoSegment || !inView) return;

    const tickStart = performance.now();
    const tickStartGlobalT = phaseStartTime(phase) + elapsed;
    const id = window.setInterval(() => {
      const now = performance.now();
      const t = tickStartGlobalT + (now - tickStart) / 1000;

      if (playback === "playing-pre") {
        // Hard stop at the end of brief. We HOLD on the brief canvas
        // with the Approve button visible and clickable, waiting for
        // the visitor to nod.
        if (t >= PRE_APPROVE_DURATION) {
          setPhase("brief");
          setElapsed(PHASE_DURATIONS.brief);
          setPlayback("awaiting-approval");
          return;
        }
      } else if (playback === "playing-post") {
        // After approve, run through approving → closed and stop.
        if (t >= TOTAL) {
          setPhase("closed");
          setElapsed(PHASE_DURATIONS.closed);
          setPlayback("finished");
          return;
        }
      }

      let cum = 0;
      for (const p of PHASE_ORDER) {
        if (t < cum + PHASE_DURATIONS[p]) {
          if (p !== phase) setPhase(p);
          setElapsed(t - cum);
          break;
        }
        cum += PHASE_DURATIONS[p];
      }
    }, 100);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playback, inView]);

  // Called by the Approve button in BriefCanvas. Resumes the timer
  // from the start of the approving phase.
  function handleApprove() {
    setPhase("approving");
    setElapsed(0);
    setPlayback("playing-post");
  }

  // Wall-clock stamp - anchored to "now" while playing, frozen on the
  // poster so the stamp reads as a fixed timestamp before the visitor
  // clicks play. Gives the poster a real "Bloomberg Terminal at rest"
  // feel rather than a ticking-but-not-doing-anything one.
  const stamp = useMemo(() => {
    const baseSec = 14 * 3600 + 21 * 60 + 0; // 14:21:00 UTC anchor
    const offset = playback === "idle"
      ? phaseStartTime("brief") + 2  // poster sits mid-brief
      : Math.floor(phaseStartTime(phase) + elapsed);
    const total = baseSec + offset;
    const hh = Math.floor(total / 3600) % 24;
    const mm = Math.floor((total % 3600) / 60);
    const ss = total % 60;
    return `${pad(hh)}:${pad(mm)}:${pad(ss)} UTC`;
  }, [playback, phase, elapsed]);

  // Phase rendered while playing. When idle or finished, we render a
  // bespoke minimal poster instead (see PosterCanvas below) so the
  // play button has room to dominate without competing with body copy.
  const renderedPhase: Phase = phase;
  const renderedElapsed = elapsed;

  function startRun() {
    runStartRef.current = performance.now();
    setPhase("trigger");
    setElapsed(0);
    setPlayback("playing-pre");
  }

  // The frame is frosted glass at rest (idle / finished) so the flora
  // hero video shows through. During any active segment of the run
  // - pre-approve, awaiting-approval, or post-approve - it solidifies
  // so the dashboard reads crisply without the video distracting.
  const glassActive = playback === "idle" || playback === "finished";
  // Show the live canvas content (vs the minimal poster) whenever the
  // visitor is engaged with the run, including the approval pause.
  const liveCanvas =
    playback === "playing-pre" ||
    playback === "awaiting-approval" ||
    playback === "playing-post";

  return (
    <motion.div
      ref={wrapRef}
      className="relative w-full"
      animate={{
        backgroundColor: glassActive
          ? "rgba(15, 15, 17, 0.48)"
          : "rgba(15, 15, 17, 0.98)",
      }}
      transition={{ duration: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
      style={{
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 6,
        overflow: "hidden",
        boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        aspectRatio: "16 / 10",
        color: "rgba(255,255,255,0.92)",
        // Frosted-glass treatment - softens the flora video underneath
        // so the dashboard content stays legible without hiding the
        // background context entirely.
        backdropFilter: "blur(22px) saturate(1.15)",
        WebkitBackdropFilter: "blur(22px) saturate(1.15)",
      }}
    >
      {/* ── HEADER STRIP - persists across every phase. ── */}
      <HeaderStrip
        phase={renderedPhase}
        idle={playback === "idle"}
        awaitingApproval={playback === "awaiting-approval"}
      />

      {/* ── CANVAS - the only thing that swaps phase to phase ── */}
      <div
        className="relative"
        style={{ height: "calc(100% - 72px)" }} // header 36 + status 36
      >
        {/* Content wrapper - fades to translucent when playback is at
             rest (idle / finished). The chrome strips above and below
             stay fully opaque, so only the dashboard *content* dims,
             leaving the play button as the obvious focal point. */}
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: liveCanvas ? 1 : 0.42 }}
          transition={{ duration: 0.45, ease: [0.22, 0.61, 0.36, 1] }}
        >
          <AnimatePresence mode="wait">
            {liveCanvas ? (
              <motion.div
                key={renderedPhase}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
                className="absolute inset-0"
              >
                {renderedPhase === "trigger" && <TriggerCanvas elapsed={renderedElapsed} />}
                {renderedPhase === "investigating" && (
                  <InvestigatingCanvas elapsed={renderedElapsed} />
                )}
                {renderedPhase === "brief" && (
                  <BriefCanvas
                    elapsed={renderedElapsed}
                    awaitingApproval={playback === "awaiting-approval"}
                    onApprove={handleApprove}
                  />
                )}
                {renderedPhase === "approving" && <ApprovingCanvas elapsed={renderedElapsed} />}
                {renderedPhase === "closed" && <ClosedCanvas />}
              </motion.div>
            ) : playback === "idle" ? (
              <motion.div
                key="poster"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
                className="absolute inset-0"
              >
                <PosterCanvas />
              </motion.div>
            ) : null}
            {/* playback === "finished" renders no canvas content at all
                - just the glass background showing the flora video
                through. The FinishedOverlay below sits on that clean
                surface as the sole focal point. */}
          </AnimatePresence>
        </motion.div>

        {/* ── PLAY OVERLAY (idle) - sleek play button on the poster.
             ── FINISHED OVERLAY (finished) - "Try it on your stack"
                CTA that routes the visitor to /signup (or /app if
                already signed in). A small inline replay link below
                lets them watch the run again without dominating the
                CTA. ── */}
        <AnimatePresence>
          {playback === "idle" && (
            <PlayOverlay kind="play" onClick={startRun} />
          )}
          {playback === "finished" && (
            <FinishedOverlay onReplay={startRun} />
          )}
        </AnimatePresence>
      </div>

      {/* ── STATUS STRIP - time + progress. ── */}
      <StatusStrip
        phase={renderedPhase}
        elapsed={renderedElapsed}
        stamp={stamp}
        idle={playback === "idle"}
        awaitingApproval={playback === "awaiting-approval"}
        opaque={glassActive}
      />
    </motion.div>
  );
}

/**
 * Sleek play button overlay. Blurred scrim, centered glyph with a
 * concentric ring that pulses on hover, captions in confident weight.
 * Sits inside the canvas region (between header and status strips)
 * so it visually belongs to the dashboard, not the page chrome.
 */
/**
 * Finished overlay - shown after the case resolves. Replaces the old
 * "Replay" button. Reads as a confident invitation rather than a "watch
 * it again" loop: "Try it on your stack" with the iridescent pill from
 * the landing hero, routing to /signup. A quiet inline "Watch again"
 * link sits beneath the CTA for visitors who do want to replay.
 */
function FinishedOverlay({ onReplay }: { onReplay: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 0.61, 0.36, 1] }}
      className="absolute inset-0 flex flex-col items-center justify-center px-10"
      style={{ background: "transparent" }}
    >
      <span
        className="text-[10.5px] uppercase"
        style={{
          color: "rgba(86, 207, 131, 0.92)",
          letterSpacing: "0.22em",
          fontWeight: 500,
        }}
      >
        Case resolved
      </span>

      <h3
        className="mt-3 text-center"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: "clamp(22px, 2.6vw, 30px)",
          color: "rgba(255,255,255,0.95)",
          letterSpacing: "-0.012em",
          lineHeight: 1.1,
        }}
      >
        Now try it on your stack.
      </h3>

      <p
        className="mt-2.5 text-center max-w-[40ch] text-[12.5px]"
        style={{
          color: "rgba(255,255,255,0.62)",
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          letterSpacing: "-0.003em",
          lineHeight: 1.5,
        }}
      >
        Point Manthan at your Stripe, your CRM, your support inbox.
        See it land a real verdict in minutes.
      </p>

      {/* End-of-run CTA - intentionally a different shape from the
           iridescent hero pill. The hero pill is the playful "watch the
           magic" invitation; this is the grounded "now commit" button.
           Cream-white surface, dark ink, hairline ring, restrained
           drop shadow - reads as the confident close of an editorial
           memo, not a marketing flourish. */}
      <Link
        to="/signup"
        className="mt-6 inline-flex items-center gap-2 transition-all hover:opacity-95 hover:translate-y-[-1px]"
        style={{
          background: "rgba(255,255,255,0.96)",
          color: "#0a0a0a",
          borderRadius: 4,
          fontSize: 13,
          fontWeight: 500,
          letterSpacing: "-0.002em",
          padding: "11px 22px",
          boxShadow:
            "0 1px 0 rgba(255,255,255,0.6) inset, " +
            "0 8px 22px rgba(0,0,0,0.35), " +
            "0 0 0 1px rgba(255,255,255,0.55)",
        }}
      >
        Try Manthan on your stack
        <ArrowRight size={14} strokeWidth={2.2} />
      </Link>

      <button
        type="button"
        onClick={onReplay}
        className="mt-4 inline-flex items-center gap-1.5 hover:opacity-90 transition-opacity outline-none"
        style={{
          color: "rgba(255,255,255,0.55)",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontSize: 11,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        <RotateCcw size={11} strokeWidth={2} />
        Watch again
      </button>
    </motion.div>
  );
}

function PlayOverlay({
  kind,
  onClick,
}: {
  kind: "play" | "replay";
  onClick: () => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 0.61, 0.36, 1] }}
      whileHover={{ scale: 1.0 }}
      aria-label={kind === "replay" ? "Replay the demo" : "Play the demo"}
      className="play-overlay-btn absolute inset-0 flex flex-col items-center justify-center cursor-pointer outline-none"
      style={{
        // No scrim, no blur. The dashboard content underneath is
        // already dimmed by the wrapper, so this overlay can stay
        // fully transparent - the glyph + captions read sharp and
        // confident against the translucent content behind.
        background: "transparent",
      }}
    >
      {/* Glyph - single bright button, no pulse rings, no hover
           breathing. A quiet inner-shadow brightens on hover via
           CSS for tactile feedback; the icon itself stays put. */}
      <span
        className="play-glyph inline-flex items-center justify-center shrink-0"
        style={{
          width: 88,
          height: 88,
          borderRadius: 999,
          background: "rgba(255,255,255,0.96)",
          color: "#0a0a0a",
          boxShadow:
            "0 1px 0 rgba(255,255,255,0.5) inset, " +
            "0 10px 30px rgba(0,0,0,0.55), " +
            "0 0 0 1px rgba(255,255,255,0.6)",
          transition:
            "box-shadow 220ms cubic-bezier(0.22, 0.61, 0.36, 1)",
        }}
      >
        {kind === "replay" ? (
          <RotateCcw size={28} strokeWidth={2} />
        ) : (
          // Triangle nudged +2px right so it appears optically
          // centered in the circle (the glyph's mass leans left).
          <Play
            size={28}
            strokeWidth={2}
            fill="currentColor"
            style={{ transform: "translateX(2px)" }}
          />
        )}
      </span>

      <span
        className="mt-6 text-[12px] uppercase"
        style={{
          color: "rgba(255,255,255,0.98)",
          letterSpacing: "0.24em",
          fontWeight: 500,
        }}
      >
        {kind === "replay" ? "Replay" : "Watch the case unfold"}
      </span>
      <span
        className="mt-2 text-[10.5px] uppercase"
        style={{
          color: "rgba(255,255,255,0.62)",
          letterSpacing: "0.16em",
        }}
      >
        {kind === "replay"
          ? "Stripe webhook → resolved"
          : "60 seconds · Stripe webhook → resolved"}
      </span>
    </motion.button>
  );
}

function phaseStartTime(p: Phase): number {
  let acc = 0;
  for (const x of PHASE_ORDER) {
    if (x === p) return acc;
    acc += PHASE_DURATIONS[x];
  }
  return 0;
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

// ──────────────────────────────────────────────────────────────────────
// Header - case identifier + phase label, separated by a hairline.
// No browser-chrome dots. Just typography.
// ──────────────────────────────────────────────────────────────────────

function HeaderStrip({
  phase,
  idle,
  awaitingApproval,
}: {
  phase: Phase;
  idle?: boolean;
  awaitingApproval?: boolean;
}) {
  return (
    <header
      className="relative flex items-center pl-4 pr-7"
      style={{
        height: 36,
        // Always-opaque chrome - keeps the traffic-light strip readable
        // regardless of whether the rest of the frame is in glass mode.
        background: "oklch(0.135 0.006 75)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        zIndex: 5,
      }}
    >
      {/* Mac-style window controls - kept restrained: 11px dots, brand
          hexes muted a touch for the warm-dark canvas. */}
      <div
        className="flex items-center mr-5"
        style={{ gap: 8 }}
        aria-hidden
      >
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: 999,
            background: "#ff5f57",
          }}
        />
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: 999,
            background: "#febc2e",
          }}
        />
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: 999,
            background: "#28c840",
          }}
        />
      </div>
      <span
        className="font-mono text-[10.5px] tabular-nums"
        style={{
          color: "rgba(255,255,255,0.55)",
          letterSpacing: "0.06em",
        }}
      >
        CASE&nbsp;{CASE.shortId}
      </span>
      <span
        className="mx-2.5"
        style={{ color: "rgba(255,255,255,0.22)" }}
        aria-hidden
      >
        ·
      </span>
      <span
        className="text-[11px]"
        style={{ color: "rgba(255,255,255,0.78)", letterSpacing: "0.02em" }}
      >
        {CASE.customer}
      </span>
      <span
        className="ml-auto text-[10px] uppercase"
        style={{
          color: awaitingApproval
            ? "rgba(255,182,77,0.92)"
            : idle
              ? "rgba(255,255,255,0.45)"
              : phase === "closed"
                ? "rgba(255,255,255,0.42)"
                : "var(--color-accent, #56cf83)",
          letterSpacing: "0.22em",
        }}
      >
        {awaitingApproval
          ? "Awaiting your nod"
          : idle
            ? "Tap to play"
            : PHASE_LABEL[phase]}
      </span>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Status strip at the bottom - time, step, simple progress.
// ──────────────────────────────────────────────────────────────────────

function StatusStrip({
  phase,
  elapsed,
  stamp,
  idle,
  awaitingApproval,
  opaque,
}: {
  phase: Phase;
  elapsed: number;
  stamp: string;
  idle?: boolean;
  awaitingApproval?: boolean;
  /** When false (demo is playing), the strip inherits the solid
   *  outer-frame fill. When true (glass mode), we let the translucent
   *  frame underneath show through, matching the canvas area's
   *  see-through-to-video treatment. */
  opaque?: boolean;
}) {
  const progress: string = (() => {
    if (idle) return "Tap to play";
    if (awaitingApproval) return "Click Approve to fire";
    if (phase === "investigating") {
      const per = PHASE_DURATIONS.investigating / STOPS.length;
      const i = Math.min(STOPS.length, Math.floor(elapsed / per) + 1);
      return `Step ${pad(i)} of ${pad(STOPS.length)}`;
    }
    if (phase === "approving") {
      const per = PHASE_DURATIONS.approving / ACTIONS.length;
      const i = Math.min(ACTIONS.length, Math.floor(elapsed / per) + 1);
      return `Action ${pad(i)} of ${pad(ACTIONS.length)}`;
    }
    if (phase === "brief") return "Awaiting your nod";
    if (phase === "closed") return "All actions fired";
    return "Routing…";
  })();
  return (
    <footer
      className="relative flex items-center px-7"
      style={{
        height: 36,
        borderTop: "1px solid rgba(255,255,255,0.06)",
        // When the frame is in glass mode the strip stays translucent
        // (the video softly shows through). When playing, we lift it
        // to the same near-opaque ink as the chrome above so the
        // dashboard reads as a solid surface during the run.
        background: opaque ? "transparent" : "oklch(0.135 0.006 75)",
      }}
    >
      <span
        className="font-mono text-[10.5px] tabular-nums"
        style={{
          color: "rgba(255,255,255,0.42)",
          letterSpacing: "0.06em",
        }}
      >
        {stamp}
      </span>
      <span
        className="ml-auto text-[10px] uppercase"
        style={{
          color: "rgba(255,255,255,0.42)",
          letterSpacing: "0.16em",
        }}
      >
        {progress}
      </span>
    </footer>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Phase 1 - TRIGGER. Teletype-style intake: a webhook lands,
// the case opens. No card-with-left-stripe.
// ──────────────────────────────────────────────────────────────────────

/**
 * Poster - the at-rest frame visitors see before clicking play.
 *
 * Deliberately minimal: just the brief eyebrow + the case title in
 * Spectral italic on the left, the suggested-actions column reduced
 * to source bylines on the right, and the action bar at the bottom.
 * No TLDR body copy, no postmortem detail, no citation chips - those
 * would compete with the play button for attention. The empty space
 * is the point.
 */
function PosterCanvas() {
  return (
    <div
      className="h-full grid"
      style={{
        gridTemplateColumns: "minmax(0, 1.35fr) minmax(0, 1fr)",
      }}
    >
      {/* LEFT - title only */}
      <div className="px-12 pt-8 pb-5 flex flex-col">
        <Eyebrow>Brief</Eyebrow>
        <h2
          className="mt-3 leading-[1.08]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(20px, 2.4vw, 26px)",
            color: "rgba(255,255,255,0.92)",
            letterSpacing: "-0.010em",
          }}
        >
          {CASE.customer}{" "}
          <em
            style={{
              fontStyle: "italic",
              color: "rgba(255,255,255,0.55)",
            }}
          >
            {CASE.caseLine}
          </em>
        </h2>
      </div>

      {/* RIGHT - action bylines only, no targets, no mono lines */}
      <div
        className="pt-8 pb-3 pl-9 pr-12 flex flex-col"
        style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Suggested actions</Eyebrow>
        <ol className="mt-4 space-y-3 flex-1 min-h-0">
          {ACTIONS.map((a, i) => (
            <li
              key={i}
              className="grid pb-3"
              style={{
                gridTemplateColumns: "20px minmax(0,1fr)",
                gap: 10,
                borderBottom:
                  i < ACTIONS.length - 1
                    ? "1px solid rgba(255,255,255,0.05)"
                    : "none",
              }}
            >
              <span
                className="text-[10.5px] tabular-nums pt-0.5"
                style={{
                  color: "rgba(255,255,255,0.32)",
                  letterSpacing: "0.04em",
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                }}
              >
                {i + 1}.
              </span>
              <div className="min-w-0">
                <SourceWord src={a.src} label={a.src.toUpperCase()} />
                <div
                  className="text-[13px] leading-[1.4] mt-1.5"
                  style={{ color: "rgba(255,255,255,0.85)" }}
                >
                  {a.title}
                </div>
              </div>
            </li>
          ))}
        </ol>

        {/* Action bar - same shape as the live Brief, but no pulse. */}
        <div
          className="mt-3 pt-3 flex items-center justify-between gap-3"
          style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center gap-4">
            {(["Escalate", "Hold", "Deny"] as const).map((verb) => (
              <span
                key={verb}
                className="text-[11px]"
                style={{
                  color:
                    verb === "Deny"
                      ? "rgba(255,107,107,0.78)"
                      : "rgba(255,255,255,0.45)",
                }}
              >
                {verb}
              </span>
            ))}
          </div>
          <span
            className="text-[11.5px] font-medium px-3.5 py-1.5"
            style={{
              background: "var(--color-accent, #56cf83)",
              color: "#0a0a0a",
              borderRadius: 4,
            }}
          >
            Approve · Execute
          </span>
        </div>
      </div>
    </div>
  );
}

function TriggerCanvas({ elapsed }: { elapsed: number }) {
  // Two lines reveal in sequence - the second after ~2s.
  const openedShown = elapsed > 1.9;
  return (
    <div className="h-full flex flex-col items-start justify-center px-12 max-w-[640px] mx-auto">
      <Eyebrow>Intake</Eyebrow>

      <motion.h2
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
        className="mt-3 leading-[1.08]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: "clamp(22px, 2.6vw, 30px)",
          color: "rgba(255,255,255,0.94)",
          letterSpacing: "-0.012em",
        }}
      >
        A new dispute landed.
      </motion.h2>

      {/* Webhook line - no card, no left-stripe. Just typography. */}
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2 }}
        className="mt-6 grid"
        style={{ gridTemplateColumns: "84px minmax(0,1fr)", gap: 14 }}
      >
        <SourceWord src="stripe" label="STRIPE" />
        <span
          className="font-mono text-[12px] tabular-nums"
          style={{ color: "rgba(255,255,255,0.85)", lineHeight: 1.5 }}
        >
          charge.dispute.created · du_1NXY · {CASE.amount}.00 · vendor_failure
        </span>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.5 }}
        className="mt-2 grid"
        style={{ gridTemplateColumns: "84px minmax(0,1fr)", gap: 14 }}
      >
        <SourceWord src="" label="CUSTOMER" />
        <span
          className="text-[13px]"
          style={{ color: "rgba(255,255,255,0.85)" }}
        >
          {CASE.customer} · cus_UbF7BXDTnXgUCt
        </span>
      </motion.div>

      <AnimatePresence>
        {openedShown && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45 }}
            className="mt-9 flex items-baseline gap-4"
          >
            <Eyebrow accent>↳ Routed</Eyebrow>
            <span
              className="text-[13.5px]"
              style={{
                color: "rgba(255,255,255,0.85)",
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
              }}
            >
              Case <span className="font-mono not-italic tabular-nums" style={{ fontStyle: "normal" }}>{CASE.shortId}</span> opened.
              Manthan is on it.
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Phase 2 - INVESTIGATING.
// Typographic "Manthan is asking *Source* …" statement that morphs
// as the agent moves through sources. Findings accumulate below as
// editorial marginalia (NOT terminal output).
// ──────────────────────────────────────────────────────────────────────

function InvestigatingCanvas({ elapsed }: { elapsed: number }) {
  const per = PHASE_DURATIONS.investigating / STOPS.length;
  const idx = Math.min(STOPS.length - 1, Math.floor(elapsed / per));
  const local = elapsed - idx * per;
  const stop = STOPS[idx];

  // Beats within a stop:
  //   0.0 – 1.0s : "Manthan is asking *Stripe* …" appears
  //   1.0 – per-1.0 : the source thinks
  //   per-1.0 – per : the finding settles into the column on the right
  const findingRevealAt = per - 1.0;
  const showFinding = local > findingRevealAt;

  // Findings list - all stops up to (and including, when revealed) current.
  const findings = useMemo(() => {
    const upTo = idx + (showFinding ? 1 : 0);
    return STOPS.slice(0, upTo);
  }, [idx, showFinding]);

  return (
    <div
      className="h-full grid"
      style={{
        gridTemplateColumns: "minmax(0, 0.95fr) minmax(0, 1.05fr)",
        columnGap: 0,
      }}
    >
      {/* LEFT - the typographic statement, single subject swapping in/out */}
      <div className="px-12 pt-8 pb-6 flex flex-col">
        <Eyebrow>Investigating</Eyebrow>

        <div
          className="mt-5 leading-[1.16]"
          style={{
            fontFamily: "Spectral, serif",
            color: "rgba(255,255,255,0.92)",
            fontSize: "clamp(22px, 2.4vw, 28px)",
            letterSpacing: "-0.010em",
          }}
        >
          Manthan is asking{" "}
          <AnimatePresence mode="wait">
            <motion.span
              key={stop.src}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
              style={{
                fontStyle: "italic",
                color: "var(--color-accent, #56cf83)",
                letterSpacing: "-0.010em",
                display: "inline-block",
              }}
            >
              {stop.name}
            </motion.span>
          </AnimatePresence>
        </div>

        {/* The question line, smaller, fades with the source */}
        <div className="mt-2 h-[44px] overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={`q-${stop.src}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.35, delay: 0.05 }}
              className="text-[14px] leading-[1.55]"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                color: "rgba(255,255,255,0.55)",
                letterSpacing: "-0.003em",
              }}
            >
              {stop.question}.
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Hero brand glyph - uses the empty space below the question.
            ~96px square so it reads as a hero element, tinted so
            dark-on-dark logos (Notion, PostHog) resolve to the ink
            token while colourful brands (Stripe, HubSpot, Intercom)
            keep their brand hex. The whole thing breathes with the
            source swap. */}
        <div
          className="mt-8 mb-auto flex items-center justify-start"
          style={{ minHeight: 120 }}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={`g-${stop.src}`}
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.45, ease: [0.22, 0.61, 0.36, 1] }}
              className="inline-flex items-center justify-center"
              style={{
                width: 112,
                height: 112,
                color: "rgba(255,255,255,0.92)", // currentColor fallback
              }}
            >
              <SourceIcon id={stop.src} size={96} tinted />
            </motion.div>
          </AnimatePresence>
        </div>

        {/* A quiet "thinking…" cursor while the source thinks */}
        <div>
          <AnimatePresence>
            {local < findingRevealAt && (
              <motion.div
                key={`t-${stop.src}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="flex items-baseline gap-2 text-[11px]"
                style={{
                  color: "rgba(255,255,255,0.42)",
                  letterSpacing: "0.04em",
                }}
              >
                <motion.span
                  animate={{ opacity: [0.3, 0.85, 0.3] }}
                  transition={{ duration: 1.4, repeat: Infinity }}
                >
                  reading
                </motion.span>
                <span>{stop.src} records</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* RIGHT - findings column. Editorial marginalia, not terminal. */}
      <div
        className="pt-8 pb-6 pl-9 pr-12 flex flex-col"
        style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Findings</Eyebrow>

        <ol className="mt-5 space-y-4">
          <AnimatePresence initial={false}>
            {findings.slice(-5).map((s, i, arr) => {
              const isLatest = i === arr.length - 1 && showFinding && i === arr.length - 1;
              return (
                <motion.li
                  key={s.src + s.finding}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: isLatest ? 1 : 0.55, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4 }}
                  className="grid"
                  style={{
                    gridTemplateColumns: "88px minmax(0,1fr)",
                    columnGap: 16,
                  }}
                >
                  <SourceWord src={s.src} label={s.name.toUpperCase()} />
                  <span
                    className="text-[13px] leading-[1.55]"
                    style={{
                      color: isLatest
                        ? "rgba(255,255,255,0.92)"
                        : "rgba(255,255,255,0.55)",
                      fontWeight: isLatest ? 500 : 400,
                    }}
                  >
                    {s.finding}
                  </span>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      </div>
    </div>
  );
}

/**
 * Source word - used as the byline in marginalia rows AND in the
 * trigger eyebrow. Small uppercase Geist with the source icon as a
 * baseline-aligned glyph. Replaces the bordered pill chips of the
 * old version.
 */
function SourceWord({ src, label }: { src: string; label: string }) {
  return (
    <span
      className="inline-flex items-baseline gap-1.5 text-[10px]"
      style={{
        color: "rgba(255,255,255,0.55)",
        letterSpacing: "0.16em",
      }}
    >
      {src && (
        <span
          aria-hidden
          style={{ display: "inline-flex", transform: "translateY(2px)" }}
        >
          <SourceIcon id={src} size={10} tinted />
        </span>
      )}
      <span>{label}</span>
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Phase 3 - BRIEF. Editorial postmortem with workspace-style citation chips.
// Single column on the left, drafted actions on the right.
// ──────────────────────────────────────────────────────────────────────

function BriefCanvas({
  elapsed,
  awaitingApproval,
  onApprove,
}: {
  elapsed: number;
  awaitingApproval?: boolean;
  onApprove?: () => void;
}) {
  // While the brief is auto-advancing, the button gives a soft pulse
  // after a 2.4-s settling beat. Once we're waiting on the visitor it
  // becomes a stronger pulse to draw the eye - and clickable.
  const settled = elapsed > 2.4;
  const pulse = settled || awaitingApproval;
  // Tracks the brief "Firing…" moment between click and the post-approve
  // phase machine taking over, so the visitor sees their click landed.
  const [firing, setFiring] = useState(false);
  function handleClick() {
    if (firing || !onApprove) return;
    setFiring(true);
    // Hold for one beat so the button visibly registers the press,
    // then hand off to the parent's onApprove which kicks the timer
    // into playing-post and the canvas swaps to ApprovingCanvas.
    window.setTimeout(() => {
      onApprove();
      setFiring(false);
    }, 380);
  }

  // Top four findings for the postmortem.
  const top = STOPS.slice(0, 4);

  return (
    <div
      className="h-full grid"
      style={{
        gridTemplateColumns: "minmax(0, 1.35fr) minmax(0, 1fr)",
      }}
    >
      {/* LEFT - Brief postmortem */}
      <div className="px-12 pt-8 pb-5 overflow-hidden flex flex-col">
        <Eyebrow>Brief</Eyebrow>

        <h2
          className="mt-3 leading-[1.08]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(20px, 2.4vw, 26px)",
            color: "rgba(255,255,255,0.92)",
            letterSpacing: "-0.010em",
          }}
        >
          {CASE.customer}{" "}
          <em
            style={{
              fontStyle: "italic",
              color: "rgba(255,255,255,0.55)",
            }}
          >
            {CASE.caseLine}
          </em>
        </h2>

        <p
          className="mt-4 leading-[1.6]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 14,
            color: "rgba(255,255,255,0.82)",
          }}
        >
          {CASE.tldr}
        </p>

        <div className="mt-5">
          <Eyebrow>Postmortem in detail</Eyebrow>
        </div>

        <ol className="mt-3 space-y-3 flex-1 min-h-0">
          {top.map((s, i) => (
            <li
              key={s.src}
              className="grid"
              style={{
                gridTemplateColumns: "20px minmax(0,1fr)",
                gap: 10,
              }}
            >
              <span
                className="text-[10.5px] tabular-nums pt-0.5"
                style={{
                  color: "rgba(255,255,255,0.32)",
                  letterSpacing: "0.04em",
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                }}
              >
                {i + 1}.
              </span>
              <p
                className="text-[12.5px] leading-[1.55]"
                style={{ color: "rgba(255,255,255,0.85)" }}
              >
                {s.finding}
                <CiteChip n={i + 1} src={s.src} label={s.citeRef} />
              </p>
            </li>
          ))}
        </ol>
      </div>

      {/* RIGHT - Suggested actions + the action bar */}
      <div
        className="pt-8 pb-5 pl-9 pr-12 flex flex-col"
        style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Suggested actions</Eyebrow>

        <ol className="mt-4 space-y-3 flex-1 min-h-0">
          {ACTIONS.map((a, i) => (
            <li
              key={i}
              className="grid pb-3"
              style={{
                gridTemplateColumns: "20px minmax(0,1fr)",
                gap: 10,
                borderBottom:
                  i < ACTIONS.length - 1
                    ? "1px solid rgba(255,255,255,0.05)"
                    : "none",
              }}
            >
              <span
                className="text-[10.5px] tabular-nums pt-0.5"
                style={{
                  color: "rgba(255,255,255,0.32)",
                  letterSpacing: "0.04em",
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                }}
              >
                {i + 1}.
              </span>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <SourceWord src={a.src} label={a.src.toUpperCase()} />
                </div>
                <div
                  className="text-[13px] leading-[1.5] mt-1.5"
                  style={{ color: "rgba(255,255,255,0.88)" }}
                >
                  {a.title}
                </div>
                <div
                  className="font-mono text-[10.5px] tabular-nums mt-1 truncate"
                  style={{ color: "rgba(255,255,255,0.42)" }}
                >
                  {a.target}
                </div>
              </div>
            </li>
          ))}
        </ol>

        {/* Action bar - quiet text verbs + the primary approve button */}
        <div
          className="mt-3 pt-3 flex items-center justify-between gap-3"
          style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center gap-4">
            {(["Escalate", "Hold", "Deny"] as const).map((verb) => (
              <span
                key={verb}
                className="text-[11px]"
                style={{
                  color:
                    verb === "Deny"
                      ? "rgba(255,107,107,0.78)"
                      : "rgba(255,255,255,0.45)",
                }}
              >
                {verb}
              </span>
            ))}
          </div>
          <motion.button
            type="button"
            disabled={!awaitingApproval || firing}
            onClick={handleClick}
            animate={
              firing
                ? { scale: 0.96 }
                : pulse
                  ? {
                      boxShadow: awaitingApproval
                        ? [
                            "0 0 0 0 rgba(86,207,131,0)",
                            "0 0 0 14px rgba(86,207,131,0.28)",
                            "0 0 0 0 rgba(86,207,131,0)",
                          ]
                        : [
                            "0 0 0 0 rgba(86,207,131,0)",
                            "0 0 0 8px rgba(86,207,131,0.16)",
                            "0 0 0 0 rgba(86,207,131,0)",
                          ],
                    }
                  : {}
            }
            whileTap={awaitingApproval ? { scale: 0.94 } : undefined}
            transition={
              firing
                ? { duration: 0.18, ease: [0.22, 0.61, 0.36, 1] }
                : { duration: awaitingApproval ? 1.3 : 1.6, repeat: Infinity }
            }
            className="text-[11.5px] font-medium px-3.5 py-1.5 inline-flex items-center gap-1.5"
            style={{
              background: firing
                ? "rgba(86,207,131,0.78)"
                : "var(--color-accent, #56cf83)",
              color: "#0a0a0a",
              borderRadius: 4,
              cursor: awaitingApproval && !firing ? "pointer" : "default",
              outline: "none",
              transition: "background 200ms ease",
            }}
          >
            {firing && (
              <Loader2 size={11} strokeWidth={2.5} className="animate-spin" />
            )}
            {firing ? "Firing…" : "Approve · Execute"}
          </motion.button>
        </div>
      </div>
    </div>
  );
}

/**
 * Citation chip - matches the workspace one. [icon][n]↗ with a 1px
 * hairline, accent-green hover. Lives at the end of finding paragraphs.
 */
function CiteChip({
  n,
  src,
  label,
}: {
  n: number;
  src: string;
  label: string;
}) {
  return (
    <span
      className="ml-1.5 inline-flex items-baseline gap-1 px-1.5 py-0.5 align-baseline"
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 3,
        color: "rgba(255,255,255,0.72)",
        fontSize: 9.5,
        fontFamily: "Geist Mono, ui-monospace, monospace",
        letterSpacing: 0,
        lineHeight: 1,
      }}
      title={`${src} · ${label}`}
    >
      <SourceIcon id={src} size={9} tinted />
      <span className="tabular-nums">[{n}]</span>
      <span aria-hidden style={{ color: "rgba(255,255,255,0.42)" }}>
        ↗
      </span>
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Phase 4 - APPROVING.
// Centered typographic statement per action. No carousel dots.
// Step indicator lives in the bottom status strip (Action 02 of 03).
// ──────────────────────────────────────────────────────────────────────

function ApprovingCanvas({ elapsed }: { elapsed: number }) {
  const per = PHASE_DURATIONS.approving / ACTIONS.length;
  const idx = Math.min(ACTIONS.length - 1, Math.floor(elapsed / per));
  const local = elapsed - idx * per;
  const state: "firing" | "fired" = local > per - 1.4 ? "fired" : "firing";
  const action = ACTIONS[idx];

  return (
    <div className="h-full flex flex-col items-start justify-center px-12 max-w-[720px] mx-auto">
      <Eyebrow accent={state === "fired"}>
        {state === "fired" ? "Fired" : "Firing"}
      </Eyebrow>

      <AnimatePresence mode="wait">
        <motion.div
          key={`${idx}-${state}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.4, ease: [0.22, 0.61, 0.36, 1] }}
          className="mt-5"
        >
          <div className="flex items-baseline gap-3">
            <SourceWord src={action.src} label={action.src.toUpperCase()} />
            {state === "fired" && (
              <motion.span
                initial={{ scale: 0.6, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.28 }}
                className="inline-flex items-center justify-center"
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: 999,
                  background: "var(--color-accent, #56cf83)",
                  color: "#0a0a0a",
                }}
              >
                <Check size={9} strokeWidth={3} />
              </motion.span>
            )}
          </div>

          <h2
            className="mt-2 leading-[1.1]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              fontSize: "clamp(22px, 2.6vw, 30px)",
              color: "rgba(255,255,255,0.94)",
              letterSpacing: "-0.012em",
            }}
          >
            {action.title}.
          </h2>

          <div
            className="font-mono text-[11.5px] tabular-nums mt-3"
            style={{ color: "rgba(255,255,255,0.55)" }}
          >
            {action.target}
          </div>
        </motion.div>
      </AnimatePresence>

      <div
        className="mt-6 text-[11px] inline-flex items-center gap-2"
        style={{
          color:
            state === "fired"
              ? "var(--color-accent, #56cf83)"
              : "rgba(255,255,255,0.55)",
        }}
      >
        {state === "firing" && (
          <Loader2 size={12} className="animate-spin" />
        )}
        {state === "fired" && action.ref && (
          <>
            <span
              className="font-mono tabular-nums"
              style={{ color: "rgba(255,255,255,0.55)" }}
            >
              ref&nbsp;·&nbsp;{action.ref}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Phase 5 - CLOSED. Editorial closing statement + receipts.
// "Now try on your stack →" as a quiet inline link, not iridescent pill.
// ──────────────────────────────────────────────────────────────────────

function ClosedCanvas() {
  return (
    <div
      className="h-full grid"
      style={{
        gridTemplateColumns: "minmax(0, 1.15fr) minmax(0, 1fr)",
      }}
    >
      <div className="px-12 pt-8 pb-5 flex flex-col">
        <Eyebrow>Resolved</Eyebrow>

        <h2
          className="mt-3 leading-[1.06]"
          style={{
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: "clamp(28px, 3vw, 36px)",
            color: "rgba(255,255,255,0.94)",
            letterSpacing: "-0.014em",
          }}
        >
          Case resolved.
        </h2>

        <p
          className="mt-4 leading-[1.6] max-w-[42ch]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 14.5,
            color: "rgba(255,255,255,0.78)",
          }}
        >
          Three actions fired. Evidence packet submitted. Decision logged.
          The reply to Northwind&apos;s finance contact is in their inbox.
        </p>

        {/* The Landing CTA - quiet inline link with a hairline-arrow,
            NOT another iridescent pill. The page header already has
            those if visitors want to sign up. */}
        <Link
          to="/signup"
          className="mt-auto inline-flex items-baseline gap-2 hover:opacity-90 transition-opacity"
          style={{
            color: "var(--color-accent, #56cf83)",
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: 16,
            letterSpacing: "-0.005em",
            paddingBottom: 4,
            borderBottom: "1px solid var(--color-accent, #56cf83)",
            alignSelf: "flex-start",
          }}
        >
          Now try one of yours
          <ArrowRight size={14} style={{ transform: "translateY(2px)" }} />
        </Link>
      </div>

      <div
        className="pt-8 pb-5 pl-9 pr-12 flex flex-col"
        style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Receipts</Eyebrow>

        <ol className="mt-4 space-y-3.5">
          {ACTIONS.map((a) => (
            <li
              key={a.ref}
              className="grid"
              style={{
                gridTemplateColumns: "88px minmax(0,1fr) auto",
                columnGap: 16,
                paddingBottom: 12,
                borderBottom: "1px solid rgba(255,255,255,0.05)",
              }}
            >
              <SourceWord src={a.src} label={a.src.toUpperCase()} />
              <span
                className="text-[12.5px] leading-[1.45]"
                style={{ color: "rgba(255,255,255,0.85)" }}
              >
                {a.title}
              </span>
              <span
                className="font-mono text-[10.5px] tabular-nums"
                style={{ color: "rgba(255,255,255,0.55)" }}
              >
                {a.ref}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow - uppercase letterspaced section label, the only place we
// use ALL CAPS. Defaults to ink-faint; accent variant for the accent
// green moment.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({
  children,
  accent,
}: {
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <span
      className="text-[10px] uppercase"
      style={{
        color: accent
          ? "var(--color-accent, #56cf83)"
          : "rgba(255,255,255,0.45)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}
