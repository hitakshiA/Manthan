/**
 * Case workspace - the unified 3-column layout (sidebar / center / right rail).
 *
 * Extracted from HeroShowcase so the live product uses the same components
 * as the marketing site. Receives data via props; no module-level constants.
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  ExternalLink,
  Loader2,
  Pencil,
  RotateCcw,
  Search,
  Send,
  X,
} from "lucide-react";
import { SourceIcon } from "@/components/ui/SourceIcon";
import {
  Code,
  Eyebrow,
  Rule,
  StatusBadge,
  StatusDot,
  Strong,
} from "./atoms";
import type {
  CaseFilter,
  CaseStatus,
  WorkspaceCaseDetail,
  WorkspaceCaseRow,
} from "./types";
import { type CaseEvent } from "@/lib/useCaseEvents";
import {
  approveCase,
  chatWithCase,
  denyCase,
  escalateCase,
  holdCase,
} from "@/lib/api";
import {
  CitationDetailModal,
  type CitationDetailRequest,
} from "./CitationDetailModal";
import { ApprovalCinematic } from "./ApprovalCinematic";
import { OriginalEmailModal } from "./OriginalEmailModal";

// ──────────────────────────────────────────────────────────────────────
// Root
// ──────────────────────────────────────────────────────────────────────

export interface CaseWorkspaceProps {
  cases: WorkspaceCaseRow[];
  detailByNum: Record<string, WorkspaceCaseDetail>;
  activeCaseNum: string;
  onActiveCaseChange: (num: string) => void;
  /** "you" if the current member should be considered the active operator. */
  meOwner?: string;
  /** UUID of the active case - used to subscribe to its live event stream. */
  activeCaseId?: string;
  /** Live event stream owned by the parent page (so refetch on milestones can fire). */
  streamedEvents?: CaseEvent[];
  isLive?: boolean;
  isComplete?: boolean;
}

export function CaseWorkspace({
  cases,
  detailByNum,
  activeCaseNum,
  onActiveCaseChange,
  meOwner = "you",
  activeCaseId,
  streamedEvents,
  isLive: isLiveProp,
  isComplete: isCompleteProp,
}: CaseWorkspaceProps) {
  const events = streamedEvents ?? [];
  const isLive = !!isLiveProp;
  const isComplete = !!isCompleteProp;
  const [status, setStatus] = useState<CaseStatus>("awaiting");
  const [approvedSteps, setApprovedSteps] = useState(0);
  const [editingAction, setEditingAction] = useState<number | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  // Citation modal - opened by clicking any [n] chip in the Brief.
  // Lifted to root so the same modal serves chips in any section.
  const [citationRequest, setCitationRequest] =
    useState<CitationDetailRequest | null>(null);
  // Original-email modal - only relevant for email-triggered cases.
  // Toggle from the BriefHeader.
  const [emailModalOpen, setEmailModalOpen] = useState(false);

  useEffect(() => {
    if (status !== "approving") return;
    if (approvedSteps < 3) {
      const t = setTimeout(() => setApprovedSteps((s) => s + 1), 480);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStatus("approved"), 600);
    return () => clearTimeout(t);
  }, [status, approvedSteps]);

  const reset = () => {
    setStatus("awaiting");
    setApprovedSteps(0);
    setEditingAction(null);
  };

  // Reset approval state whenever the user switches cases.
  useEffect(() => reset(), [activeCaseNum]);

  const activeCase =
    cases.find((c) => c.num === activeCaseNum) ?? cases[0];
  const activeDetail =
    detailByNum[activeCaseNum] ??
    (activeCase ? detailByNum[activeCase.num] : undefined);

  // ────────────────────────────────────────────────────────────────────
  // All hooks must run on every render - Rules of Hooks.
  //
  // Previously the early-return for "case not found / detail loading"
  // sat above the useMemos below, so the hook count flipped (8 → 12)
  // the moment the case detail finished loading. That manifested as
  // "Rendered more hooks than during the previous render" when the
  // operator clicked into any case. Now every hook runs every render,
  // and the missing-case fallback is rendered as a normal branch in
  // the return tree at the bottom.
  // ────────────────────────────────────────────────────────────────────
  const investigationActive = activeCase
    ? investigationIsActive(activeCase.status, events, isComplete)
    : false;
  const sourceStats = useMemo(() => extractSourceStats(events), [events]);
  const sourcesUsed = useMemo(() => Object.keys(sourceStats), [sourceStats]);
  const elapsed = computeElapsed(events);
  const closedKind = useMemo(
    () => (activeCase ? deriveClosedKind(activeCase, events) : null),
    [activeCase, events],
  );
  const stage: WorkspaceStage = useMemo(() => {
    if (investigationActive) return "investigation";
    if (closedKind) return "closed";
    // Local "approving" status flips immediately on Approve click.
    // Server "executing" is the lagging confirmation of the same thing.
    if (
      status === "approving" ||
      status === "approved" ||
      activeCase?.status === "executing"
    ) {
      return "approving";
    }
    return "review";
  }, [investigationActive, closedKind, status, activeCase?.status]);

  if (!activeCase || !activeDetail) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-bg)", color: "var(--color-ink-faint)" }}
      >
        {cases.length === 0 ? (
          <div className="text-[12.5px]">
            No active cases. Trigger one via the API or a Stripe webhook.
          </div>
        ) : (
          <div className="text-[12.5px]">Loading case…</div>
        )}
      </div>
    );
  }

  // When the cinematic finishes, snap local UI state forward so we
  // don't bounce back into "approving" before the server's resolved
  // state propagates.
  const onCinematicComplete = () => {
    setStatus("approved");
  };

  return (
    <div
      className="h-full flex flex-col relative"
      style={{ background: "var(--color-bg)" }}
    >
      <CaseHeaderV2
        caseRow={activeCase}
        detail={activeDetail}
        status={status}
        isLive={isLive && !isComplete}
        sourceStats={sourceStats}
        elapsed={elapsed}
      />

      {/* BODY - stage-driven layout:
            investigation → InvestigationPlayground
            review        → Brief + Drafted actions (two-column)
            approving     → ApprovalCinematic takeover
            closed        → Brief + Actions performed (two-column, with
                            "Case closed" / "Denied" / "Escalated" tag)
       */}
      {stage === "investigation" && (
        <InvestigationPlayground
          events={events}
          isLive={isLive}
          sourcesUsed={sourcesUsed}
        />
      )}

      {stage === "approving" && (
        <ApprovalCinematic
          actions={activeDetail.actions}
          onAllComplete={onCinematicComplete}
        />
      )}

      {(stage === "review" || stage === "closed") && (
        <div
          className="flex-1 min-h-0 grid"
          style={{
            gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)",
          }}
        >
          {/* LEFT - Brief + decision rationale + collapsible trace */}
          <section
            className="overflow-y-auto border-r"
            style={{ borderColor: "var(--color-rule-soft)" }}
          >
            <div className="px-10 md:px-12 pt-10 pb-16 max-w-[62ch] mx-auto space-y-12">
              {stage === "closed" && closedKind && (
                <CaseClosedBanner kind={closedKind} events={events} />
              )}

              <BriefPostmortem
                detail={activeDetail}
                caseRow={activeCase}
                onCite={(req) => setCitationRequest(req)}
                onShowOriginalEmail={() => setEmailModalOpen(true)}
              />

              {events.some((e) =>
                ["tool_call", "tool_result", "finding_recorded", "reflexion", "brief_drafted"].includes(e.type),
              ) && (
                <div
                  className="pt-10 border-t"
                  style={{ borderColor: "var(--color-rule-soft)" }}
                >
                  <InvestigationTrace
                    events={events}
                    isLive={isLive}
                    collapsedByDefault
                  />
                </div>
              )}
            </div>
          </section>

          {/* RIGHT - Drafted/Performed actions + Receipts */}
          <section className="overflow-y-auto">
            <div className="px-10 md:px-12 pt-10 pb-16 max-w-[62ch] mx-auto space-y-12">
              <CaseActions
                detail={activeDetail}
                caseRow={activeCase}
                status={status}
                approvedSteps={approvedSteps}
                editingAction={editingAction}
                setEditingAction={setEditingAction}
                closed={stage === "closed"}
                closedKind={closedKind}
              />

              {events.some((e) =>
                [
                  "action_executed",
                  "action_failed",
                  "action_verified",
                  "drift_detected",
                  "human_approved",
                  "human_hold",
                ].includes(e.type),
              ) && (
                <div
                  className="pt-10 border-t"
                  style={{ borderColor: "var(--color-rule-soft)" }}
                >
                  <CaseReceiptsAndChat events={events} />
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Action bar is only meaningful in the review stage - once the
          operator has approved/denied/escalated, the verbs become noise.
          In the closed state we still surface the chat affordance via
          the ChatDrawer side-tab, so nothing is lost. */}
      {stage === "review" && (
        <CaseActionBar
          caseRow={activeCase}
          detail={activeDetail}
          status={status}
          setStatus={setStatus}
          reset={reset}
          caseId={activeCaseId}
          onToggleChat={() => setChatOpen((v) => !v)}
          chatOpen={chatOpen}
        />
      )}

      {/* In the closed state, give the operator a quiet inline "Talk to
          agent" affordance - they can ask follow-up questions about
          what was decided. No big verb row, just a hairline footer. */}
      {stage === "closed" && (
        <ClosedCaseFooter
          chatOpen={chatOpen}
          onToggleChat={() => setChatOpen((v) => !v)}
        />
      )}

      {/* Talk-to-agent drawer - toggled either from the action bar or the
          side-edge tab. State is lifted up so both controls stay in sync. */}
      <ChatDrawer
        caseId={activeCaseId}
        events={events}
        canSend={!(isLive && !isComplete)}
        open={chatOpen}
        onOpenChange={setChatOpen}
      />

      {/* Clicky citation modal - opens when any [n] chip in the Brief
          is clicked. Lifted up so the same modal is reused across
          Brief, Postmortem, and (future) Evidence rail. */}
      <CitationDetailModal
        request={citationRequest}
        onClose={() => setCitationRequest(null)}
      />

      {/* Original-email modal - only ever opened for email-triggered
          cases (BriefHeader hides the affordance otherwise). Endpoint
          404s for non-email cases, so it's safe even if the toggle
          fires unexpectedly. */}
      <OriginalEmailModal
        caseId={activeCaseId}
        open={emailModalOpen}
        onClose={() => setEmailModalOpen(false)}
      />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────

/** Distinct list of source ids the agent has queried (from coral_sql tool calls). */
function extractSourcesUsed(events: CaseEvent[]): string[] {
  return Object.keys(extractSourceStats(events));
}

interface SourceStat {
  /** How many tool_call queries hit this source. */
  count: number;
  /** Distinct table names referenced - e.g. ["disputes", "charges"]. */
  tables: string[];
}

/**
 * Per-source breakdown of "what did Manthan touch here?" - count of
 * queries and the distinct table names. Powers the rich source chips
 * in the case header ("Stripe - disputes, charges").
 */
function extractSourceStats(events: CaseEvent[]): Record<string, SourceStat> {
  const KNOWN = new Set([
    "stripe", "salesforce", "hubspot", "intercom", "zendesk", "slack",
    "notion", "posthog", "sentry", "datadog", "pagerduty",
  ]);
  const out: Record<string, { count: number; tables: Set<string> }> = {};
  for (const e of events) {
    if (e.type !== "tool_call") continue;
    const args = (e.data as { arguments?: { query?: string } } | undefined)?.arguments;
    const q = (args?.query || "").toLowerCase();
    const seenInQuery = new Set<string>();
    const re = /\b([a-z_][a-z0-9_]+)\s*\.\s*([a-z_][a-z0-9_]+)\b/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(q)) !== null) {
      const src = m[1];
      const tbl = m[2];
      if (!KNOWN.has(src)) continue;
      if (!out[src]) out[src] = { count: 0, tables: new Set() };
      if (!seenInQuery.has(src)) {
        out[src].count += 1;
        seenInQuery.add(src);
      }
      out[src].tables.add(tbl);
    }
  }
  // Coerce the Set into a stable array for downstream rendering.
  const final: Record<string, SourceStat> = {};
  for (const [k, v] of Object.entries(out)) {
    final[k] = { count: v.count, tables: Array.from(v.tables) };
  }
  return final;
}

const SOURCE_NAME: Record<string, string> = {
  stripe: "Stripe",
  salesforce: "Salesforce",
  hubspot: "HubSpot",
  intercom: "Intercom",
  zendesk: "Zendesk",
  slack: "Slack",
  notion: "Notion",
  posthog: "PostHog",
  sentry: "Sentry",
  datadog: "Datadog",
  pagerduty: "PagerDuty",
};

/** Wall-clock elapsed from case_opened to the most recent event (or
 *  case_closed if present). Returns a short label like "1m 23s" or "44s". */
function computeElapsed(events: CaseEvent[]): string | null {
  if (events.length < 2) return null;
  const start = new Date(events[0].created_at).getTime();
  const closed = events.find((e) => e.type === "case_closed");
  const end = closed
    ? new Date(closed.created_at).getTime()
    : new Date(events[events.length - 1].created_at).getTime();
  const ms = Math.max(0, end - start);
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

// ──────────────────────────────────────────────────────────────────────
// InvestigationPlayground - the cinematic "Manthan is working" view.
//
// Replaces the 2-column Brief/Actions body while the agent is still
// running. Shows:
//   1. A wide source mesh - every connected source as a small glyph.
//      Glyphs illuminate when the agent queries that source, then fade
//      back to dim. The currently-querying source has a pulsing dot.
//   2. A "rolling" live trace of the last N events, with the prettifier
//      summary as the human-readable line. Older events recede in
//      contrast so the eye lands on what just happened.
// ──────────────────────────────────────────────────────────────────────

const KNOWN_SOURCES = [
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
] as const;

function InvestigationPlayground({
  events,
  isLive,
  sourcesUsed,
}: {
  events: CaseEvent[];
  isLive?: boolean;
  sourcesUsed: string[];
}) {
  // For each source, find the most recent tool_call event referencing it.
  // The recency drives the glow intensity in the mesh below.
  const lastTouchedBySource = useMemo(() => {
    const out: Record<string, number> = {};
    for (const e of events) {
      if (e.type !== "tool_call") continue;
      const args = (e.data as { arguments?: { query?: string } } | undefined)?.arguments;
      const q = (args?.query || "").toLowerCase();
      const re = /\b([a-z_][a-z0-9_]+)\s*\.\s*[a-z_][a-z0-9_]+\b/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(q)) !== null) {
        const src = m[1];
        if ((KNOWN_SOURCES as readonly string[]).includes(src)) {
          out[src] = Math.max(out[src] || 0, new Date(e.created_at).getTime());
        }
      }
    }
    return out;
  }, [events]);

  // Stream of human-readable lines for the rolling trace.
  const stream = useMemo(
    () =>
      events
        .filter((e) =>
          [
            "tool_call",
            "tool_result",
            "finding_recorded",
            "reflexion",
            "agent_thought",
          ].includes(e.type),
        )
        .slice(-12),
    [events],
  );

  // Force a 1s re-render so glow recency stays fresh even when no new
  // events have landed.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!isLive) return;
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [isLive]);

  const stepCount = events.filter((e) => e.type === "tool_call").length;
  const lastSource = sourcesUsed[sourcesUsed.length - 1] ?? null;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      <div className="px-10 md:px-14 pt-12 pb-24 max-w-[920px] mx-auto">
        <div
          className="eyebrow"
          style={{ color: "var(--color-accent)" }}
        >
          <span
            className="inline-block h-[5px] w-[5px] rounded-full align-middle mr-1.5 animate-pulse-dot"
            style={{ background: "var(--color-accent)" }}
          />
          Investigating
        </div>
        <h3
          className="font-display text-[34px] md:text-[42px] leading-[1.05] tracking-[-0.012em] mt-2"
          style={{ color: "var(--color-ink-strong)" }}
        >
          Manthan is looking{" "}
          <em
            className="display-italic"
            style={{ color: "var(--color-ink-muted)" }}
          >
            across {sourcesUsed.length || "-"} source
            {sourcesUsed.length === 1 ? "" : "s"}
          </em>
        </h3>
        <div
          className="mt-2 text-[12.5px] tabular-nums"
          style={{ color: "var(--color-ink-faint)" }}
        >
          {stepCount} step{stepCount === 1 ? "" : "s"} so far
          {lastSource && (
            <>
              {" · "}last touched{" "}
              <span style={{ color: "var(--color-ink-strong)" }}>
                {lastSource}
              </span>
            </>
          )}
        </div>

        {/* Source mesh */}
        <div
          className="mt-12 pt-10 border-t"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          <div
            className="eyebrow mb-5"
            style={{ color: "var(--color-ink-faint)" }}
          >
            Source mesh
          </div>
          <div className="grid grid-cols-6 md:grid-cols-11 gap-x-3 gap-y-5">
            {KNOWN_SOURCES.map((id) => (
              <SourceCell key={id} id={id} lastTouchedAt={lastTouchedBySource[id]} />
            ))}
          </div>
        </div>

        {/* Rolling live trace */}
        <div
          className="mt-12 pt-10 border-t"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          <div className="flex items-baseline justify-between mb-5">
            <div
              className="eyebrow"
              style={{ color: "var(--color-ink-faint)" }}
            >
              Live trace
            </div>
            <div
              className="text-[11px] tabular-nums"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              latest {stream.length} of {events.length}
            </div>
          </div>
          {stream.length === 0 ? (
            <div
              className="font-display italic text-[14px]"
              style={{ color: "var(--color-ink-muted)" }}
            >
              Waiting for the first move
              <span className="animate-pulse-dot">…</span>
            </div>
          ) : (
            <ol className="space-y-3">
              <AnimatePresence initial={false}>
                {stream.map((e, i) => {
                  const isMostRecent = i === stream.length - 1;
                  return (
                    <motion.li
                      key={e.seq}
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.22 }}
                      className="grid grid-cols-[auto_1fr] items-baseline gap-3"
                    >
                      <span
                        className="font-mono text-[10.5px] tabular-nums"
                        style={{ color: "var(--color-ink-ghost)" }}
                      >
                        {String(e.seq).padStart(3, "0")}
                      </span>
                      <span
                        className="text-[13px] leading-relaxed"
                        style={{
                          color: isMostRecent
                            ? "var(--color-ink-strong)"
                            : "var(--color-ink-muted)",
                          fontWeight: isMostRecent ? 500 : 400,
                        }}
                      >
                        {e.summary || prettyFallback(e)}
                      </span>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

function SourceCell({
  id,
  lastTouchedAt,
}: {
  id: string;
  lastTouchedAt?: number;
}) {
  const now = Date.now();
  const ageMs = lastTouchedAt ? now - lastTouchedAt : Infinity;
  // 3 states: querying-now (<2s), recently-touched (<10s), dim (otherwise)
  const fresh = ageMs < 2000;
  const warm = ageMs < 10_000;
  return (
    <div className="flex flex-col items-center gap-1.5 transition-opacity">
      <div
        className="h-9 w-9 inline-flex items-center justify-center transition-all"
        style={{
          background: fresh
            ? "var(--color-accent-soft)"
            : warm
              ? "var(--color-surface-2)"
              : "transparent",
          border: `1px solid ${
            fresh
              ? "var(--color-accent)"
              : warm
                ? "var(--color-rule)"
                : "var(--color-rule-soft)"
          }`,
          borderRadius: "var(--radius-sm)",
          color: fresh
            ? "var(--color-accent)"
            : warm
              ? "var(--color-ink-strong)"
              : "var(--color-ink-ghost)",
          opacity: warm ? 1 : 0.45,
        }}
      >
        <SourceIcon id={id} size={16} tinted={warm} />
      </div>
      <span
        className="text-[9.5px] uppercase tracking-[0.12em] tabular-nums"
        style={{
          color: fresh
            ? "var(--color-accent)"
            : warm
              ? "var(--color-ink-muted)"
              : "var(--color-ink-ghost)",
          fontWeight: fresh ? 600 : 500,
        }}
      >
        {id}
      </span>
      {fresh && (
        <span
          className="h-[3px] w-[3px] rounded-full animate-pulse-dot"
          style={{ background: "var(--color-accent)" }}
        />
      )}
    </div>
  );
}

function prettyFallback(e: CaseEvent): string {
  const data = e.data as Record<string, unknown> | undefined;
  if (!data) return e.type;
  if (e.type === "tool_call") {
    return `Calling ${String(data.name ?? "tool")}`;
  }
  if (e.type === "tool_result") {
    return `Result from ${String((data as { name?: string }).name ?? "tool")}`;
  }
  if (e.type === "finding_recorded") {
    return String((data as { text?: string }).text ?? "Recorded a finding");
  }
  if (e.type === "reflexion") {
    return "Reflexion checkpoint";
  }
  if (e.type === "agent_thought") {
    return String((data as { text?: string }).text ?? "Thinking");
  }
  return e.type;
}

// ──────────────────────────────────────────────────────────────────────
// CaseHeaderV2 - the new top strip that replaces the old header + right
// rail. Shows the case title, source chips used, time taken, status,
// and a "Talk to agent" trigger. Compact (60-70px tall) so the two-
// column body has the screen.
// ──────────────────────────────────────────────────────────────────────

function CaseHeaderV2({
  caseRow,
  detail,
  status,
  isLive,
  sourceStats,
  elapsed,
}: {
  caseRow: WorkspaceCaseRow;
  detail: WorkspaceCaseDetail;
  status: CaseStatus;
  isLive?: boolean;
  sourceStats: Record<string, SourceStat>;
  elapsed: string | null;
}) {
  const sourceIds = Object.keys(sourceStats);
  return (
    <header
      className="px-8 md:px-10 pt-5 pb-5 border-b flex items-start justify-between gap-8"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div className="min-w-0 flex-1">
        <div
          className="eyebrow flex items-center gap-2 mb-1.5"
          style={{ color: "var(--color-ink-faint)" }}
        >
          <span>
            Case №{" "}
            <span
              className="font-mono"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {caseRow.num}
            </span>
          </span>
          <span style={{ color: "var(--color-ink-ghost)" }}>·</span>
          <span>{caseRow.type}</span>
        </div>
        <h2
          className="font-display text-[24px] leading-[1.12] tracking-[-0.005em]"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {caseRow.customer}{" "}
          <em
            className="display-italic"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {detail.headlineVerb}
          </em>
        </h2>

        {/* Source-used chips: each shows brand glyph + name + the
            distinct tables touched, mirroring the sketch's "Source used
            + Description". */}
        {sourceIds.length > 0 && (
          <div className="mt-4 flex items-baseline gap-5 flex-wrap">
            {sourceIds.slice(0, 8).map((id) => {
              const stat = sourceStats[id];
              const tablesLine = stat.tables.slice(0, 3).join(", ");
              return (
                <div
                  key={id}
                  className="flex items-center gap-2 min-w-0"
                  title={`${stat.count} queries · ${stat.tables.join(", ")}`}
                >
                  <SourceIcon id={id} size={13} tinted />
                  <div className="min-w-0">
                    <div
                      className="text-[11.5px] leading-none"
                      style={{ color: "var(--color-ink-strong)" }}
                    >
                      {SOURCE_NAME[id] ?? id}
                    </div>
                    {tablesLine && (
                      <div
                        className="text-[10px] tabular-nums mt-0.5 leading-none truncate max-w-[180px]"
                        style={{ color: "var(--color-ink-ghost)" }}
                      >
                        {tablesLine}
                        {stat.tables.length > 3
                          ? ` · +${stat.tables.length - 3}`
                          : ""}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {sourceIds.length > 8 && (
              <span
                className="text-[10.5px] italic font-display"
                style={{ color: "var(--color-ink-ghost)" }}
              >
                + {sourceIds.length - 8} more
              </span>
            )}
          </div>
        )}

        {/* Time taken - print-style callout on its own row, aligned with
            the sketch's "Time taken ←" arrow on the left. */}
        {elapsed && (
          <div className="mt-3 inline-flex items-baseline gap-2">
            <span
              className="text-[10px] uppercase tracking-[0.13em]"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              Time taken
            </span>
            <span
              className="font-display text-[15px] tabular-nums"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {elapsed}
            </span>
          </div>
        )}
      </div>

      <div className="shrink-0 pt-1">
        {isLive ? (
          <span
            className="inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.13em] font-medium"
            style={{ color: "var(--color-accent)" }}
          >
            <span
              className="h-[5px] w-[5px] rounded-full animate-pulse-dot"
              style={{ background: "var(--color-accent)" }}
            />
            Investigating
          </span>
        ) : (
          <StatusBadge status={status} />
        )}
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// ChatDrawer - slides in from the right edge with the talk-to-agent
// thread. Toggle lives as a vertical tab on the right side; clicking
// expands a 380px-wide drawer.
// ──────────────────────────────────────────────────────────────────────

function ChatDrawer({
  caseId,
  events,
  canSend,
  open,
  onOpenChange,
}: {
  caseId?: string;
  events: CaseEvent[];
  canSend: boolean;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const setOpen = (v: boolean | ((p: boolean) => boolean)) =>
    onOpenChange(typeof v === "function" ? v(open) : v);
  const chatTurns = events.filter((e) =>
    ["human_followup", "agent_thinking", "agent_reply"].includes(e.type),
  );

  return (
    <>
      {/* Toggle tab - vertical pill anchored to the right edge */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-30 px-2 py-3 flex flex-col items-center gap-1.5 hover:opacity-90 transition-opacity"
        style={{
          background: open ? "var(--color-surface-2)" : "var(--color-surface)",
          border: "1px solid var(--color-rule)",
          borderRight: "none",
          borderTopLeftRadius: "var(--radius-md)",
          borderBottomLeftRadius: "var(--radius-md)",
          color: "var(--color-ink-strong)",
        }}
        title="Talk to the agent that wrote this brief"
      >
        <span
          className="font-display italic text-[12px]"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          Talk to agent
        </span>
        {chatTurns.length > 0 && (
          <span
            className="text-[9.5px] tabular-nums"
            style={{ color: "var(--color-ink-faint)" }}
          >
            {chatTurns.filter((e) => e.type === "agent_reply" || e.type === "human_followup").length}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="fixed top-0 right-0 h-full z-40 flex flex-col border-l"
            style={{
              width: 400,
              background: "var(--color-bg)",
              borderColor: "var(--color-rule)",
              boxShadow: "-24px 0 48px rgba(0,0,0,0.35)",
            }}
          >
            <header
              className="px-5 py-3 border-b flex items-baseline justify-between"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <div>
                <div
                  className="eyebrow"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  Talk to the agent
                </div>
                <div
                  className="font-display text-[15px] mt-0.5"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  About this case
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-[11px] tracking-[0.04em] hover:opacity-90"
                style={{ color: "var(--color-ink-faint)" }}
              >
                Close
              </button>
            </header>

            <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              {chatTurns.length === 0 ? (
                <p
                  className="font-display italic text-[13.5px] leading-relaxed max-w-prose"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  Ask the agent anything about this case - &quot;why did you
                  fight this?&quot;, &quot;re-check the Notion policy&quot;,
                  &quot;rewrite the customer email warmer&quot;. The agent
                  has full Coral access to re-investigate.
                </p>
              ) : (
                <ul className="space-y-5">
                  <AnimatePresence initial={false}>
                    {chatTurns.map((e) => (
                      <motion.div
                        key={e.seq}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18 }}
                      >
                        <ReceiptOrChatItem event={e} />
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </ul>
              )}
            </div>

            {caseId && (
              <div
                className="px-5 py-4 border-t"
                style={{ borderColor: "var(--color-rule-soft)" }}
              >
                <CaseChatInput caseId={caseId} disabled={!canSend} />
              </div>
            )}
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Case closed banner - appears above the Brief once a case is terminal
// ──────────────────────────────────────────────────────────────────────

/** A quiet, hairline-bordered banner across the top of the Brief column
 *  signalling the case is closed. Reads the most recent terminal event
 *  to surface the verdict in the operator's voice ("denied", "escalated",
 *  "fired"). */
function CaseClosedBanner({
  kind,
  events,
}: {
  kind: ClosedKind;
  events: CaseEvent[];
}) {
  // Pull the reason from the relevant terminal event, when available.
  const reason = useMemo(() => {
    const terminal = [...events]
      .reverse()
      .find((e) =>
        ["human_denied", "human_escalated", "case_closed", "error"].includes(
          e.type,
        ),
      );
    if (!terminal) return null;
    const d = terminal.data || {};
    return (
      (d.reason as string | undefined) ??
      (d.summary as string | undefined) ??
      (d.note as string | undefined) ??
      null
    );
  }, [events]);

  const label = {
    resolved: "Case closed",
    denied: "Denied",
    escalated: "Escalated",
    errored: "Errored",
  }[kind];

  const tint = {
    resolved: "var(--color-accent)",
    denied: "var(--color-danger)",
    escalated: "var(--color-amber)",
    errored: "var(--color-danger)",
  }[kind];

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="px-4 py-3 flex items-start gap-3"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-rule-soft)",
        borderLeft: `2px solid ${tint}`,
        borderRadius: "var(--radius-md)",
      }}
    >
      <span
        className="text-[10px] uppercase tracking-[0.13em] shrink-0 pt-0.5"
        style={{ color: tint }}
      >
        {label}
      </span>
      <div
        className="text-[12.5px] leading-[1.5]"
        style={{ color: "var(--color-ink-muted)" }}
      >
        {kind === "denied" && (
          <>You denied the agent&apos;s recommendation.</>
        )}
        {kind === "escalated" && (
          <>The case was handed off to a human team.</>
        )}
        {kind === "resolved" && <>The agent&apos;s actions fired and the case is resolved.</>}
        {kind === "errored" && <>The run errored mid-investigation. Inspect the trace below.</>}
        {reason && (
          <span
            className="block mt-1 font-display italic"
            style={{ color: "var(--color-ink-faint)" }}
          >
            “{reason}”
          </span>
        )}
      </div>
    </motion.div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Brief - header + TL;DR lede + postmortem-in-detail + inline citation chips
// ──────────────────────────────────────────────────────────────────────

/**
 * BriefPostmortem - the centerpiece of the Brief column.
 *
 *   ┌────────────────────────────────┐
 *   │ Header (customer · verdict)    │
 *   │ TLDR (italic lede paragraph)   │
 *   │                                │
 *   │ Postmortem in detail           │
 *   │   1. Finding text [1] [2]      │
 *   │   2. Finding text [3]          │
 *   │   3. ...                       │
 *   │                                │
 *   │ Decision rationale             │
 *   └────────────────────────────────┘
 *
 * Citation chips [n] are clickable - calls `onCite` with the evidence
 * row so the parent opens the CitationDetailModal.
 */
function BriefPostmortem({
  detail,
  caseRow,
  onCite,
  onShowOriginalEmail,
}: {
  detail: WorkspaceCaseDetail;
  caseRow: WorkspaceCaseRow;
  onCite: (req: CitationDetailRequest) => void;
  /** Called when the user wants to peek at the inbound email that
   *  opened this case. BriefHeader only shows the affordance for
   *  email-triggered cases. */
  onShowOriginalEmail?: () => void;
}) {
  // Prefer the agent-written brief.tldr (a real memo lede); fall back to
  // the concatenated finding text when no brief has dropped yet.
  const tldrRaw =
    (typeof detail.briefTldr === "string" && detail.briefTldr.trim()) ||
    (typeof detail.tldr === "string" ? detail.tldr : String(detail.tldr ?? ""));
  const tldrParagraphs = splitIntoParagraphs(tldrRaw);
  const showPostmortem = detail.findings && detail.findings.length > 0;

  return (
    <div className="space-y-8 shrink-0">
      {/* ── Header - customer · verdict · amount · confidence ── */}
      <BriefHeader
        caseRow={caseRow}
        detail={detail}
        onShowOriginalEmail={onShowOriginalEmail}
      />

      {/* ── TLDR lede - italic display, the "what happened in one breath" ── */}
      {tldrParagraphs.length > 0 && (
        <div className="space-y-4">
          {tldrParagraphs.map((p, i) => (
            <p
              key={i}
              className="font-display text-[15px] leading-[1.65]"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {p}
            </p>
          ))}
        </div>
      )}

      {/* ── Postmortem in detail - each finding as a numbered paragraph
             with inline citation chips at the end. ── */}
      {showPostmortem && (
        <div className="space-y-4">
          <Eyebrow>Postmortem in detail</Eyebrow>
          <ol className="space-y-4">
            {detail.findings.map((f, i) => (
              <li
                key={f.seq}
                className="grid"
                style={{
                  gridTemplateColumns: "20px minmax(0,1fr)",
                  gap: 10,
                }}
              >
                <span
                  className="font-mono text-[11px] tabular-nums pt-1"
                  style={{ color: "var(--color-ink-ghost)" }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <p
                  className="text-[14px] leading-[1.6]"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  {f.text}
                  {f.citationIndices.length > 0 && (
                    <span className="ml-1 inline-flex items-baseline gap-1 align-baseline">
                      {f.citationIndices.map((evIdx) => {
                        const ev = detail.evidence[evIdx];
                        if (!ev) return null;
                        return (
                          <CitationChip
                            key={`${f.seq}-${evIdx}`}
                            n={ev.n}
                            src={ev.src}
                            url={ev.url ?? null}
                            onShowReasoning={() =>
                              onCite({
                                caseId: detail.caseId,
                                source: ev.src,
                                table: ev.table ?? null,
                                ref: ev.ref ?? null,
                                field: ev.field ?? null,
                                url: ev.url ?? null,
                                findingText: f.text,
                                n: ev.n,
                              })
                            }
                          />
                        );
                      })}
                    </span>
                  )}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* ── Decision rationale - the agent's spoken reasoning. ── */}
      {detail.policyReasoning && (
        <div className="space-y-2">
          <Eyebrow>Decision rationale</Eyebrow>
          <div
            className="text-[13.5px] leading-[1.65]"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {detail.policyReasoning}
          </div>
        </div>
      )}
    </div>
  );
}

/** Header line above the brief: customer + verdict verb + amount. */
function BriefHeader({
  caseRow,
  detail,
  onShowOriginalEmail,
}: {
  caseRow: WorkspaceCaseRow;
  detail: WorkspaceCaseDetail;
  onShowOriginalEmail?: () => void;
}) {
  // Show the "Original email" affordance only when this case was opened
  // via inbound email. The trigger surface comes through on the case
  // row (set by caseRowFromApi). The endpoint 404s for other surfaces
  // anyway, so this just hides a button that wouldn't do anything.
  const isEmailCase = caseRow.triggerSurface === "inbound_email";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Eyebrow>Brief</Eyebrow>
        {isEmailCase && onShowOriginalEmail && (
          <button
            type="button"
            onClick={onShowOriginalEmail}
            className={
              "inline-flex items-center gap-1.5 text-[11px] " +
              "hover:opacity-90 transition-opacity " +
              "outline-none focus-visible:ring-2 focus-visible:ring-offset-2 " +
              "focus-visible:ring-[color:var(--color-accent)] " +
              "focus-visible:ring-offset-[color:var(--color-bg)]"
            }
            style={{
              color: "var(--color-ink-muted)",
              letterSpacing: "0.02em",
            }}
            title="Show the original email that opened this case"
          >
            <span
              aria-hidden
              className="inline-block"
              style={{
                width: 10,
                height: 7,
                border: "1px solid var(--color-ink-faint)",
                borderRadius: 1,
                position: "relative",
              }}
            />
            Original email ↗
          </button>
        )}
      </div>
      <h2
        className="font-display text-[clamp(1.5rem,1.2rem+0.7vw,2rem)] leading-[1.1] tracking-[-0.01em]"
        style={{ color: "var(--color-ink-strong)" }}
      >
        {caseRow.customer}{" "}
        <span
          className="italic"
          style={{ color: "var(--color-ink-muted)" }}
        >
          {detail.headlineVerb}
        </span>
      </h2>
      <div
        className="text-[11px] tabular-nums"
        style={{
          color: "var(--color-ink-faint)",
          letterSpacing: "0.04em",
        }}
      >
        <span className="font-mono">CASE-{detail.num}</span>
        {" · "}
        <span className="uppercase">{caseRow.type}</span>
        {" · "}
        <span>{detail.routedNote.toLowerCase()}</span>
      </div>
    </div>
  );
}

/** Inline numbered citation chip - `[icon][n]↗` linked to the source.
 *
 *  Two affordances in one inline glyph:
 *    - **Plain click** on the chip → opens the source record in a new
 *      tab (one-click verification - the primary UX per the sketch).
 *    - **Click the small `ⓘ`** to its right → opens the reasoning
 *      modal with the agent's "why this matters" explanation.
 *    - **Shift-click** on the chip is the same as clicking `ⓘ` -
 *      useful when keyboard is faster than aiming at the info dot.
 *
 *  When no URL is known (resolver returned null), the chip falls back
 *  to opening the reasoning modal on plain click so it isn't dead.
 */
function CitationChip({
  n,
  src,
  url,
  onShowReasoning,
}: {
  n: number;
  src: string;
  url: string | null;
  onShowReasoning: () => void;
}) {
  const hasUrl = !!url;
  const baseClasses =
    "citation-chip inline-flex items-center gap-1 px-1.5 py-0.5 " +
    "font-mono text-[10.5px] tabular-nums align-baseline " +
    "outline-none focus-visible:ring-2 " +
    "focus-visible:ring-[color:var(--color-accent)] focus-visible:ring-offset-1 " +
    "focus-visible:ring-offset-[color:var(--color-bg)]";
  const baseStyle = {
    background: "var(--color-surface)",
    border: "1px solid var(--color-rule-soft)",
    borderRadius: 4,
    color: "var(--color-ink-muted)",
    lineHeight: 1,
  } as const;

  const chip = hasUrl ? (
    <a
      href={url!}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => {
        // Shift-click → open reasoning instead of source. Lets the
        // operator stay in-workspace when they want context first.
        if (e.shiftKey) {
          e.preventDefault();
          onShowReasoning();
        }
      }}
      className={baseClasses}
      style={baseStyle}
      title={`Open ${src} record in new tab · shift-click for reasoning`}
    >
      <SourceIcon id={src} size={9} tinted />
      <span>[{n}]</span>
      <span
        aria-hidden
        style={{ color: "var(--color-ink-ghost)", fontSize: 9 }}
      >
        ↗
      </span>
    </a>
  ) : (
    // No URL → chip itself opens the reasoning modal. Don't render
    // the arrow glyph so the operator doesn't expect a navigation.
    <button
      type="button"
      onClick={onShowReasoning}
      className={baseClasses}
      style={baseStyle}
      title={`Citation [${n}] - no direct link available · click for reasoning`}
    >
      <SourceIcon id={src} size={9} tinted />
      <span>[{n}]</span>
    </button>
  );

  return (
    <span className="inline-flex items-baseline gap-[2px]">
      {chip}
      {hasUrl && (
        <button
          type="button"
          onClick={onShowReasoning}
          aria-label={`Why this citation matters - [${n}]`}
          title="Why this matters"
          className={
            "citation-info inline-flex items-center justify-center " +
            "font-mono text-[10px] tabular-nums align-baseline " +
            "outline-none focus-visible:ring-2 " +
            "focus-visible:ring-[color:var(--color-accent)] focus-visible:ring-offset-1 " +
            "focus-visible:ring-offset-[color:var(--color-bg)]"
          }
          style={{
            background: "transparent",
            color: "var(--color-ink-ghost)",
            lineHeight: 1,
            padding: "0 2px",
          }}
        >
          ⓘ
        </button>
      )}
    </span>
  );
}

function splitIntoParagraphs(text: string): string[] {
  if (!text) return [];
  if (text.includes("\n\n")) {
    return text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  }
  // Heuristic: split on sentence boundaries followed by a structural cue
  // ("Prior renewals", "Hubspot", "Stripe", "Intercom", "Notion", "PostHog")
  // so concatenated finding-text reads as paragraphs.
  const cues = /(?<=\.) (?=(?:Prior |Hubspot |HubSpot |Stripe |Intercom |Zendesk |Notion |PostHog |Sentry |Datadog |PagerDuty |Salesforce |No |Customer |Account |The )[A-Z])/;
  const parts = text.split(cues);
  if (parts.length > 1) return parts.map((p) => p.trim()).filter(Boolean);
  return [text];
}

// ──────────────────────────────────────────────────────────────────────
// Drafted actions
// ──────────────────────────────────────────────────────────────────────

function CaseActions({
  detail,
  caseRow,
  status,
  approvedSteps,
  editingAction,
  setEditingAction,
  closed,
  closedKind,
}: {
  detail: WorkspaceCaseDetail;
  caseRow: WorkspaceCaseRow;
  status: CaseStatus;
  approvedSteps: number;
  editingAction: number | null;
  setEditingAction: (n: number | null) => void;
  closed?: boolean;
  closedKind?: ClosedKind | null;
}) {
  const actions = detail.actions;
  const allDone = caseRow.status === "executing" || caseRow.status === "resolved" || closed === true;

  // Section heading + status sub-label depend on the closed terminal kind.
  const eyebrow = closed
    ? closedKind === "denied"
      ? "Actions skipped"
      : closedKind === "escalated"
        ? "Actions left undrafted"
        : closedKind === "errored"
          ? "Actions interrupted"
          : "Actions performed"
    : "Drafted actions";

  const subLabel = closed
    ? closedKind === "denied"
      ? "denied by you"
      : closedKind === "escalated"
        ? "handed off"
        : closedKind === "errored"
          ? "stopped on error"
          : "fired ✓"
    : allDone
      ? "executed"
      : "awaiting approval";

  const emptyText = closed
    ? closedKind === "denied"
      ? "You denied the agent's recommendation - no actions fired."
      : closedKind === "escalated"
        ? "Case was escalated before the agent drafted actions."
        : closedKind === "errored"
          ? "The run errored before any action could fire."
          : "No actions were fired for this case."
    : "No actions drafted yet - investigation in progress.";

  return (
    <section className="h-full flex flex-col min-h-0">
      <div className="flex items-baseline justify-between shrink-0">
        <Eyebrow>{eyebrow}</Eyebrow>
        <span
          className="text-[10.5px]"
          style={{
            color: "var(--color-ink-ghost)",
            letterSpacing: "0.04em",
          }}
        >
          {actions.length} action{actions.length === 1 ? "" : "s"} · {subLabel}
        </span>
      </div>

      <ol className="mt-3 space-y-2.5 flex-1 min-h-0 overflow-auto pr-1">
        {actions.length === 0 && (
          <li
            className="text-[12px] italic"
            style={{ color: "var(--color-ink-faint)" }}
          >
            {emptyText}
          </li>
        )}
        {actions.map((a, i) => {
          // Prefer the real action.status when present (live DB row).
          // Fall back to caseRow-derived "done" for cases without actions yet.
          const realStatus = a.status;
          const succeeded = realStatus === "succeeded";
          const failed = realStatus === "failed";
          const executing = realStatus === "executing" || realStatus === "approved";
          const fallbackDone =
            !realStatus &&
            (allDone ||
              status === "approved" ||
              (status === "approving" && i < approvedSteps));
          const done = succeeded || fallbackDone;
          const isEditing = editingAction === i;
          return (
            <li key={a.id ?? `${a.title}-${i}`}>
              <div
                className="items-start py-0.5"
                style={{
                  display: "grid",
                  gridTemplateColumns: "24px minmax(0,1fr) 24px",
                  gap: 10,
                }}
              >
                <span
                  className="tabular-nums text-[11px] flex items-center justify-center"
                  style={{
                    color: failed
                      ? "var(--color-danger, #d04545)"
                      : done
                        ? "var(--color-accent)"
                        : "var(--color-ink-faint)",
                    paddingTop: 2,
                    fontWeight: 500,
                  }}
                >
                  {failed ? (
                    <AlertTriangle className="h-3 w-3" />
                  ) : executing ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : done ? (
                    "✓"
                  ) : (
                    String(i + 1).padStart(2, "0")
                  )}
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className="text-[12.5px]"
                      style={{
                        color: "var(--color-ink-strong)",
                        fontWeight: 500,
                      }}
                    >
                      {a.title}
                    </span>
                    <ActionStatusPill action={a} fallbackFired={fallbackDone} />
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 flex-wrap">
                    <Code>
                      <span
                        style={{
                          color: "var(--color-ink-faint)",
                          fontSize: "11px",
                        }}
                      >
                        {a.target}
                      </span>
                    </Code>
                    {a.externalRef && a.externalUrl && (
                      <a
                        href={a.externalUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 text-[10.5px] hover:underline"
                        style={{ color: "var(--color-accent)" }}
                        title={`View ${a.externalRef} in source`}
                      >
                        view <ExternalLink className="h-2.5 w-2.5" />
                      </a>
                    )}
                    {a.externalRef && !a.externalUrl && (
                      <span
                        className="text-[10.5px] tabular-nums"
                        style={{ color: "var(--color-ink-faint)" }}
                      >
                        ref: {a.externalRef.slice(0, 18)}
                        {a.externalRef.length > 18 ? "…" : ""}
                      </span>
                    )}
                  </div>
                  {isEditing ? (
                    <textarea
                      defaultValue={a.body}
                      className="mt-1.5 w-full text-[11.5px] leading-relaxed p-2 outline-none resize-none"
                      style={{
                        background: "var(--color-surface)",
                        color: "var(--color-ink)",
                        border: "1px solid var(--color-accent-line)",
                        minHeight: 60,
                      }}
                      onBlur={() => setEditingAction(null)}
                      autoFocus
                    />
                  ) : (
                    <p
                      className="mt-1 text-[11.5px] leading-snug line-clamp-2"
                      style={{ color: "var(--color-ink-muted)" }}
                    >
                      {a.body}
                    </p>
                  )}
                  {failed && a.errorMessage && (
                    <p
                      className="mt-1 text-[11px] leading-snug"
                      style={{
                        color: "var(--color-danger, #d04545)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      ✗ {a.errorMessage}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setEditingAction(isEditing ? null : i)}
                  className="self-start p-1 transition-colors"
                  style={{
                    color: isEditing
                      ? "var(--color-accent)"
                      : "var(--color-ink-ghost)",
                  }}
                  disabled={status !== "awaiting" || !a.id}
                  title={a.id ? "Edit draft" : "Action not yet drafted"}
                >
                  {isEditing ? (
                    <X className="h-3 w-3" />
                  ) : (
                    <Pencil className="h-3 w-3" />
                  )}
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Status pill for the action card title row. */
function ActionStatusPill({
  action,
  fallbackFired,
}: {
  action: WorkspaceAction;
  fallbackFired: boolean;
}) {
  // Real status takes precedence; otherwise fall back to the caseRow-derived
  // "fired" indicator so the existing UI for cases without actions still works.
  const s = action.status;
  if (!s) {
    if (fallbackFired) {
      return (
        <motion.span
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider"
          style={{
            color: "var(--color-accent)",
            fontWeight: 600,
            letterSpacing: "0.08em",
          }}
        >
          fired
        </motion.span>
      );
    }
    return null;
  }
  const map: Record<
    NonNullable<WorkspaceAction["status"]>,
    { label: string; color: string }
  > = {
    drafted: { label: "drafted", color: "var(--color-ink-faint)" },
    awaiting_approval: { label: "awaiting", color: "var(--color-warning, #d4a04e)" },
    approved: { label: "approved", color: "var(--color-warning, #d4a04e)" },
    executing: { label: "executing", color: "var(--color-warning, #d4a04e)" },
    succeeded: { label: "fired", color: "var(--color-accent)" },
    failed: { label: "failed", color: "var(--color-danger, #d04545)" },
    drift: { label: "drifted", color: "var(--color-danger, #d04545)" },
  };
  const entry = map[s];
  return (
    <motion.span
      initial={{ scale: 0.7, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider"
      style={{
        color: entry.color,
        fontWeight: 600,
        letterSpacing: "0.08em",
      }}
    >
      {entry.label}
    </motion.span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Investigation timeline - live stream of agent activity
// ──────────────────────────────────────────────────────────────────────

/** Stage of the case workspace.
 *
 *  investigation → agent still working (cinematic Playground)
 *  review        → brief drafted, awaiting human nod
 *  approving     → user clicked Approve, actions firing (cinematic)
 *  closed        → terminal: resolved/denied/escalated/errored
 */
type WorkspaceStage = "investigation" | "review" | "approving" | "closed";

/** Reason a case has reached the terminal "closed" stage. Drives the
 *  banner copy + colour at the top of the Brief column. */
type ClosedKind = "resolved" | "denied" | "escalated" | "errored";

function deriveClosedKind(
  caseRow: WorkspaceCaseRow,
  events: CaseEvent[],
): ClosedKind | null {
  // The Tone type loses "escalated" + "errored" detail - we recover it
  // from the event log instead.
  const escalated = events.some((e) => e.type === "human_escalated");
  if (escalated) return "escalated";
  const denied = events.some((e) => e.type === "human_denied");
  if (denied) return "denied";
  const errored = events.some((e) => e.type === "error" || e.type === "case_errored");
  // For "resolved" tone, decide between resolved (approved+fired) and
  // errored based on event log.
  if (caseRow.status === "resolved") return errored ? "errored" : "resolved";
  // Some cases sit in "drafted" tone after errored/escalated due to the
  // adapter's lossy mapping - recover from events.
  const caseClosed = events.some((e) => e.type === "case_closed");
  if (caseClosed) return "resolved";
  if (errored) return "errored";
  return null;
}

function investigationIsActive(
  caseStatus: WorkspaceCaseRow["status"],
  events: CaseEvent[],
  isComplete: boolean,
): boolean {
  // While the agent is mid-investigation, show the live timeline instead
  // of the placeholder Drafted actions. Once a brief is drafted OR the
  // case is closed, switch back to actions.
  if (isComplete) return false;
  if (caseStatus === "executing" || caseStatus === "resolved") return false;
  // If we have events but no brief yet, we're investigating.
  const hasBrief = events.some(
    (e) => e.type === "brief_drafted" || e.type === "case_closed",
  );
  if (hasBrief) return false;
  // If we have ANY agent activity in events, treat as live.
  return events.some(
    (e) =>
      e.type === "investigation_started" ||
      e.type === "tool_call" ||
      e.type === "tool_result" ||
      e.type === "finding_recorded" ||
      e.type === "reflexion",
  );
}

/**
 * InvestigationTrace - always-open list of every step the agent took,
 * with relative time offsets (+0:00, +0:01.2, …) running down the gutter.
 *
 * Individual rows are still per-step expandable so the operator can pop
 * a step open to read the raw SQL or tool result - but the section as a
 * whole is never collapsed. The whole point of the trace is to be the
 * audit log; hiding it would defeat that.
 *
 * `collapsedByDefault` is kept on the prop signature for backward
 * compatibility with old callers, but is no longer honoured.
 */
function InvestigationTrace({
  events,
  isLive,
}: {
  events: CaseEvent[];
  isLive: boolean;
  /** @deprecated Section is always open. */
  collapsedByDefault?: boolean;
}) {
  const steps = useMemo(() => pairToolEvents(events), [events]);
  if (steps.length === 0) return null;

  // pairToolEvents returns newest-first; the first step in source-time
  // order is the LAST item in the array.
  const firstAt = steps.length
    ? steps[steps.length - 1].at
    : events[0]?.created_at;

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <Eyebrow>
          {isLive ? "Investigation · live" : "Investigation trace"}
        </Eyebrow>
        <span
          className="text-[10.5px] inline-flex items-center gap-1.5 tabular-nums"
          style={{ color: "var(--color-ink-ghost)", letterSpacing: "0.04em" }}
        >
          {isLive && (
            <span
              className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
              style={{ background: "var(--color-accent)" }}
            />
          )}
          {steps.length} step{steps.length === 1 ? "" : "s"}
        </span>
      </div>
      <ol>
        <AnimatePresence initial={false}>
          {steps.map((s) => (
            <motion.li
              key={s.id}
              layout
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
            >
              <TimelineStep step={s} firstAt={firstAt} />
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </section>
  );
}

interface TimelineStep {
  id: string;
  kind:
    | "tool"
    | "finding"
    | "reflexion"
    | "brief"
    | "closed"
    | "error"
    | "started"
    | "thinking";
  title: string;
  summary?: string;
  source?: string;
  detailLines: { label: string; value: string }[];
  status?: "running" | "ok" | "error";
  /** ISO timestamp of the originating event (e.g. case_opened, tool_call). */
  at: string;
}

function pairToolEvents(events: CaseEvent[]): TimelineStep[] {
  const result: TimelineStep[] = [];
  const consumedResultSeqs = new Set<number>();

  // Index tool_results by call_id (or tool_call_id) for fast pairing.
  const resultByCallId = new Map<string, CaseEvent>();
  for (const e of events) {
    if (e.type === "tool_result") {
      const d = e.data as Record<string, unknown>;
      const cid =
        (d.tool_call_id as string) ||
        (d.call_id as string) ||
        (d.id as string) ||
        "";
      if (cid) resultByCallId.set(cid, e);
    }
  }

  for (const e of events) {
    const d = (e.data ?? {}) as Record<string, unknown>;

    if (e.type === "investigation_started") {
      result.push({
        id: `e-${e.seq}`,
        kind: "started",
        title: "Investigation started",
        detailLines: [],
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "tool_call") {
      const callId = (d.id as string) || `${e.seq}`;
      const matchedResult = resultByCallId.get(callId);
      if (matchedResult) consumedResultSeqs.add(matchedResult.seq);
      const name = (d.name as string) || "tool";
      const args = (d.arguments as Record<string, unknown>) || {};
      const query = typeof args.query === "string" ? (args.query as string) : "";
      const source =
        sniffSourceFromQuery(query) ?? sniffSourceFromTool(name) ?? "manthan";

      // Prefer the Gemini-Flash-Lite-written summary if the prettifier has
      // landed it; otherwise fall back to the tool name as the title.
      const prettyTitle = e.summary?.trim();
      const fallbackTitle =
        name === "coral_sql"
          ? "Cross-source SQL"
          : name === "coral_list_catalog"
            ? "Catalog discovery"
            : name === "coral_describe_table"
              ? `Describe ${args.table ?? "table"}`
              : name;
      const title = prettyTitle || fallbackTitle;

      // Show the SQL as a SECONDARY hint when we have a pretty summary -
      // they complement each other (summary = intent, query = mechanism).
      const summary = prettyTitle
        ? (query ? truncateInline(query, 100) : undefined)
        : query
          ? truncateInline(query, 100)
          : Object.keys(args).length > 0
            ? truncateInline(JSON.stringify(args), 100)
            : undefined;

      const detailLines: { label: string; value: string }[] = [
        { label: "tool", value: name },
      ];
      if (query) detailLines.push({ label: "query", value: query });
      if (Object.keys(args).length > 0 && !query) {
        detailLines.push({ label: "args", value: JSON.stringify(args, null, 2) });
      }
      if (matchedResult) {
        const rd = (matchedResult.data ?? {}) as Record<string, unknown>;
        const ok = rd.ok !== false;
        const rowCount = (rd.row_count as number) ?? undefined;
        if (rowCount !== undefined) {
          detailLines.push({
            label: "result",
            value: `${rowCount} row${rowCount === 1 ? "" : "s"}`,
          });
        }
        const resultBody = (rd.result as Record<string, unknown>) ?? rd;
        detailLines.push({
          label: "raw",
          value: truncate(JSON.stringify(resultBody, null, 2), 4000),
        });
        result.push({
          id: `e-${e.seq}`,
          kind: "tool",
          title,
          summary,
          source,
          detailLines,
          status: ok ? "ok" : "error",
          at: e.created_at,
        });
      } else {
        // call without result yet → still running
        result.push({
          id: `e-${e.seq}`,
          kind: "tool",
          title,
          summary,
          source,
          detailLines,
          status: "running",
          at: e.created_at,
        });
      }
      continue;
    }
    if (e.type === "tool_result") {
      if (consumedResultSeqs.has(e.seq)) continue;
      const name = (d.name as string) || "result";
      const ok = d.ok !== false;
      result.push({
        id: `e-${e.seq}`,
        kind: "tool",
        title: `Result · ${name}`,
        summary: ok ? undefined : "error",
        detailLines: [
          { label: "raw", value: truncate(JSON.stringify(d, null, 2), 4000) },
        ],
        status: ok ? "ok" : "error",
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "finding_recorded") {
      const text = String(d.text ?? d.finding ?? "");
      result.push({
        id: `e-${e.seq}`,
        kind: "finding",
        title: e.summary?.trim() || "Finding recorded",
        summary: e.summary?.trim() ? undefined : truncateInline(text, 140),
        detailLines: [
          { label: "finding", value: text },
          ...(d.confidence != null
            ? [{ label: "confidence", value: String(d.confidence) }]
            : []),
        ],
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "reflexion") {
      const verdict = String(d.verdict_text ?? "");
      result.push({
        id: `e-${e.seq}`,
        kind: "reflexion",
        title: e.summary?.trim() || "Reflexion check",
        summary: e.summary?.trim() ? undefined : truncateInline(verdict, 140),
        detailLines: [{ label: "verdict", value: verdict }],
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "agent_thought") {
      const t = String(d.text ?? "");
      if (!t) continue;
      result.push({
        id: `e-${e.seq}`,
        kind: "thinking",
        title: "Reasoning",
        summary: truncateInline(t, 140),
        detailLines: [{ label: "thought", value: t }],
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "brief_drafted") {
      const dec = (d.decision as Record<string, unknown>) ?? {};
      result.push({
        id: `e-${e.seq}`,
        kind: "brief",
        title: e.summary?.trim() || "Brief drafted",
        summary: dec.action ? `Decision: ${String(dec.action)}` : undefined,
        detailLines: [{ label: "brief", value: JSON.stringify(d, null, 2) }],
        status: "ok",
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "case_closed") {
      result.push({
        id: `e-${e.seq}`,
        kind: "closed",
        title: "Case closed",
        summary: String(d.reason ?? ""),
        detailLines: [],
        status: "ok",
        at: e.created_at,
      });
      continue;
    }
    if (e.type === "error") {
      result.push({
        id: `e-${e.seq}`,
        kind: "error",
        title: "Error",
        summary: String(d.detail ?? d.reason ?? ""),
        detailLines: [{ label: "error", value: JSON.stringify(d, null, 2) }],
        status: "error",
        at: e.created_at,
      });
      continue;
    }
  }
  return result.reverse(); // newest first
}

function TimelineStep({
  step,
  firstAt,
}: {
  step: TimelineStep;
  firstAt?: string;
}) {
  const [open, setOpen] = useState(false);
  const hasDetail = step.detailLines.length > 0;

  const dotColor =
    step.status === "running"
      ? "var(--color-accent)"
      : step.status === "error"
        ? "var(--color-danger)"
        : step.kind === "finding"
          ? "var(--color-amber)"
          : step.kind === "brief"
            ? "var(--color-accent)"
            : "var(--color-ink-faint)";

  // Wall-clock with seconds is the primary timestamp. The relative
  // offset from case start is shown below it, bounded - cases that
  // span hours (because the operator re-investigated through chat
  // hours later) show "+1h+" instead of an absurd "+569:03".
  const wallClock = formatWallClock(step.at);
  const offsetLabel = firstAt ? boundedOffset(step.at, firstAt) : null;

  return (
    <div
      className="group py-2 border-b last:border-b-0"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <button
        onClick={() => hasDetail && setOpen((v) => !v)}
        className="w-full text-left grid items-start gap-3"
        style={{
          cursor: hasDetail ? "pointer" : "default",
          gridTemplateColumns: "auto 12px minmax(0,1fr) auto",
        }}
      >
        {/* Timestamp gutter - wall-clock primary, offset secondary */}
        <div
          className="text-right tabular-nums leading-tight shrink-0"
          style={{ width: 70 }}
        >
          <div
            className="text-[11px] font-mono"
            style={{ color: "var(--color-ink-strong)" }}
            title={step.at}
          >
            {wallClock}
          </div>
          {offsetLabel && (
            <div
              className="text-[9.5px] font-mono mt-0.5"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              {offsetLabel}
            </div>
          )}
        </div>

        {/* Status dot */}
        <div className="pt-[7px] flex justify-center shrink-0">
          {step.status === "running" ? (
            <span
              className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
              style={{ background: dotColor }}
            />
          ) : (
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: dotColor }}
            />
          )}
        </div>

        {/* Title + summary */}
        <div className="min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            {step.source && step.source !== "manthan" && (
              <span className="inline-flex shrink-0">
                <SourceIcon id={step.source} size={11} tinted />
              </span>
            )}
            <span
              className="text-[12.5px]"
              style={{ color: "var(--color-ink-strong)", fontWeight: 500 }}
            >
              {step.title}
            </span>
          </div>
          {step.summary && (
            <div
              className="text-[11.5px] font-mono mt-0.5 truncate"
              style={{ color: "var(--color-ink-muted)" }}
              title={step.summary}
            >
              {step.summary}
            </div>
          )}
        </div>

        {hasDetail && (
          <ChevronRight
            className="h-3 w-3 mt-[7px] shrink-0 transition-transform"
            style={{
              color: "var(--color-ink-faint)",
              transform: open ? "rotate(90deg)" : "rotate(0deg)",
            }}
          />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && hasDetail && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div
              className="mt-2 mb-1 space-y-2"
              style={{ paddingLeft: 64 + 12 + 12 }}
            >
              {step.detailLines.map((d, i) => (
                <div key={i}>
                  <div
                    className="text-[9.5px] uppercase tracking-wider"
                    style={{ color: "var(--color-ink-ghost)" }}
                  >
                    {d.label}
                  </div>
                  <pre
                    className="text-[11px] font-mono mt-0.5 whitespace-pre-wrap break-words p-2 max-h-60 overflow-auto"
                    style={{
                      color: "var(--color-ink-muted)",
                      background: "var(--color-surface)",
                      border: "1px solid var(--color-rule-soft)",
                    }}
                  >
                    {d.value}
                  </pre>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** "+0:01.4" style relative offset from the case start, mm:ss with
 *  centisecond precision under 10 seconds so the operator can feel the
 *  difference between back-to-back tool calls. */
/**
 * Bounded relative offset. Anything past 60 minutes returns "+1h+" -
 * cases that span hours are almost always cases the operator
 * re-investigated through chat later, and the operator cares about
 * the wall-clock not the multi-hour gap.
 */
function boundedOffset(at: string, firstAt: string): string | null {
  const t = new Date(at).getTime();
  const t0 = new Date(firstAt).getTime();
  const ms = Math.max(0, t - t0);
  const totalSec = Math.round(ms / 1000);
  if (totalSec === 0) return "+0:00";
  if (totalSec >= 3600) return "+1h+";
  const m = Math.floor(totalSec / 60);
  const s = totalSec - m * 60;
  return `+${m}:${String(s).padStart(2, "0")}`;
}

/** "14:21:09" - wall-clock with seconds for the primary timestamp. */
function formatWallClock(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function sniffSourceFromQuery(q: string): string | undefined {
  if (!q) return undefined;
  const m = q.match(
    /\b(stripe|salesforce|hubspot|intercom|zendesk|notion|slack|sentry|datadog|pagerduty|posthog)\b/i,
  );
  return m ? m[1].toLowerCase() : undefined;
}

function sniffSourceFromTool(name: string): string | undefined {
  if (!name) return undefined;
  if (name.startsWith("coral")) return "manthan";
  return undefined;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function truncateInline(s: string, n: number): string {
  const oneLine = s.replace(/\s+/g, " ").trim();
  return truncate(oneLine, n);
}

// ──────────────────────────────────────────────────────────────────────
// Receipts + agent chat replies (rendered below drafted actions)
// ──────────────────────────────────────────────────────────────────────

function CaseReceiptsAndChat({ events }: { events: CaseEvent[] }) {
  // Surface the post-investigation conversation: action receipts +
  // human/agent chat turns + human approval markers, in sequence order.
  const items = events.filter((e) =>
    [
      "action_executed",
      "action_failed",
      "action_verified",
      "drift_detected",
      "human_approved",
      "human_hold",
      "human_followup",
      "agent_thinking",
      "agent_reply",
    ].includes(e.type),
  );
  if (items.length === 0) return null;

  // Separate receipts (action_*/human_approved/hold) from chat
  // (human_followup/agent_*) so the visual hierarchy mirrors function.
  const receipts = items.filter((e) =>
    ["action_executed", "action_failed", "action_verified", "drift_detected", "human_approved", "human_hold"].includes(
      e.type,
    ),
  );
  const chat = items.filter((e) =>
    ["human_followup", "agent_thinking", "agent_reply"].includes(e.type),
  );

  return (
    // No inner border, no max-height. The parent CaseBand owns the
    // hairline + breathing room; the two subsections inside get vertical
    // rhythm so receipts read separately from the conversation.
    <div className="space-y-9">
      {receipts.length > 0 && (
        <div className="space-y-3">
          <Eyebrow>Receipts</Eyebrow>
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {receipts.map((e) => (
                <motion.div
                  key={e.seq}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <ReceiptOrChatItem event={e} />
                </motion.div>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
      {chat.length > 0 && (
        <div className="space-y-3">
          <Eyebrow>Conversation</Eyebrow>
          <ul className="space-y-4">
            <AnimatePresence initial={false}>
              {chat.map((e) => (
                <motion.div
                  key={e.seq}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <ReceiptOrChatItem event={e} />
                </motion.div>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
    </div>
  );
}

function ReceiptOrChatItem({ event }: { event: CaseEvent }) {
  const d = event.data ?? {};
  if (event.type === "action_executed") {
    return (
      <li className="flex items-baseline gap-2 text-[12px]">
        <span
          className="tabular-nums shrink-0"
          style={{ color: "var(--color-accent)" }}
        >
          ✓
        </span>
        <span style={{ color: "var(--color-ink-strong)" }}>
          {String((d as { kind?: string }).kind ?? "action")}
        </span>
        <span style={{ color: "var(--color-ink-muted)" }} className="truncate">
          {String((d as { summary?: string }).summary ?? "")}
        </span>
        {(d as { external_ref?: string }).external_ref && (
          <code
            className="ml-auto font-mono text-[10.5px]"
            style={{ color: "var(--color-ink-faint)" }}
          >
            {(d as { external_ref?: string }).external_ref}
          </code>
        )}
      </li>
    );
  }
  if (event.type === "action_failed" || event.type === "drift_detected") {
    return (
      <li className="flex items-baseline gap-2 text-[12px]">
        <span className="tabular-nums shrink-0" style={{ color: "var(--color-danger)" }}>
          ✗
        </span>
        <span style={{ color: "var(--color-ink-strong)" }}>
          {String((d as { kind?: string }).kind ?? event.type)}
        </span>
        <span style={{ color: "var(--color-danger)" }} className="truncate">
          {String((d as { error?: string }).error ?? "drift")}
        </span>
      </li>
    );
  }
  if (event.type === "action_verified") {
    return (
      <li className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
        ✓ verified · {String((d as { external_ref?: string }).external_ref ?? "")}
      </li>
    );
  }
  if (event.type === "human_approved") {
    return (
      <li className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {String((d as { member_email?: string }).member_email ?? "operator")} approved {(d as { action_ids?: string[] }).action_ids?.length ?? 0} action(s)
      </li>
    );
  }
  if (event.type === "human_hold") {
    return (
      <li className="text-[11.5px]" style={{ color: "var(--color-amber)" }}>
        {String((d as { member_email?: string }).member_email ?? "operator")} put case on hold
      </li>
    );
  }
  if (event.type === "human_followup") {
    return (
      <li className="text-[12.5px] leading-relaxed pl-4 border-l-2"
          style={{ borderColor: "var(--color-rule-strong)", color: "var(--color-ink)" }}>
        <span className="font-medium" style={{ color: "var(--color-ink-strong)" }}>
          You:{" "}
        </span>
        {String((d as { message?: string }).message ?? "")}
      </li>
    );
  }
  if (event.type === "agent_thinking") {
    return (
      <li className="text-[11.5px] inline-flex items-center gap-2"
          style={{ color: "var(--color-ink-faint)" }}>
        <span className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
              style={{ background: "var(--color-accent)" }} />
        Manthan is thinking…
      </li>
    );
  }
  if (event.type === "agent_reply") {
    return (
      <li className="text-[12.5px] leading-relaxed pl-4 border-l-2"
          style={{ borderColor: "var(--color-accent-line)", color: "var(--color-ink)" }}>
        <span className="font-medium" style={{ color: "var(--color-accent)" }}>
          Manthan:{" "}
        </span>
        {String((d as { text?: string }).text ?? "")}
      </li>
    );
  }
  return null;
}

function CaseChatInput({
  caseId,
  disabled,
}: {
  caseId: string;
  disabled: boolean;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    try {
      await chatWithCase(caseId, value);
      setText("");
    } catch (err) {
      console.error("chat send failed", err);
    } finally {
      setSending(false);
    }
  }

  return (
    <form
      onSubmit={send}
      className="shrink-0 mt-2 flex items-center gap-2 border-t pt-3"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div
        className="flex-1 flex items-center gap-2 px-2.5 py-1.5 border"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <span
          className="text-[10px] font-mono shrink-0"
          style={{ color: "var(--color-ink-ghost)", letterSpacing: "0.08em" }}
        >
          ASK
        </span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            disabled
              ? "Manthan is investigating…"
              : "Ask a follow-up - \"why fight not refund?\" or \"rewrite the email warmer\""
          }
          disabled={disabled || sending}
          className="flex-1 bg-transparent text-[12.5px] outline-none min-w-0"
          style={{ color: "var(--color-ink)" }}
        />
      </div>
      <button
        type="submit"
        disabled={!text.trim() || disabled || sending}
        className="text-[11.5px] font-semibold px-3.5 py-1.5 disabled:opacity-50 inline-flex items-center gap-1.5"
        style={{
          background: "var(--color-accent)",
          color: "var(--color-accent-ink)",
        }}
      >
        <Send className="h-3 w-3" strokeWidth={2.5} />
        {sending ? "Sending…" : "Send"}
      </button>
    </form>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Closed-case footer (hairline, just the chat toggle)
// ──────────────────────────────────────────────────────────────────────

/** Footer for terminal cases - no big verbs, just an option to open the
 *  agent chat for follow-up questions. Matches the layout space the
 *  CaseActionBar occupies in review mode so the page doesn't reflow on
 *  the review → closed transition. */
function ClosedCaseFooter({
  chatOpen,
  onToggleChat,
}: {
  chatOpen: boolean;
  onToggleChat: () => void;
}) {
  return (
    <footer
      className="shrink-0 border-t flex items-center justify-between px-10 md:px-12 h-12"
      style={{
        borderColor: "var(--color-rule-soft)",
        background: "var(--color-bg)",
      }}
    >
      <span
        className="eyebrow"
        style={{ color: "var(--color-ink-faint)" }}
      >
        Closed · no further action required
      </span>

      <button
        onClick={onToggleChat}
        className="text-[12px] italic font-display hover:opacity-90 inline-flex items-center gap-1.5"
        style={{
          color: chatOpen
            ? "var(--color-ink-strong)"
            : "var(--color-ink-muted)",
        }}
        title="Ask the agent about this case"
      >
        <span
          className="h-[7px] w-[7px] rounded-full"
          style={{
            background: chatOpen
              ? "var(--color-accent)"
              : "var(--color-rule-strong)",
            border: "1px solid var(--color-rule-strong)",
          }}
        />
        Talk to agent {chatOpen ? "↗" : "↘"}
      </button>
    </footer>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Action bar (footer)
// ──────────────────────────────────────────────────────────────────────

function CaseActionBar({
  caseRow,
  detail,
  status,
  setStatus,
  reset,
  caseId,
  onToggleChat,
  chatOpen,
}: {
  caseRow: WorkspaceCaseRow;
  detail: WorkspaceCaseDetail;
  status: CaseStatus;
  setStatus: (s: CaseStatus) => void;
  reset: () => void;
  caseId?: string;
  onToggleChat?: () => void;
  chatOpen?: boolean;
}) {
  const [denyOpen, setDenyOpen] = useState(false);
  const [escalateOpen, setEscalateOpen] = useState(false);
  if (caseRow.status === "executing") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <div className="text-[12.5px] flex items-center gap-3">
          <span
            style={{ color: "var(--color-accent)" }}
            className="font-medium inline-flex items-center gap-1.5"
          >
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
            Resolved by Manthan
          </span>
          <span style={{ color: "var(--color-ink-faint)" }}>·</span>
          <span style={{ color: "var(--color-ink-muted)" }}>
            <Strong>${caseRow.amount.toLocaleString()}</Strong> refunded · plan
            corrected · confirmation sent · under your{" "}
            <Code>refund.auto_under_500</Code> rule
          </span>
        </div>
        <span
          className="text-[11px]"
          style={{ color: "var(--color-ink-faint)", letterSpacing: "0.04em" }}
        >
          no approval needed
        </span>
      </footer>
    );
  }

  if (caseRow.status === "investigating") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <div className="text-[12.5px] flex items-center gap-2">
          <span
            className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
            style={{ background: "var(--color-info)" }}
          />
          <span style={{ color: "var(--color-ink-muted)" }}>
            Still investigating · {detail.actions.length} action
            {detail.actions.length === 1 ? "" : "s"} drafted but not fired ·
            awaiting reconciliation
          </span>
        </div>
        <span
          className="font-mono text-[11px]"
          style={{ color: "var(--color-ink-faint)" }}
        >
          will route when ready
        </span>
      </footer>
    );
  }

  if (status === "approved") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <div className="text-[12.5px] flex items-center gap-3">
          <span
            style={{ color: "var(--color-accent)" }}
            className="font-medium inline-flex items-center gap-1.5"
          >
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
            Resolved in 2m 14s
          </span>
          <span style={{ color: "var(--color-ink-faint)" }}>·</span>
          <span style={{ color: "var(--color-ink-muted)" }}>
            <span style={{ color: "var(--color-ink-strong)" }}>
              ${caseRow.amount.toLocaleString()}
            </span>{" "}
            actioned · brief posted to <span className="font-mono">#billing-ops</span>
          </span>
        </div>
        <button
          onClick={reset}
          className="text-[11.5px] inline-flex items-center gap-1.5 transition-colors"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <RotateCcw className="h-3 w-3" />
          Replay
        </button>
      </footer>
    );
  }

  if (status === "held") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <div className="text-[12.5px]" style={{ color: "var(--color-amber)" }}>
          Held by you · awaiting your edit
        </div>
        <button
          onClick={reset}
          className="text-[11.5px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Resume
        </button>
      </footer>
    );
  }

  const actionVerb =
    caseRow.status === "drafted" ? "drafted, awaiting approval" : "ready to fire";

  return (
    <>
      <footer
        className="px-7 py-3 border-t flex items-center justify-between gap-3"
        style={{
          borderColor: "var(--color-rule-soft)",
          background: "var(--color-surface)",
        }}
      >
        <div className="text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
          <span style={{ color: "var(--color-ink-strong)" }}>
            {detail.actions.length} action
            {detail.actions.length === 1 ? "" : "s"}
          </span>{" "}
          {actionVerb}
        </div>

        {/* Action row - left side has the secondary "negative" verbs, the
            right has the primary "act" verb. The chat trigger sits all the
            way right so it doesn't compete with Approve. */}
        <div className="flex items-center gap-4">
          {/* Escalate · Hold · Deny - text-only secondary verbs */}
          <button
            onClick={() => setEscalateOpen(true)}
            className="text-[12px] tracking-[0.02em] hover:opacity-90"
            style={{ color: "var(--color-ink-faint)" }}
          >
            Escalate
          </button>
          <button
            onClick={async () => {
              setStatus("held");
              if (caseId) {
                try {
                  await holdCase(caseId);
                } catch (e) {
                  console.error("hold failed", e);
                }
              }
            }}
            className="text-[12px] tracking-[0.02em] hover:opacity-90"
            style={{ color: "var(--color-ink-muted)" }}
          >
            Hold
          </button>
          <button
            onClick={() => setDenyOpen(true)}
            className="text-[12px] tracking-[0.02em] hover:opacity-90"
            style={{ color: "var(--color-danger)" }}
          >
            Deny
          </button>

          {/* Approve - primary verb */}
          <button
            disabled={status === "approving"}
            onClick={async () => {
              setStatus("approving");
              if (caseId) {
                try {
                  await approveCase(caseId);
                } catch (e) {
                  console.error("approve failed", e);
                }
              }
            }}
            className="text-[12.5px] font-medium h-9 px-4 disabled:opacity-70 rounded-[3px]"
            style={{
              background: "var(--color-accent)",
              color: "var(--color-accent-ink)",
            }}
          >
            {status === "approving" ? "Approving…" : "Approve"}
          </button>

          {/* Talk to agent - toggle the right-side chat drawer */}
          {onToggleChat && (
            <button
              onClick={onToggleChat}
              className="text-[12px] italic font-display hover:opacity-90 inline-flex items-center gap-1.5 ml-2"
              style={{
                color: chatOpen
                  ? "var(--color-ink-strong)"
                  : "var(--color-ink-muted)",
              }}
              title="Talk to the agent that wrote this brief"
            >
              <span
                className="h-[7px] w-[7px] rounded-full"
                style={{
                  background: chatOpen
                    ? "var(--color-accent)"
                    : "var(--color-rule-strong)",
                  border: "1px solid var(--color-rule-strong)",
                }}
              />
              Talk to agent {chatOpen ? "↗" : "↘"}
            </button>
          )}
        </div>
      </footer>

      <DenyModal
        open={denyOpen}
        onClose={() => setDenyOpen(false)}
        caseId={caseId}
        onDone={() => {
          setStatus("held");
          reset;
        }}
      />
      <EscalateModal
        open={escalateOpen}
        onClose={() => setEscalateOpen(false)}
        caseId={caseId}
        onDone={() => {
          setStatus("held");
        }}
      />
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Deny modal - operator rejects the agent's recommendation, captures
// the reason for the audit trail.
// ──────────────────────────────────────────────────────────────────────

function DenyModal({
  open,
  onClose,
  caseId,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  caseId?: string;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!caseId || !reason.trim()) return;
    setSubmitting(true);
    try {
      await denyCase(caseId, reason.trim());
      onDone();
      onClose();
      setReason("");
    } catch (e) {
      console.error("deny failed", e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ReasonModal
      open={open}
      onClose={onClose}
      title="Deny recommendation"
      eyebrow="Audit-logged"
      description="Manthan will mark the drafted actions as denied and close the case. The reason is captured for the audit trail."
      placeholder="Why are you denying? - e.g. customer reached out separately, will handle directly."
      submitLabel={submitting ? "Denying…" : "Deny"}
      reason={reason}
      onReasonChange={setReason}
      onSubmit={submit}
      submitting={submitting}
      tone="danger"
    />
  );
}

// ──────────────────────────────────────────────────────────────────────
// Escalate modal - hand the case off to a human team.
// ──────────────────────────────────────────────────────────────────────

function EscalateModal({
  open,
  onClose,
  caseId,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  caseId?: string;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!caseId) return;
    setSubmitting(true);
    try {
      await escalateCase(caseId, reason.trim() || undefined);
      onDone();
      onClose();
      setReason("");
    } catch (e) {
      console.error("escalate failed", e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ReasonModal
      open={open}
      onClose={onClose}
      title="Escalate to a human"
      eyebrow="Hand-off"
      description="Manthan stops acting on this case. The case stays open under your team's queue with the reason attached."
      placeholder="Why are you escalating? (optional)"
      submitLabel={submitting ? "Escalating…" : "Escalate"}
      reason={reason}
      onReasonChange={setReason}
      onSubmit={submit}
      submitting={submitting}
      tone="amber"
      reasonOptional
    />
  );
}

// ──────────────────────────────────────────────────────────────────────
// ReasonModal - shared shell for any "capture a reason then submit"
// modal so Deny and Escalate stay visually identical.
// ──────────────────────────────────────────────────────────────────────

function ReasonModal({
  open,
  onClose,
  title,
  eyebrow,
  description,
  placeholder,
  submitLabel,
  reason,
  onReasonChange,
  onSubmit,
  submitting,
  tone,
  reasonOptional,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow: string;
  description: string;
  placeholder: string;
  submitLabel: string;
  reason: string;
  onReasonChange: (next: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  tone: "danger" | "amber";
  reasonOptional?: boolean;
}) {
  const submitColor =
    tone === "danger" ? "var(--color-danger)" : "var(--color-amber)";

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50"
            style={{ background: "rgba(0,0,0,0.55)" }}
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none"
          >
            <div
              className="pointer-events-auto w-full max-w-lg border"
              style={{
                background: "var(--color-bg)",
                borderColor: "var(--color-rule)",
                borderRadius: "var(--radius-md)",
                boxShadow: "0 24px 64px rgba(0,0,0,0.55)",
              }}
            >
              <header
                className="px-5 py-4 border-b"
                style={{ borderColor: "var(--color-rule-soft)" }}
              >
                <div
                  className="eyebrow"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  {eyebrow}
                </div>
                <h3
                  className="font-display text-[22px] leading-tight mt-1"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  {title}
                </h3>
              </header>
              <div className="px-5 py-4 space-y-3">
                <p
                  className="text-[13px] leading-relaxed max-w-prose"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  {description}
                </p>
                <textarea
                  value={reason}
                  onChange={(e) => onReasonChange(e.target.value)}
                  placeholder={placeholder}
                  rows={4}
                  autoFocus
                  className="w-full px-3 py-2 rounded-[3px] border bg-transparent text-[13px] focus:outline-none resize-none"
                  style={{
                    borderColor: "var(--color-rule)",
                    color: "var(--color-ink-strong)",
                  }}
                />
              </div>
              <footer
                className="px-5 py-3 border-t flex items-center justify-end gap-4"
                style={{ borderColor: "var(--color-rule-soft)" }}
              >
                <button
                  onClick={onClose}
                  className="text-[12.5px] hover:opacity-90"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  Cancel
                </button>
                <button
                  onClick={onSubmit}
                  disabled={
                    submitting || (!reasonOptional && !reason.trim())
                  }
                  className="text-[12.5px] font-medium h-8 px-4 rounded-[3px] disabled:opacity-50"
                  style={{
                    background: submitColor,
                    color: "white",
                  }}
                >
                  {submitLabel}
                </button>
              </footer>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
