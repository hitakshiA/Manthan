/**
 * InvestigationMemo - the LIVE investigation, editorial-memo direction.
 *
 * Pulls the landing's InvestigatingCanvas vocabulary onto the actual
 * dashboard SSE stream. Subscribes via useCaseEvents, extracts the
 * current source from the latest tool_call.arguments.query, swaps the
 * Spectral italic source name + 96 px hero glyph in/out as the agent
 * walks across sources, accumulates findings as marginalia on the right.
 *
 * Route: /app/investigation-memo/:id  → useParams() supplies the case id.
 *
 * Throwaway draft - production wires this into the Workspace as the
 * phase the operator sees while status === "investigating".
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useParams } from "react-router-dom";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { getSource } from "@/lib/sources";
import { useCaseEvents, type CaseEvent } from "@/lib/useCaseEvents";
import { useInvestigationNarrative } from "@/lib/useInvestigationNarrative";
// Re-export the citation deep-link helper so any future Coral-trace
// citation chip can import it from this file alongside the trace
// rendering primitives, instead of reaching into WorkspaceMemo. The
// helper itself lives in WorkspaceMemo because that's where the chip
// component is defined.
export { citationUrl } from "./WorkspaceMemo";

// Manthan's connected source taxonomy. The same set the existing
// InvestigationPlayground uses for source extraction.
const KNOWN_SOURCES = new Set([
  "stripe",
  "salesforce",
  "hubspot",
  "intercom",
  "zendesk",
  "slack",
  "notion",
  "posthog",
  "sentry",
  "datadog",
  "pagerduty",
  "linear",
  "gmail",
  "resend",
  "github",
  "mixpanel",
]);

export default function InvestigationMemo() {
  const { id } = useParams<{ id: string }>();
  const { events, isLive, isComplete } = useCaseEvents(id);

  // Toggle: "prose" = the editorial-memo prettified hero ("Manthan is
  // asking hubspot"), "coral" = the raw SQL feed with prettified
  // summaries paired alongside each query. The operator switches at
  // will; the data is the same, only the surface changes.
  const [mode, setMode] = useState<"prose" | "coral">("prose");

  const elapsed = useElapsed(events);
  const currentSource = useMemo(() => latestSource(events), [events]);
  const latestStep = useMemo(() => latestInteractiveEvent(events), [events]);
  const findings = useMemo(() => collectFindings(events), [events]);
  const coralSteps = useMemo(() => collectCoralSteps(events), [events]);
  // Live narrative + interim findings, synthesized server-side from
  // the last 25 events. Polls every 6s while the case is still
  // investigating; freezes once isComplete flips so we don't keep
  // calling the LLM after the brief lands.
  const { narrative, findings: interimFindings } = useInvestigationNarrative(
    id,
    { enabled: !isComplete },
  );
  // Full source set the LATEST coral_sql touched - drives the prose
  // canvas's multi-source asking line + the hero constellation. The
  // existing single `currentSource` is the FROM table; this includes
  // every JOIN / subquery / scalar-correlated source as well.
  const currentSources = useMemo(() => {
    const latest = coralSteps[0]; // newest-first ordering
    return latest?.sources ?? [];
  }, [coralSteps]);
  const stepCount = useMemo(
    () => events.filter((e) => e.type === "tool_call").length,
    [events],
  );

  // Customer + case label - derived from case_opened if present.
  const caseHeader = useMemo(() => deriveCaseHeader(events, id), [events, id]);

  return (
    // Mobile: container grows to fit content, AppShell main scrolls.
    // Desktop: viewport-locked card with internal column scrolls.
    <div
      className="lg:h-full w-full flex items-stretch px-2 sm:px-4 lg:px-6 py-3 sm:py-4 lg:py-6 min-h-full"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex flex-col flex-1 lg:min-h-0"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 6,
          color: "var(--color-ink-strong)",
          // overflow:hidden on lg only; mobile lets the stack grow.
          overflow: undefined,
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        }}
      >
        <HeaderStrip
          caseId={caseHeader.shortId}
          customer={caseHeader.customer}
          elapsed={elapsed}
          stepCount={stepCount}
          isLive={isLive}
          isComplete={isComplete}
          mode={mode}
          onToggleMode={() =>
            setMode((m) => (m === "prose" ? "coral" : "prose"))
          }
        />

        {/* Conditional canvas - no AnimatePresence at this level. The
            opacity fade happens via a single keyed motion.div that
            re-mounts when mode changes; React unmounts the old one
            cleanly so we never get a phantom prose canvas behind coral.
            (Earlier version used AnimatePresence mode="wait" with
            nested AnimatePresences inside each canvas, which silently
            errored and kept the prose tree mounted.) */}
        <motion.div
          key={mode}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
          className="relative flex-1 min-h-0"
        >
          {mode === "prose" ? (
            <Canvas
              currentSource={currentSource}
              currentSources={currentSources}
              latestSummary={latestStep?.summary ?? null}
              latestType={latestStep?.type ?? null}
              findings={findings}
              interimFindings={interimFindings}
              narrative={narrative}
              hasEvents={events.length > 0}
              isComplete={isComplete}
            />
          ) : (
            <CoralCanvas
              steps={coralSteps}
              isComplete={isComplete}
              currentSource={currentSource}
            />
          )}
        </motion.div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// HeaderStrip - case identity + live elapsed clock.
// ──────────────────────────────────────────────────────────────────────

function HeaderStrip({
  caseId,
  customer,
  elapsed,
  stepCount,
  isLive,
  isComplete,
  mode,
  onToggleMode,
}: {
  caseId: string;
  customer: string;
  elapsed: string;
  stepCount: number;
  isLive: boolean;
  isComplete: boolean;
  mode: "prose" | "coral";
  onToggleMode: () => void;
}) {
  const phase = isComplete ? "Brief ready" : isLive ? "Investigating" : "-";
  const phaseColor = isComplete
    ? "var(--color-accent)" // accent green
    : "var(--color-amber)"; // amber for active

  return (
    <header
      className="flex items-center px-9 shrink-0"
      style={{
        height: 56,
        borderBottom: "1px solid var(--color-rule-soft)",
        background: "var(--color-bg)",
      }}
    >
      <span
        className="font-mono text-[13px] uppercase tabular-nums"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.16em",
        }}
      >
        CASE {caseId}
      </span>

      <span
        className="mx-3"
        style={{ color: "var(--color-rule-strong)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[15px]"
        style={{
          color: "var(--color-ink)",
          letterSpacing: "0.005em",
        }}
      >
        {customer}
      </span>

      <span
        className="mx-4"
        style={{ color: "var(--color-rule-strong)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="font-mono text-[12.5px] tabular-nums"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.06em",
        }}
        title="elapsed wall-clock since the case opened"
      >
        ELAPSED {elapsed} · {String(stepCount).padStart(2, "0")} STEPS
      </span>

      <div className="ml-auto inline-flex items-center gap-5">
        <CoralToggle mode={mode} onToggle={onToggleMode} />

        <span
          className="text-[12.5px] uppercase inline-flex items-center gap-2"
          style={{
            color: phaseColor,
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          {!isComplete && (
            <motion.span
              animate={{ opacity: [0.3, 0.95, 0.3] }}
              transition={{ duration: 1.4, repeat: Infinity }}
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: 999,
                background: phaseColor,
              }}
              aria-hidden
            />
          )}
          {phase}
        </span>
      </div>
    </header>
  );
}

/**
 * Coral toggle - small icon button in the header. Active state has a
 * green hairline ring + slight glow on the coral glyph; inactive state
 * is ghosted so the icon reads as "available, not on."
 */
export function CoralToggle({
  mode,
  onToggle,
}: {
  mode: "prose" | "coral";
  onToggle: () => void;
}) {
  const active = mode === "coral";
  // Suppress the first-time hint after the operator clicks Coral once.
  // localStorage keeps that suppression sticky across navigations + cases,
  // so the nudge only appears for users who haven't discovered the panel.
  const [seen, setSeen] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(CORAL_HINT_KEY) === "1";
  });
  const showHint = !active && !seen;

  function handleClick() {
    if (!seen) {
      try {
        window.localStorage.setItem(CORAL_HINT_KEY, "1");
      } catch {
        /* private mode etc - just ignore */
      }
      setSeen(true);
    }
    onToggle();
  }

  return (
    <div className="inline-flex items-center" style={{ gap: 10 }}>
      {showHint && (
        <span
          className="inline-flex items-center select-none"
          style={{
            gap: 6,
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: 12.5,
            color: "var(--color-accent, #56cf83)",
            letterSpacing: "-0.003em",
            animation: "coral-hint-breathe 2.6s ease-in-out infinite",
          }}
          aria-hidden
        >
          watch the queries
          <span style={{ fontSize: 13, lineHeight: 1 }}>→</span>
        </span>
      )}
      <button
        type="button"
        onClick={handleClick}
        className="relative inline-flex items-center gap-2 outline-none transition-opacity"
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "4px 8px 4px 4px",
          borderRadius: 4,
        }}
        title={
          active
            ? "Coral SQL view is on - click to return to the prettified summary"
            : "Show the raw Coral SQL the agent is running"
        }
        aria-pressed={active}
      >
        {showHint && (
          <span
            aria-hidden
            className="absolute pointer-events-none"
            style={{
              left: 0,
              top: 0,
              width: 34,
              height: 34,
              borderRadius: 6,
              animation: "coral-hint-pulse 1.8s ease-out infinite",
            }}
          />
        )}
        <span
          className="inline-flex items-center justify-center transition-all"
          style={{
            width: 26,
            height: 26,
            borderRadius: 4,
            background: active ? "var(--color-accent-soft)" : "var(--color-rule-soft)",
            border: active
              ? "1px solid var(--color-accent-line)"
              : showHint
                ? "1px solid var(--color-accent-line)"
                : "1px solid var(--color-rule-soft)",
          }}
        >
          <img
            src="/coral-button.png"
            alt=""
            width={18}
            height={18}
            style={{
              opacity: active ? 1 : showHint ? 0.92 : 0.62,
              filter: active || showHint
                ? "drop-shadow(0 0 6px var(--color-accent-line))"
                : "none",
              transition: "opacity 200ms ease, filter 200ms ease",
            }}
          />
        </span>
        <span
          className="text-[11px] uppercase tabular-nums"
          style={{
            color: active
              ? "var(--color-accent, #56cf83)"
              : showHint
                ? "var(--color-accent, #56cf83)"
                : "var(--color-ink-faint)",
            letterSpacing: "0.18em",
            fontWeight: 500,
          }}
        >
          coral
        </span>
      </button>
      <style>{`
        @keyframes coral-hint-pulse {
          0%   { box-shadow: 0 0 0 0 var(--color-accent-line, rgba(86,207,131,0.55)); opacity: 1; }
          100% { box-shadow: 0 0 0 12px rgba(86,207,131,0); opacity: 0; }
        }
        @keyframes coral-hint-breathe {
          0%, 100% { opacity: 0.55; transform: translateX(0); }
          50%      { opacity: 1;    transform: translateX(2px); }
        }
      `}</style>
    </div>
  );
}

const CORAL_HINT_KEY = "manthan:coral-hint-seen";

// ──────────────────────────────────────────────────────────────────────
// Canvas - landing's InvestigatingCanvas layout, wired to live events.
// ──────────────────────────────────────────────────────────────────────

function Canvas({
  currentSource,
  currentSources,
  latestSummary,
  latestType,
  findings,
  interimFindings,
  narrative,
  hasEvents,
  isComplete,
}: {
  currentSource: string | null;
  currentSources: string[];
  latestSummary: string | null;
  latestType: string | null;
  findings: { src: string | null; text: string }[];
  /** Live LLM-derived findings from tool_results, surfaced while the
   *  agent hasn't yet committed formal record_finding events. */
  interimFindings: string[];
  /** 2-paragraph live narrative of agent activity, refreshed every 6s. */
  narrative: string | null;
  hasEvents: boolean;
  isComplete: boolean;
}) {
  // Multi-source headline. Three states:
  //  • 1 source     → "Manthan is asking <source>."
  //  • 2-3 sources  → "Manthan is cross-referencing <a>, <b>, and <c>."
  //  • 4+ sources   → "Manthan is cross-referencing <primary> with N other sources."
  // headlineKey is what AnimatePresence keys on, so it re-runs the
  // motion when the source set materially changes.
  const sourceCount = currentSources.length;
  const headlineKey = currentSources.join("|") || currentSource || "_";

  return (
    <div className="lg:h-full grid lg:overflow-hidden grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      {/* LEFT - typographic statement, currently-asked source */}
      <div className="px-5 sm:px-8 lg:px-14 pt-6 sm:pt-10 lg:pt-12 pb-6 lg:pb-8 flex flex-col">
        <Eyebrow accent={!isComplete}>
          {isComplete ? "Investigation complete" : "Investigating"}
        </Eyebrow>

        {/* Big Spectral statement */}
        <h2
          className="mt-5 leading-[1.12]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(28px, 2.8vw, 36px)",
            color: "var(--color-ink-strong)",
            letterSpacing: "-0.012em",
          }}
        >
          {hasEvents ? (
            <AnimatePresence mode="wait">
              <motion.span
                key={headlineKey}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.34, ease: [0.22, 0.61, 0.36, 1] }}
                style={{ display: "inline-block" }}
              >
                <Headline
                  sources={currentSources}
                  fallback={currentSource}
                  sourceCount={sourceCount}
                />
              </motion.span>
            </AnimatePresence>
          ) : (
            <em style={{ fontStyle: "italic", color: "var(--color-ink-muted)" }}>
              Waiting for the first event…
            </em>
          )}
        </h2>

        {/* Live narrative - synthesized server-side from the last 25
            events. 2 paragraphs of plain-English story: what the
            agent has done so far, what it's doing now. Falls back to
            the prettifier's one-line summary while the first
            narrative is loading. */}
        <div className="mt-4 min-h-[44px] max-w-[52ch]">
          <AnimatePresence mode="wait">
            <motion.div
              key={narrative ? `n-${narrative.slice(0, 32)}` : `l-${latestSummary ?? "empty"}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.32, delay: 0.04 }}
              className="text-[15.5px] leading-[1.55] space-y-3"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "normal",
                color: "var(--color-ink)",
                letterSpacing: "-0.003em",
              }}
            >
              {narrative ? (
                narrative.split(/\n{2,}/).map((p, i) => (
                  <p key={i}>{p}</p>
                ))
              ) : latestSummary ? (
                <p>{latestSummary}</p>
              ) : (
                <p style={{ color: "var(--color-ink-faint)" }}>
                  Reading the first events…
                </p>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Hero - source constellation. When the query touches one
            source, render the big primary glyph (old behavior). When
            it joins across N sources, render the primary at center +
            up to 7 secondary glyphs in a halo around it, animating
            in as fresh sources land. */}
        <div
          className="mt-12 mb-auto flex items-center"
          style={{ minHeight: 144 }}
        >
          <SourceConstellation sources={currentSources} />
        </div>

        {/* Status line. Single source → "reading <X> records". Multi
            → "cross-checking <primary> against <N> sources". */}
        <div>
          <AnimatePresence mode="wait">
            {!isComplete && hasEvents && currentSource ? (
              <motion.div
                key={`p-${headlineKey}-${latestType}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="flex items-baseline gap-2 text-[12px]"
                style={{
                  color: "var(--color-ink-faint)",
                  letterSpacing: "0.04em",
                }}
              >
                <motion.span
                  animate={{ opacity: [0.3, 0.92, 0.3] }}
                  transition={{ duration: 1.4, repeat: Infinity }}
                >
                  {latestType === "reflexion"
                    ? "reflecting"
                    : sourceCount > 1
                      ? "cross-checking"
                      : "reading"}
                </motion.span>
                <span>
                  {sourceCount > 1
                    ? `${currentSource} against ${sourceCount - 1} other source${sourceCount - 1 === 1 ? "" : "s"}`
                    : `${currentSource} records`}
                </span>
              </motion.div>
            ) : isComplete ? (
              <motion.div
                key="done"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-[12.5px] uppercase"
                style={{
                  color: "var(--color-accent, #56cf83)",
                  letterSpacing: "0.20em",
                  fontWeight: 500,
                }}
              >
                Brief drafted - see workspace
              </motion.div>
            ) : (
              <motion.div
                key="waiting"
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.55 }}
                className="text-[12px] uppercase"
                style={{
                  color: "rgba(255,255,255,0.4)",
                  letterSpacing: "0.20em",
                }}
              >
                Listening for events…
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* RIGHT - findings as editorial marginalia. Formal findings
          (record_finding events) take priority. Until the agent
          commits any, we show LLM-derived interim findings - concrete
          facts the agent has surfaced from tool_results, with a small
          "in flight" caveat so the operator knows these aren't yet
          claims-with-citations. */}
      <div
        className="
          pt-8 lg:pt-12 pb-6 lg:pb-8
          px-5 sm:px-8 lg:pl-11 lg:pr-14
          flex flex-col
          border-t lg:border-t-0 lg:border-l
        "
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <Eyebrow>
          {findings.length > 0 ? "Findings" : "Surfacing"}
        </Eyebrow>

        <ol className="mt-7 space-y-5 flex-1 lg:min-h-0 lg:overflow-y-auto">
          <AnimatePresence initial={false}>
            {findings.length > 0 ? (
              findings.map((f, i) => {
                const isLatest = i === 0;
                return (
                  <motion.li
                    key={`${f.src}-${i}-${f.text.slice(0, 32)}`}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: isLatest ? 1 : 0.6, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.4 }}
                    className="grid"
                    style={{
                      gridTemplateColumns: "96px minmax(0,1fr)",
                      columnGap: 16,
                    }}
                  >
                    <SourceWord
                      src={f.src ?? ""}
                      label={(f.src ?? "agent").toUpperCase()}
                    />
                    <span
                      className="text-[14.5px] leading-[1.55]"
                      style={{
                        color: isLatest
                          ? "var(--color-ink-strong)"
                          : "var(--color-ink-muted)",
                        fontWeight: isLatest ? 500 : 400,
                      }}
                    >
                      {f.text}
                    </span>
                  </motion.li>
                );
              })
            ) : interimFindings.length > 0 ? (
              // No per-item enter animation here: the narrative endpoint
              // refreshes the whole findings array every 6s, and
              // AnimatePresence + stagger delays would leave items
              // stuck mid-fade on each refresh. Plain rendering keeps
              // them readable; the editorial typography carries the
              // motion implicitly when new items appear.
              <li key="interim-block" className="contents">
                <div
                  className="text-[11.5px] uppercase pb-1"
                  style={{
                    color: "var(--color-ink-faint)",
                    letterSpacing: "0.18em",
                    fontFamily: "Geist Mono, ui-monospace, monospace",
                  }}
                >
                  In flight · not yet committed
                </div>
                {interimFindings.map((f, i) => (
                  <div
                    key={`interim-${i}-${f.slice(0, 24)}`}
                    className="grid"
                    style={{
                      gridTemplateColumns: "20px minmax(0,1fr)",
                      columnGap: 12,
                    }}
                  >
                    <span
                      className="text-[13px] tabular-nums pt-[2px]"
                      style={{
                        color: "var(--color-ink-faint)",
                        fontFamily: "Spectral, serif",
                        fontStyle: "italic",
                      }}
                    >
                      {String(i + 1).padStart(2, "0")}.
                    </span>
                    <span
                      className="text-[14.5px] leading-[1.55]"
                      style={{
                        color: "var(--color-ink)",
                        fontFamily: "Spectral, serif",
                      }}
                    >
                      {f}
                    </span>
                  </div>
                ))}
              </li>
            ) : (
              <motion.li
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.55 }}
                className="text-[14px] italic"
                style={{
                  fontFamily: "Spectral, serif",
                  color: "var(--color-ink-faint)",
                }}
              >
                The agent hasn't surfaced anything yet. Facts will land
                here as queries return data.
              </motion.li>
            )}
          </AnimatePresence>
        </ol>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// CoralCanvas - raw SQL feed paired with prettified summaries.
//
// Each row is one tool_call: a header line with [SOURCE BYLINE] + the
// prettified prose, then a code block with the actual SQL query (or the
// args for non-SQL tools like record_finding / conclude / ask_human).
// Latest at top. Older rows decay to 60% opacity. Newly-arrived rows
// fade in with a subtle slide; React's reordering happens because the
// list is fed reverse-chronologically.
// ──────────────────────────────────────────────────────────────────────

export function CoralCanvas({
  steps,
  isComplete,
  currentSource,
}: {
  steps: CoralStep[];
  isComplete: boolean;
  currentSource: string | null;
}) {
  // Track which rows are expanded. Set of step seq numbers - using seq
  // rather than index so reorder via newer events doesn't toggle the
  // wrong row.
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  function toggle(seq: number) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });
  }

  // Fix #1: the subtitle switches verb based on isComplete. "Currently
  // reading X" is the live phrasing; once the agent's done, the same
  // source becomes "last source touched."
  const subtitle = (() => {
    if (steps.length === 0) return "Waiting for the first query…";
    const base = `${steps.length} ${steps.length === 1 ? "query" : "queries"} executed`;
    if (!currentSource) return base;
    return isComplete
      ? `${base} · last source touched: ${currentSource}`
      : `${base} · currently reading ${currentSource}`;
  })();

  return (
    <div className="lg:h-full flex flex-col lg:overflow-hidden">
      <div className="px-5 sm:px-8 lg:px-14 pt-8 sm:pt-10 pb-5 flex items-baseline justify-between shrink-0 gap-3 flex-wrap">
        <div className="flex items-baseline gap-4">
          <Eyebrow accent={!isComplete}>
            {isComplete ? "Coral · trace" : "Coral · live"}
          </Eyebrow>
          <span
            className="text-[14px]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "normal",
              color: "var(--color-ink-muted)",
            }}
          >
            {subtitle}
          </span>
        </div>
        <span
          className="font-mono text-[11px] uppercase"
          style={{
            color: "var(--color-ink-faint)",
            letterSpacing: "0.16em",
          }}
        >
          newest first · click any row to expand
        </span>
      </div>

      <ol className="flex-1 lg:min-h-0 lg:overflow-y-auto px-5 sm:px-8 lg:px-14 pb-10 space-y-5">
        <AnimatePresence initial={false}>
          {steps.length === 0 ? (
            <motion.li
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.55 }}
              className="text-[14px] italic"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink-faint)",
              }}
            >
              No queries have been issued yet. The first Coral SQL call will
              appear here the instant the agent fires it.
            </motion.li>
          ) : (
            steps.map((s, i) => {
              const isLatest = i === 0;
              return (
                <motion.li
                  key={`${s.seq}-${s.tool}`}
                  layout
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: isLatest ? 1 : 0.66, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4, ease: [0.22, 0.61, 0.36, 1] }}
                >
                  <CoralRow
                    step={s}
                    isLatest={isLatest}
                    isLive={!isComplete}
                    isExpanded={expanded.has(s.seq)}
                    onToggle={() => toggle(s.seq)}
                  />
                </motion.li>
              );
            })
          )}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function CoralRow({
  step,
  isLatest,
  isLive,
  isExpanded,
  onToggle,
}: {
  step: CoralStep;
  isLatest: boolean;
  isLive: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  // Fix #2: only the topmost row pulses, and only while the
  // investigation is in flight. Once isComplete this dot disappears.
  const showLivePulse = isLatest && isLive;

  return (
    <article
      onClick={onToggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
      className="grid cursor-pointer transition-colors"
      style={{
        // Wider left column (was 118px) so the longest byline -
        // DESCRIBE_TABLE - fits without colliding with the prose. We
        // also short-label the tools (see byline()) so the column
        // doesn't need to scale to "CORAL_DESCRIBE_TABLE" length.
        gridTemplateColumns: "150px minmax(0, 1fr)",
        columnGap: 24,
        padding: "4px 10px 8px",
        margin: "0 -10px",
        borderRadius: 4,
        background: isExpanded ? "var(--color-surface-2)" : "transparent",
      }}
    >
      {/* LEFT - byline + (extra source icons) + sequence + timestamp */}
      <div className="flex flex-col gap-1 pt-[3px] min-w-0 overflow-hidden">
        <div className="inline-flex items-baseline gap-2 min-w-0">
          <SourceWord
            src={step.source ?? ""}
            label={byline(step.source, step.tool)}
          />
          {showLivePulse && (
            <motion.span
              animate={{ opacity: [0.25, 1, 0.25] }}
              transition={{ duration: 1.4, repeat: Infinity }}
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: 999,
                background: "var(--color-accent, #56cf83)",
                boxShadow: "0 0 6px rgba(86,207,131,0.7)",
                transform: "translateY(-1px)",
                flexShrink: 0,
              }}
              aria-hidden
              title="live - agent is on this step"
            />
          )}
        </div>
        {/* Secondary sources - every OTHER known source this query
            touched via JOIN or scalar subquery. Tiny brand-tinted
            icons, max 6 shown + "+N" overflow. Hides when there's
            only the primary. */}
        {step.sources.length > 1 && (
          <ExtraSources sources={step.sources.slice(1)} />
        )}
        <span
          className="font-mono text-[10.5px] tabular-nums"
          style={{
            color: "var(--color-ink-faint)",
            letterSpacing: "0.06em",
          }}
        >
          #{String(step.seq).padStart(2, "0")} · {step.localTime}
        </span>
      </div>

      {/* RIGHT - prose then code (and on expand, the full event JSON) */}
      <div className="flex flex-col gap-3 min-w-0">
        {/* Prettified prose - same line the prose-view shows */}
        <div
          className="text-[14.5px] leading-[1.45]"
          style={{
            color: isLatest
              ? "var(--color-ink-strong)"
              : "var(--color-ink)",
            fontWeight: isLatest ? 500 : 400,
          }}
        >
          <CoralStepProse step={step} />
        </div>

        {/* Code block - Fix #3: pre-wrap so long SQL breaks at natural
            boundaries instead of forcing a horizontal scroll. Long
            identifiers stay on one line via word-break: keep-all. */}
        <pre
          style={{
            background: "rgba(0,0,0,0.40)",
            border: "1px solid var(--color-rule-soft)",
            borderRadius: 4,
            padding: "12px 14px",
            margin: 0,
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 12.5,
            lineHeight: 1.55,
            color: "var(--color-ink)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            overflowWrap: "anywhere",
          }}
        >
          {renderCoralBody(step)}
        </pre>

        {/* Fix #4: expand panel - full event JSON for the power user.
            Triggered by clicking the row. Slides down from the code
            block with a subtle opacity+y animation. */}
        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              key="expand"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
              style={{ overflow: "hidden" }}
            >
              <div
                className="mt-1"
                style={{
                  borderTop: "1px solid var(--color-rule-soft)",
                  paddingTop: 12,
                }}
              >
                <div
                  className="text-[10.5px] uppercase mb-2"
                  style={{
                    color: "var(--color-ink-faint)",
                    letterSpacing: "0.18em",
                    fontWeight: 500,
                  }}
                >
                  Raw event · seq #{step.seq} · {step.tool}
                </div>
                <pre
                  style={{
                    background: "rgba(0,0,0,0.55)",
                    border: "1px solid var(--color-rule-soft)",
                    borderRadius: 4,
                    padding: "12px 14px",
                    margin: 0,
                    fontFamily: "Geist Mono, ui-monospace, monospace",
                    fontSize: 11.5,
                    lineHeight: 1.6,
                    color: "var(--color-ink)",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {JSON.stringify(
                    {
                      seq: step.seq,
                      tool: step.tool,
                      source: step.source,
                      summary: step.summary,
                      created_at: step.createdAt,
                      data: step.rawData,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </article>
  );
}

/**
 * Render the body of a Coral step. For SQL tool calls we colorise
 * keywords lightly; for other tools we render the args as readable
 * key:value pairs.
 */
function renderCoralBody(step: CoralStep): React.ReactNode {
  if (step.sql) {
    return formatSql(step.sql);
  }
  if (step.tool === "record_finding") {
    return (
      <>
        <span style={{ color: "var(--color-accent)" }}>record_finding</span>
        {"("}
        {"\n  "}
        <span style={{ color: "var(--color-ink-muted)" }}>text</span>:{" "}
        <span style={{ color: "var(--color-ink-strong)" }}>
          {JSON.stringify(step.argsPreview.text)}
        </span>
        {step.argsPreview.citations
          ? `,\n  citations: [${(step.argsPreview.citations as number[]).join(", ")}]`
          : ""}
        {step.argsPreview.confidence !== undefined
          ? `,\n  confidence: ${step.argsPreview.confidence}`
          : ""}
        {"\n)"}
      </>
    );
  }
  if (step.tool === "conclude") {
    return (
      <>
        <span style={{ color: "var(--color-accent)" }}>conclude</span>
        {"("}
        {"\n  "}
        <span style={{ color: "var(--color-ink-muted)" }}>decision_action</span>
        : {JSON.stringify(step.argsPreview.decision_action)}
        {"\n  "}
        <span style={{ color: "var(--color-ink-muted)" }}>
          decision_amount_minor
        </span>
        : {String(step.argsPreview.decision_amount_minor)}
        {"\n)"}
      </>
    );
  }
  if (step.tool === "ask_human") {
    return (
      <>
        <span style={{ color: "var(--color-accent)" }}>ask_human</span>
        {"("}
        {"\n  "}
        <span style={{ color: "var(--color-ink-muted)" }}>question</span>:{" "}
        {JSON.stringify(step.argsPreview.question)}
        {"\n)"}
      </>
    );
  }
  // Fallback: show the raw args as JSON pretty.
  return JSON.stringify(step.argsPreview, null, 2);
}

/**
 * Light SQL syntax-tinting. Splits on whitespace and styles keywords
 * green, identifiers white, string literals amber. Not a parser - just
 * enough to give the eye a foothold.
 */
function formatSql(sql: string): React.ReactNode {
  const KEYWORDS = new Set([
    "SELECT",
    "FROM",
    "WHERE",
    "JOIN",
    "LEFT",
    "RIGHT",
    "INNER",
    "OUTER",
    "ON",
    "AS",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "NULL",
    "LIMIT",
    "ORDER",
    "BY",
    "GROUP",
    "HAVING",
    "DESC",
    "ASC",
    "UNION",
    "ALL",
    "DISTINCT",
    "WITH",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
  ]);

  // Tokenize SQL into runs: keywords, strings, identifiers, punctuation.
  // We use a regex with a capture group per kind. Simple but covers
  // ~95% of typical Coral SQL.
  const tokens: React.ReactNode[] = [];
  const re =
    /('(?:[^'\\]|\\.)*')|("(?:[^"\\]|\\.)*")|([A-Za-z_][A-Za-z0-9_.]*)|(\s+)|([(),;])/g;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(sql)) !== null) {
    const [, sStr, dStr, ident, ws, punct] = m;
    if (sStr) {
      tokens.push(
        <span key={key++} style={{ color: "var(--color-amber)" }}>
          {sStr}
        </span>,
      );
    } else if (dStr) {
      tokens.push(
        <span key={key++} style={{ color: "var(--color-amber)" }}>
          {dStr}
        </span>,
      );
    } else if (ident) {
      if (KEYWORDS.has(ident.toUpperCase())) {
        tokens.push(
          <span
            key={key++}
            style={{
              color: "var(--color-accent)",
              fontWeight: 500,
            }}
          >
            {ident}
          </span>,
        );
      } else if (ident.includes(".")) {
        // Schema-qualified identifier like stripe.disputes - color the
        // schema part in info-blue, the table in normal ink.
        const [src, tbl] = ident.split(".");
        tokens.push(
          <span key={key++}>
            <span style={{ color: "var(--color-info)" }}>{src}</span>
            <span style={{ color: "var(--color-ink-muted)" }}>.</span>
            <span style={{ color: "var(--color-ink-strong)" }}>{tbl}</span>
          </span>,
        );
      } else {
        tokens.push(
          <span key={key++} style={{ color: "var(--color-ink)" }}>
            {ident}
          </span>,
        );
      }
    } else if (ws) {
      tokens.push(ws);
    } else if (punct) {
      tokens.push(
        <span key={key++} style={{ color: "var(--color-ink-faint)" }}>
          {punct}
        </span>,
      );
    }
  }
  return <>{tokens}</>;
}

// ──────────────────────────────────────────────────────────────────────
// Editorial primitives.
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
      className="text-[12.5px] uppercase inline-flex items-baseline gap-2"
      style={{
        color: accent
          ? "var(--color-accent, #56cf83)"
          : "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {accent && (
        <motion.span
          animate={{ opacity: [0.3, 0.95, 0.3] }}
          transition={{ duration: 1.4, repeat: Infinity }}
          style={{
            display: "inline-block",
            width: 5,
            height: 5,
            borderRadius: 999,
            background: "var(--color-accent, #56cf83)",
            transform: "translateY(-1px)",
          }}
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}

function SourceWord({ src, label }: { src: string; label: string }) {
  return (
    <span
      className="inline-flex items-baseline gap-2 text-[11.5px] min-w-0 max-w-full"
      style={{
        color: "var(--color-ink-muted)",
        letterSpacing: "0.16em",
      }}
    >
      {src && (
        <span
          aria-hidden
          className="shrink-0"
          style={{ display: "inline-flex", transform: "translateY(2px)" }}
        >
          <SourceIcon id={src} size={11} tinted />
        </span>
      )}
      <span
        className="truncate"
        style={{ minWidth: 0 }}
      >
        {label}
      </span>
    </span>
  );
}

/**
 * Headline - renders the "Manthan is asking …" phrase, scaling its
 * shape with how many sources the current query touches.
 *
 *   0 sources (non-SQL tool): "Manthan is working on it."
 *   1 source:                  "Manthan is asking <source>."
 *   2 sources:                  "Manthan is cross-referencing <a> and <b>."
 *   3 sources:                  "Manthan is cross-referencing <a>, <b>, and <c>."
 *   4+ sources:                 "Manthan is cross-referencing <primary> with <N> other sources."
 */
function Headline({
  sources,
  fallback,
  sourceCount,
}: {
  sources: string[];
  fallback: string | null;
  sourceCount: number;
}) {
  // Inline source name rendered with the brand logo + capitalized
  // canonical name + brand-color text. The logo is the same SVG path
  // the source catalog already carries (from simple-icons), inlined as
  // an SVG so it lives on the typographic baseline beside the name
  // instead of needing a separate box.
  const src = (slug: string) => {
    const meta = getSource(slug);
    const hex = meta?.simpleIcon?.hex;
    const EXTREME = new Set(["000000", "FFFFFF", "FDFDFD", "FEFEFE"]);
    const isExtreme = !hex || EXTREME.has(hex.toUpperCase());
    const fill = isExtreme ? "currentColor" : `#${hex}`;
    const viewBox = meta?.simpleIcon?.viewBox ?? "0 0 24 24";
    const path = meta?.simpleIcon?.path;

    return (
      <span
        key={slug}
        className="inline-flex items-center"
        style={{
          fontStyle: "normal",
          fontWeight: 500,
          color: brandColorFor(slug),
          letterSpacing: "-0.012em",
          gap: "0.34em",
          // Pull the row baseline-ish so the glyph sits inside the line.
          verticalAlign: "baseline",
        }}
      >
        {path && (
          <svg
            width="0.95em"
            height="0.95em"
            viewBox={viewBox}
            fill={fill}
            aria-hidden
            style={{
              flexShrink: 0,
              // Drop a hair from baseline so the cap-height of the glyph
              // visually centers against the lowercase serifs.
              transform: "translateY(0.05em)",
            }}
          >
            <path d={path} />
          </svg>
        )}
        {prettySourceName(slug)}
      </span>
    );
  };

  if (sourceCount === 0) {
    if (fallback) {
      return <>Manthan is asking {src(fallback)}</>;
    }
    return <>Manthan is working on it</>;
  }
  if (sourceCount === 1) {
    return <>Manthan is asking {src(sources[0])}</>;
  }
  if (sourceCount === 2) {
    return (
      <>
        Manthan is cross-referencing {src(sources[0])} and {src(sources[1])}
      </>
    );
  }
  if (sourceCount === 3) {
    return (
      <>
        Manthan is cross-referencing {src(sources[0])}, {src(sources[1])}, and{" "}
        {src(sources[2])}
      </>
    );
  }
  // 4+
  const others = sourceCount - 1;
  return (
    <>
      Manthan is cross-referencing {src(sources[0])} with{" "}
      <span
        style={{
          fontStyle: "normal",
          fontWeight: 500,
          color: "var(--color-accent)",
        }}
      >
        {others} other sources
      </span>
    </>
  );
}

/**
 * Canonical display name for a source slug. Most brands are just title-
 * cased ("stripe" → "Stripe") but a handful use camelCase
 * ("hubspot" → "HubSpot", "github" → "GitHub").
 */
function prettySourceName(slug: string): string {
  const overrides: Record<string, string> = {
    hubspot: "HubSpot",
    pagerduty: "PagerDuty",
    posthog: "PostHog",
    github: "GitHub",
    youtube: "YouTube",
    gitlab: "GitLab",
    snowflake: "Snowflake",
  };
  if (overrides[slug]) return overrides[slug];
  return slug.charAt(0).toUpperCase() + slug.slice(1);
}

/**
 * Brand hex for inline source name coloring. Pure-black / pure-white
 * brands (Notion, GitHub, Resend) fall through to ink-strong so they
 * stay legible against both light and dark backgrounds. Mid-range brand
 * hexes (Stripe purple, HubSpot orange, Intercom mint, Slack purple)
 * render in their actual color.
 */
function brandColorFor(slug: string): string {
  const meta = getSource(slug);
  const hex = meta?.simpleIcon?.hex;
  if (!hex) return "var(--color-ink-strong)";
  const EXTREME = new Set(["000000", "FFFFFF", "FDFDFD", "FEFEFE"]);
  if (EXTREME.has(hex.toUpperCase())) return "var(--color-ink-strong)";
  return `#${hex}`;
}

/**
 * SourceConstellation - hero visual for the multi-source asking state.
 *
 * Renders the touched sources as a horizontal row of equal-sized boxes
 * below the narrative text. Every source gets the same treatment - no
 * primary-vs-secondary hierarchy, no orbit - so the operator reads
 * "these N systems are being asked" at a glance.
 *
 * Each tile is 56x56 with the brand logo at 28px and the source name
 * below in mono caps. The primary (currently-active) source gets a
 * subtle accent ring so the reader knows which one the agent is
 * actively reading; the rest sit at 70% opacity.
 */
function SourceConstellation({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;
  const primary = sources[0];
  const visible = sources.slice(0, 8); // cap row at 8

  return (
    <div
      className="flex flex-wrap items-start gap-4"
      style={{ maxWidth: 720 }}
      aria-label={`${sources.length} sources touched: ${sources.join(", ")}`}
    >
      {visible.map((src) => {
        const isPrimary = src === primary;
        return (
            <div
              key={`box-${src}`}
              className="flex flex-col items-center gap-2"
              title={src}
              style={{ opacity: isPrimary ? 1 : 0.72 }}
            >
              <div
                className="inline-flex items-center justify-center"
                style={{
                  width: 88,
                  height: 88,
                  borderRadius: 8,
                  background: "var(--color-surface)",
                  border: isPrimary
                    ? "1px solid var(--color-accent-line)"
                    : "1px solid var(--color-rule-soft)",
                  boxShadow: isPrimary
                    ? "0 0 0 3px var(--color-accent-tint)"
                    : "none",
                  transition: "border-color 200ms ease, box-shadow 200ms ease",
                }}
              >
                <SourceIcon id={src} size={44} tinted />
              </div>
              <span
                className="text-[13.5px]"
                style={{
                  // Brand-color the label so the row reads as a
                  // panel of bylines. Primary at full opacity, others
                  // sit slightly muted so the eye lands on the live one.
                  color: brandColorFor(src),
                  opacity: isPrimary ? 1 : 0.72,
                  letterSpacing: "-0.003em",
                  fontFamily: "Spectral, serif",
                  fontWeight: 500,
                }}
              >
                {prettySourceName(src)}
              </span>
            </div>
          );
      })}
      {sources.length > visible.length && (
        <div
          className="flex flex-col items-center justify-center gap-2"
          style={{
            width: 88,
            height: 88,
            color: "var(--color-ink-muted)",
          }}
        >
          <span
            className="text-[18px] tabular-nums"
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontWeight: 500,
            }}
          >
            +{sources.length - visible.length}
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * CoralStepProse - the human-readable line that sits next to a Coral
 * trace row's SQL. Picks the best signal we have:
 *
 *   1. Real prettifier summary (if the worker has caught up AND
 *      didn't just write the generic `Calling coral_sql` fallback).
 *   2. Multi-source synthetic when the SQL touches ≥2 known sources -
 *      "Joining stripe with hubspot, intercom, notion, datadog and
 *      pagerduty" - derived from the step.sources list. Reads better
 *      than "Calling coral_sql" and stays useful while the prettifier
 *      catches up.
 *   3. Single-source synthetic - "Reading stripe records" /
 *      "Describing the stripe disputes table" - for short queries.
 *   4. Non-SQL tools fall back to a labelled "(prettifier pending)".
 */
function CoralStepProse({ step }: { step: CoralStep }) {
  const synthetic = describeStep(step);

  // Treat the prettifier's own fallback ("Calling coral_sql",
  // "Result from coral_sql") as no-summary so we render the multi-
  // source synthetic instead - it's strictly more useful.
  const summary = step.summary?.trim() ?? "";
  const isWeakSummary =
    !summary ||
    /^calling\s+\w+$/i.test(summary) ||
    /^result\s+from\s+\w+$/i.test(summary);

  if (!isWeakSummary) {
    return <span>{summary}</span>;
  }
  if (synthetic) {
    return <span>{synthetic}</span>;
  }
  return (
    <em
      className="italic"
      style={{
        fontFamily: "Spectral, serif",
        color: "var(--color-ink-faint)",
      }}
    >
      (prettifier pending)
    </em>
  );
}

/**
 * Derive a short prose description from a coral step's shape. Returns
 * null when we can't say anything more useful than the prettifier
 * fallback (then CoralStepProse falls through to "(prettifier
 * pending)").
 */
function describeStep(step: CoralStep): string | null {
  const tool = step.tool;
  if (tool === "coral_describe_table") {
    // The qualified_name lives in argsPreview for describe calls.
    const qn = (step.argsPreview as { qualified_name?: string })
      ?.qualified_name;
    if (qn) {
      const [src, tbl] = qn.split(".");
      if (src && tbl) {
        return `Describing the ${src} ${tbl.replace(/_/g, " ")} table`;
      }
    }
    return null;
  }
  if (tool === "coral_sql" && step.sources.length >= 2) {
    const [primary, ...rest] = step.sources;
    const list = formatSourceList(rest);
    return `Cross-checking ${primary} with ${list}`;
  }
  if (tool === "coral_sql" && step.sources.length === 1) {
    return `Reading ${step.sources[0]} records`;
  }
  if (tool === "coral_sql") {
    // No source extractable (probably a catalog query like
    // SELECT FROM coral.tables). Stay descriptive but generic.
    return "Surveying which systems hold customer history";
  }
  if (tool === "record_finding") {
    const text = (step.argsPreview as { text?: string })?.text;
    if (text) return `Logging: ${text.slice(0, 110)}`;
    return "Logging a finding";
  }
  if (tool === "conclude") {
    return "Concluding with a recommended decision";
  }
  if (tool === "ask_human") {
    return "Pausing to ask the operator";
  }
  if (tool === "amend_brief") {
    return "Amending the brief";
  }
  if (tool === "reply") {
    return "Replying to the operator";
  }
  return null;
}

/**
 * Join an array of source slugs as a comma+'and' list, deduplicated
 * by lower-case. Cap at 5 visible names + "and N more" so the line
 * doesn't run off.
 */
function formatSourceList(sources: string[]): string {
  if (sources.length === 0) return "-";
  if (sources.length === 1) return sources[0];
  if (sources.length === 2) return `${sources[0]} and ${sources[1]}`;
  if (sources.length <= 5) {
    return `${sources.slice(0, -1).join(", ")} and ${sources[sources.length - 1]}`;
  }
  return `${sources.slice(0, 4).join(", ")} and ${sources.length - 4} more`;
}

/**
 * ExtraSources - small brand-icon row for the OTHER sources a SQL
 * touched (subqueries, joins). Caps at 6 visible + "+N" overflow so a
 * 10-source join still fits in the gutter.
 */
function ExtraSources({ sources }: { sources: string[] }) {
  const VISIBLE = 6;
  const shown = sources.slice(0, VISIBLE);
  const overflow = Math.max(0, sources.length - VISIBLE);
  return (
    <div
      className="inline-flex items-center gap-1"
      style={{ marginTop: 2, flexWrap: "wrap" }}
      title={`also touched: ${sources.join(", ")}`}
    >
      {shown.map((s) => (
        <span
          key={s}
          aria-hidden
          style={{
            display: "inline-flex",
            opacity: 0.65,
          }}
        >
          <SourceIcon id={s} size={10} tinted />
        </span>
      ))}
      {overflow > 0 && (
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 9.5,
            color: "var(--color-ink-muted)",
            letterSpacing: "0.04em",
            marginLeft: 2,
          }}
        >
          +{overflow}
        </span>
      )}
    </div>
  );
}

/**
 * Short byline label for a Coral-trace row. The whole panel is the
 * Coral trace, so the `CORAL_` prefix is redundant noise - we strip
 * it. When `source` is set (extracted from the SQL), prefer it because
 * "STRIPE" reads as the actor faster than "SQL".
 *
 *   coral_sql              → "SQL"
 *   coral_describe_table   → "DESCRIBE"
 *   coral_list_catalogs    → "CATALOGS"
 *   record_finding         → "FINDING"
 *   conclude               → "CONCLUDE"
 *   ask_human              → "ASK HUMAN"
 */
function byline(source: string | null, tool: string | null | undefined): string {
  if (source) return source.toUpperCase();
  if (!tool) return "AGENT";
  const t = tool.toLowerCase();
  const map: Record<string, string> = {
    coral_sql: "SQL",
    coral_describe_table: "DESCRIBE",
    coral_list_catalogs: "CATALOGS",
    coral_list_tables: "TABLES",
    record_finding: "FINDING",
    conclude: "CONCLUDE",
    ask_human: "ASK HUMAN",
    amend_brief: "AMEND",
    reply: "REPLY",
  };
  if (map[t]) return map[t];
  // Generic fallback - drop "coral_" prefix and uppercase.
  return t.replace(/^coral_/, "").toUpperCase();
}

// ──────────────────────────────────────────────────────────────────────
// Derivation helpers - pull the "current source", "question line", and
// "findings list" out of the raw event stream.
// ──────────────────────────────────────────────────────────────────────

/**
 * Latest interactive event = the most recent tool_call / tool_result /
 * reflexion / agent_thought / finding_recorded. We use its prettifier
 * summary as the question line on the left column.
 */
function latestInteractiveEvent(events: CaseEvent[]): CaseEvent | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const t = events[i].type;
    if (
      t === "tool_call" ||
      t === "tool_result" ||
      t === "reflexion" ||
      t === "agent_thought" ||
      t === "finding_recorded"
    ) {
      return events[i];
    }
  }
  return null;
}

/**
 * Walks backwards through events looking for the most recent tool_call
 * whose `arguments.query` references a known source. Pattern: SQL FROM
 * or JOIN clauses like `stripe.disputes`, `hubspot.companies`. Returns
 * the source slug ("stripe", "hubspot", ...) or null.
 */
export function latestSource(events: CaseEvent[]): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type !== "tool_call") continue;
    const args = (e.data as { arguments?: { query?: string } } | undefined)
      ?.arguments;
    const q = stripSqlLiterals((args?.query || "").toLowerCase());
    // Pattern: <source>.<table> in FROM / JOIN positions.
    const re = /\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*\b/g;
    let m: RegExpExecArray | null;
    let lastInThisQuery: string | null = null;
    while ((m = re.exec(q)) !== null) {
      const src = m[1];
      if (KNOWN_SOURCES.has(src)) lastInThisQuery = src;
    }
    if (lastInThisQuery) return lastInThisQuery;
  }
  return null;
}

/**
 * Strip single- and double-quoted string literals from a SQL string so
 * the source-extraction regex doesn't false-match domains inside email
 * literals (e.g. `gmail.com` inside `'thatspacebiker@gmail.com'` looked
 * like a `gmail.com` table reference).
 *
 * We replace the contents with spaces (preserving length-ish) so any
 * subsequent positional logic (paren-balancing for top-level FROM
 * detection) still works approximately.
 */
function stripSqlLiterals(sql: string): string {
  return sql
    .replace(/'(?:[^'\\]|\\.)*'/g, (m) => " ".repeat(m.length))
    .replace(/"(?:[^"\\]|\\.)*"/g, (m) => " ".repeat(m.length));
}

interface FindingRow {
  src: string | null;
  text: string;
}

export interface CoralStep {
  seq: number;
  tool: string;            // coral_sql | record_finding | conclude | ask_human | …
  /** Primary source - the table after the first FROM clause (the table
   *  the query is actually scanning). null for non-SQL tools. */
  source: string | null;
  /** Every distinct known source touched by this query, in textual order
   *  (FROM + JOINs + subqueries + correlated SELECTs). Always includes
   *  `source` as the first element when source is non-null. Multi-source
   *  joins surface here so the byline can show "+ 9 sources". */
  sources: string[];
  summary: string | null;  // prettifier output for this event
  sql: string | null;      // raw query string for coral_sql, else null
  argsPreview: Record<string, unknown>; // for non-SQL tools
  localTime: string;       // HH:MM:SS in the user's locale
  rawData: Record<string, unknown>; // full event data for the expanded view
  createdAt: string;       // ISO string from the event
}

/**
 * Convert the event stream into one CoralStep per tool_call (reverse
 * chronological - newest first). Non-SQL tool calls get rendered too
 * with their args, so the operator sees the whole sequence: the
 * coral_sql reads, the record_findings the agent commits, and the
 * final conclude / ask_human.
 */
export function collectCoralSteps(events: CaseEvent[]): CoralStep[] {
  const out: CoralStep[] = [];
  for (const e of events) {
    if (e.type !== "tool_call") continue;
    const data = e.data as
      | {
          name?: string;
          arguments?: {
            query?: string;
            text?: string;
            citations?: number[];
            confidence?: number;
            decision_action?: string;
            decision_amount_minor?: number | null;
            question?: string;
          };
        }
      | undefined;
    const tool = data?.name ?? "coral_sql";
    const sql =
      tool === "coral_sql" || tool === "coral_describe_table"
        ? (data?.arguments?.query ?? null)
        : null;
    // Extract every known source the query touches (FROM, JOIN, scalar
    // subqueries, correlated SELECTs). Preserve textual order so the
    // primary FROM table - usually the agent's anchor table for this
    // query - ends up first.
    const sources = extractSources(sql);
    const primary = sources[0] ?? null;
    const local = new Date(e.created_at);
    const localTime = `${pad(local.getHours())}:${pad(local.getMinutes())}:${pad(
      local.getSeconds(),
    )}`;
    out.push({
      seq: e.seq,
      tool,
      source: primary,
      sources,
      summary: e.summary,
      sql,
      argsPreview: data?.arguments ?? {},
      localTime,
      rawData: e.data,
      createdAt: e.created_at,
    });
  }
  return out.reverse();
}

/**
 * Pull every distinct known source out of a SQL string in textual
 * order. A 10-source join (Salesforce FROM + Intercom/Zendesk/HubSpot/
 * Datadog/PagerDuty/Sentry/Notion/PostHog/Slack scalar subqueries)
 * returns all ten - the byline can then show "SALESFORCE +9" instead
 * of pretending only Salesforce was touched.
 *
 * Anchor the primary on the FIRST `FROM table` token when present,
 * because that's the table the query actually scans; the rest are
 * subqueries / joined dimensions.
 */
function extractSources(sql: string | null): string[] {
  if (!sql) return [];
  // Strip quoted string literals first so domains inside email/URL
  // literals don't false-match (e.g. 'thatspacebiker@gmail.com' was
  // matching as a `gmail.com` source reference).
  const q = stripSqlLiterals(sql.toLowerCase());
  const seen = new Set<string>();
  const out: string[] = [];

  // First, prefer the table named in the outermost FROM clause as
  // the primary source. Match `from <source>.<table>` not inside a
  // subquery - i.e. the LAST FROM at the top level. (We approximate
  // "top level" by taking the FROM that's not immediately preceded by
  // an open paren on the same line - good enough for the agent's
  // generated SQL, which doesn't nest the main FROM.)
  const fromRe = /\bfrom\s+([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*\b/g;
  let fm: RegExpExecArray | null;
  let primary: string | null = null;
  while ((fm = fromRe.exec(q)) !== null) {
    const src = fm[1];
    if (!KNOWN_SOURCES.has(src)) continue;
    // Look backwards from the match to find the last "(" or "\n".
    // The "main" FROM is the one that isn't inside a subquery - we
    // approximate by picking the one whose preceding "(" count over
    // the file is balanced.
    const before = q.slice(0, fm.index);
    const opens = (before.match(/\(/g) || []).length;
    const closes = (before.match(/\)/g) || []).length;
    if (opens === closes) primary = src; // top-level FROM
  }
  if (primary) {
    out.push(primary);
    seen.add(primary);
  }

  // Then sweep every other `<source>.<table>` token and append any
  // known source we haven't already seen.
  const allRe = /\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*\b/g;
  let am: RegExpExecArray | null;
  while ((am = allRe.exec(q)) !== null) {
    const src = am[1];
    if (!KNOWN_SOURCES.has(src) || seen.has(src)) continue;
    seen.add(src);
    out.push(src);
  }
  return out;
}

/**
 * Pulls findings from the event stream. Two sources:
 *   1. tool_call events with name="record_finding" - the args.text is
 *      the finding text.
 *   2. finding_recorded events (server-side projection) - data.text.
 * Source attribution falls back to the source the agent was reading
 * most recently before the finding was emitted.
 */
function collectFindings(events: CaseEvent[]): FindingRow[] {
  const out: FindingRow[] = [];
  let runningSource: string | null = null;
  for (const e of events) {
    if (e.type === "tool_call") {
      const data = e.data as
        | { name?: string; arguments?: { query?: string; text?: string } }
        | undefined;
      // Update the running source from any tool_call's query.
      const q = (data?.arguments?.query || "").toLowerCase();
      if (q) {
        const re = /\b([a-z_][a-z0-9_]*)\s*\.\s*[a-z_][a-z0-9_]*\b/g;
        let m: RegExpExecArray | null;
        while ((m = re.exec(q)) !== null) {
          if (KNOWN_SOURCES.has(m[1])) runningSource = m[1];
        }
      }
      if (data?.name === "record_finding" && data.arguments?.text) {
        out.push({ src: runningSource, text: data.arguments.text });
      }
    } else if (e.type === "finding_recorded") {
      const data = e.data as { text?: string; source?: string } | undefined;
      if (data?.text) {
        out.push({
          src: data.source ?? runningSource,
          text: data.text,
        });
      }
    }
  }
  // Newest first.
  return out.reverse();
}

interface CaseHeader {
  shortId: string;
  customer: string;
}

function deriveCaseHeader(
  events: CaseEvent[],
  fallbackId: string | undefined,
): CaseHeader {
  for (const e of events) {
    if (e.type === "case_opened") {
      const data = e.data as
        | {
            short_id?: string;
            customer_ref?: string;
            customer?: string;
          }
        | undefined;
      return {
        shortId: data?.short_id ?? truncId(fallbackId),
        customer: data?.customer_ref ?? data?.customer ?? "-",
      };
    }
  }
  return {
    shortId: truncId(fallbackId),
    customer: "-",
  };
}

function truncId(id: string | undefined): string {
  if (!id) return "-";
  // UUIDs are unwieldy in the header; show the first 8 chars uppercased.
  return id.slice(0, 8).toUpperCase();
}

// ──────────────────────────────────────────────────────────────────────
// Elapsed clock - ticks once per second, anchored to the earliest
// case_opened event so the wall-clock shows real investigation duration.
// ──────────────────────────────────────────────────────────────────────

function useElapsed(events: CaseEvent[]): string {
  const startMs = useMemo(() => {
    for (const e of events) {
      if (e.type === "case_opened") return new Date(e.created_at).getTime();
    }
    if (events.length > 0) return new Date(events[0].created_at).getTime();
    return null;
  }, [events]);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  if (startMs === null) return "-";
  const sec = Math.max(0, Math.floor((now - startMs) / 1000));
  const mm = Math.floor(sec / 60);
  const ss = sec % 60;
  return `${pad(mm)}:${pad(ss)}`;
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}
