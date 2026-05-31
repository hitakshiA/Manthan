/**
 * Inbox - the operator's morning view, editorial-memo direction.
 *
 * The inbox is a stack of mini-memos. Each row is a compressed version of
 * the case workspace: HeaderStrip (case_id + customer + policy + status)
 * on top, headline case-line + dollar-transform in the body, TLDR + next
 * action in the footer.
 *
 * Sort order: investigating → awaiting_approval (oldest-first within) →
 * resolved/escalated/errored (newest-first within). One stack, no tabs.
 *
 * Realtime: subscribes to /api/inbox/stream over SSE (useInboxStream).
 * Wraps each row in `<Link to=/app/case/:id>` so the workspace opens on
 * click.
 */

import { Link, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";

import {
  formatAge,
  formatAmount,
  getMe,
  listDemoScenarios,
  triggerDemoScenario,
  type ApiCase,
  type CaseStatus,
  type DemoScenario,
} from "@/lib/api";
import { useInboxStream } from "@/lib/useInboxStream";
import { getSource } from "@/lib/sources";
import { storyFor } from "@/lib/scenarioStory";
import { ScenarioStory } from "@/components/app/ScenarioStory";

// ──────────────────────────────────────────────────────────────────────
// Status presentation - colors + labels for the right edge of the
// HeaderStrip. Match the WorkspaceMemo phase indicator palette.
// ──────────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<CaseStatus, string> = {
  investigating: "Investigating",
  awaiting_approval: "Awaiting nod",
  acting: "Acting",
  resolved: "Resolved",
  errored: "Errored",
  escalated: "Escalated",
};

const STATUS_COLOR: Record<CaseStatus, string> = {
  investigating: "var(--color-info)",
  awaiting_approval: "var(--color-amber)",
  acting: "var(--color-amber)",
  resolved: "var(--color-accent)",
  errored: "var(--color-danger)",
  escalated: "var(--color-danger)",
};

const ACTION_VERB: Record<string, string> = {
  refund: "Refund",
  fight: "Submit dispute evidence",
  partial_credit: "Issue partial credit",
  accept: "Accept",
  escalate: "Escalate to human",
};

// Sort priority: lower number = higher in the stack.
const STATUS_RANK: Record<CaseStatus, number> = {
  investigating: 0,
  acting: 1,
  awaiting_approval: 2,
  errored: 3,
  escalated: 4,
  resolved: 5,
};

// ──────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────

export default function Inbox() {
  const { cases, isLive, error, lastUpdatedAt } = useInboxStream(60);

  // Subtle "just refreshed" pulse on the meta line. Driven off the SSE
  // timestamp so it fires once per real update, not on every render.
  const [justUpdated, setJustUpdated] = useState(false);
  useEffect(() => {
    if (lastUpdatedAt === null) return;
    setJustUpdated(true);
    const t = window.setTimeout(() => setJustUpdated(false), 900);
    return () => window.clearTimeout(t);
  }, [lastUpdatedAt]);

  const sorted = useMemo(() => {
    if (!cases) return null;
    // Inbox is the active desk only - resolved / errored / escalated
    // cases live in /app/done. Without this filter, closed cases stay
    // listed at the bottom forever and the inbox never reaches "zero",
    // which defeats the whole "Inbox Zero" framing.
    const arr = cases.filter(
      (c) =>
        c.status !== "resolved" &&
        c.status !== "errored" &&
        c.status !== "escalated",
    );
    arr.sort((a, b) => {
      const ra = STATUS_RANK[a.status] ?? 99;
      const rb = STATUS_RANK[b.status] ?? 99;
      if (ra !== rb) return ra - rb;
      // Within awaiting_approval, oldest first (most overdue at top).
      if (a.status === "awaiting_approval") {
        return (
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
      }
      // Everything else: newest first.
      return (
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });
    return arr;
  }, [cases]);

  const counts = useMemo(() => {
    if (!sorted) return null;
    let awaiting = 0;
    let inflight = 0;
    for (const c of sorted) {
      if (c.status === "awaiting_approval") awaiting++;
      else if (c.status === "investigating" || c.status === "acting")
        inflight++;
    }
    return { total: sorted.length, awaiting, inflight };
  }, [sorted]);

  const isEmpty = sorted !== null && sorted.length === 0;

  // Empty state takes the full viewport on its own - no PageHeader above
  // (it would just duplicate the centered "Inbox zero." title), no outer
  // scroll. The state IS the page.
  if (isEmpty) {
    return (
      <div
        className="h-full w-full"
        style={{ background: "var(--color-bg)" }}
      >
        <InboxEmptyState />
      </div>
    );
  }

  return (
    <div
      className="h-full w-full overflow-y-auto"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="mx-auto flex flex-col"
        style={{
          maxWidth: 1100,
          padding: "40px 24px 64px",
          color: "var(--color-ink-strong)",
        }}
      >
        <PageHeader counts={counts} isLive={isLive} justUpdated={justUpdated} />

        {error && cases === null && (
          <p
            className="mt-8 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-danger)",
            }}
          >
            Couldn’t load the inbox: {error}
          </p>
        )}

        {cases === null && !error && (
          <p
            className="mt-12 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-faint)",
            }}
          >
            Loading the desk…
          </p>
        )}

        {sorted && sorted.length > 0 && (
          <>
            <ol className="flex flex-col gap-4 mt-12 list-none p-0">
            {sorted.map((c, i) => (
              <motion.li
                key={c.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.36,
                  delay: Math.min(i * 0.04, 0.4),
                  ease: [0.22, 0.61, 0.36, 1],
                }}
              >
                <CaseRow c={c} />
              </motion.li>
            ))}
          </ol>
          <DemoScenariosStrip />
          </>
        )}
      </div>
    </div>
  );
}

/**
 * DemoScenariosStrip - the launcher rendered below the case list when
 * the inbox already has cases. Compact resting state: a single quiet
 * "Launch a new case" button under a hairline. Clicking opens a
 * centered modal that surfaces the same three big trigger cards used
 * on the empty-state hero, so the choose-a-trigger UX is consistent
 * across both inbox states.
 *
 * The actual case fire still routes through `onCardFire`, so the
 * Aperture card opens its guided ScenarioStory just like on the empty
 * state - the picker just sits in front while the story takes over.
 */
function DemoScenariosStrip() {
  const { scenarios, firingId, onCardFire, storyOverlay } =
    useScenarioWithStory();
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);

  // Once a card fires we navigate away, but in the moment between click
  // and navigation we want the picker to dismiss so the operator sees
  // the seeding spinner against the underlying inbox, not floating in
  // a modal that's about to vanish anyway.
  useEffect(() => {
    if (firingId !== null) setOpen(false);
  }, [firingId]);

  if (scenarios === null || scenarios.length === 0) return null;

  const visible = TRIGGER_CARDS.filter((c) =>
    scenarios.some((s) => s.id === c.scenarioId),
  );

  return (
    <>
      <section className="mt-12 flex justify-center">
        <button
          type="button"
          onClick={() => setOpen(true)}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          className="inline-flex items-center gap-2.5 outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)]"
          style={{
            background: "var(--color-bg)",
            border: `1px solid ${
              hover ? "var(--color-rule-strong)" : "var(--color-rule)"
            }`,
            borderRadius: 10,
            padding: "14px 22px",
            color: "var(--color-ink)",
            fontFamily: "Spectral, serif",
            fontSize: 15.5,
            letterSpacing: "-0.005em",
            cursor: "pointer",
            transition:
              "border-color 200ms ease, transform 200ms ease, background 200ms ease",
            transform: hover ? "translateY(-1px)" : "translateY(0)",
          }}
        >
          <Plus
            size={15}
            strokeWidth={1.6}
            style={{ color: "var(--color-ink-muted)" }}
          />
          Launch a new case
        </button>
      </section>

      {open && (
        <LaunchPicker
          visible={visible}
          firingId={firingId}
          onClose={() => setOpen(false)}
          onFire={onCardFire}
        />
      )}

      {storyOverlay}
    </>
  );
}

/**
 * LaunchPicker - centered modal that mirrors the empty-state hero:
 * title + Geist Mono sub-eyebrow + three big trigger cards. Backdrop
 * blur dims the inbox underneath. Closes on backdrop click, ESC, or
 * the X button at top-right.
 */
function LaunchPicker({
  visible,
  firingId,
  onClose,
  onFire,
}: {
  visible: { scenarioId: string; sourceId: string; label: string }[];
  firingId: string | null;
  onClose: () => void;
  onFire: (id: string) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18 }}
      className="fixed inset-0 z-50 flex items-center justify-center px-6"
      onClick={onClose}
      style={{
        background: "color-mix(in oklch, var(--color-bg) 78%, transparent)",
        backdropFilter: "blur(14px) saturate(120%)",
        WebkitBackdropFilter: "blur(14px) saturate(120%)",
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Launch a new case"
    >
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.22, ease: [0.22, 0.61, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex flex-col items-center"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 18,
          padding: "60px 56px 52px",
          maxWidth: 1180,
          width: "100%",
          gap: 44,
          boxShadow:
            "0 30px 80px -20px color-mix(in oklch, var(--color-ink-strong) 35%, transparent)",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)]"
          style={{
            top: 14,
            right: 14,
            width: 36,
            height: 36,
            borderRadius: 999,
            background: "transparent",
            border: "none",
            color: "var(--color-ink-muted)",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <X size={18} strokeWidth={1.6} />
        </button>

        <div className="text-center flex flex-col items-center gap-5">
          <h3
            className="leading-[0.98]"
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(44px, 5vw, 64px)",
              color: "var(--color-ink-strong)",
              letterSpacing: "-0.022em",
              fontWeight: 400,
            }}
          >
            Launch a new case
          </h3>
          <p
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              fontSize: 12,
              color: "var(--color-ink-faint)",
              letterSpacing: "0.24em",
              textTransform: "uppercase",
            }}
          >
            Pick a trigger
          </p>
        </div>

        <div
          className="w-full grid"
          style={{
            gridTemplateColumns: `repeat(${visible.length}, minmax(0, 1fr))`,
            gap: 20,
          }}
        >
          {visible.map((card) => (
            <BigTriggerCard
              key={card.scenarioId}
              scenarioId={card.scenarioId}
              sourceId={card.sourceId}
              label={card.label}
              firing={firingId === card.scenarioId}
              disabled={firingId !== null && firingId !== card.scenarioId}
              onFire={() => onFire(card.scenarioId)}
            />
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// PageHeader - eyebrow + Spectral italic title + italic subtitle +
// live pulse dot.
// ──────────────────────────────────────────────────────────────────────

function PageHeader({
  counts,
  isLive,
  justUpdated,
}: {
  counts: { total: number; awaiting: number; inflight: number } | null;
  isLive: boolean;
  justUpdated: boolean;
}) {
  const title =
    counts === null
      ? "The desk."
      : counts.total === 0
        ? "Inbox zero."
        : counts.total === 1
          ? "One case on your desk."
          : `${humanCount(counts.total)} cases on your desk.`;

  return (
    <header className="flex flex-col gap-5">
      <Eyebrow>Inbox</Eyebrow>

      <h1
        className="leading-[1.06]"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: "clamp(30px, 3vw, 38px)",
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.014em",
          fontStyle: "italic",
          fontWeight: 400,
        }}
      >
        {title}
      </h1>

      {counts && counts.total > 0 && (
        <p
          className="leading-[1.5] inline-flex items-baseline flex-wrap gap-2"
          style={{
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: 15,
            color: "var(--color-ink-muted)",
            letterSpacing: "-0.003em",
          }}
        >
          {counts.awaiting > 0 ? (
            <>
              <span style={{ color: "var(--color-amber)" }}>
                {counts.awaiting} awaiting your nod
              </span>
              {counts.inflight > 0 && (
                <span style={{ color: "var(--color-rule-strong)" }}>·</span>
              )}
            </>
          ) : null}
          {counts.inflight > 0 && (
            <span style={{ color: "var(--color-info)" }}>
              {counts.inflight === 1
                ? "one in flight"
                : `${counts.inflight} in flight`}
            </span>
          )}
          {counts.awaiting === 0 && counts.inflight === 0 && (
            <span>everything’s closed.</span>
          )}
          <span
            className="ml-2 inline-block transition-opacity"
            title={isLive ? "Live" : "Reconnecting…"}
            style={{
              width: 7,
              height: 7,
              borderRadius: 999,
              background: isLive
                ? "var(--color-accent)"
                : "var(--color-ink-ghost)",
              opacity: justUpdated ? 1 : isLive ? 0.7 : 0.4,
              transform: `scale(${justUpdated ? 1.2 : 1})`,
              transitionDuration: "500ms",
            }}
          />
        </p>
      )}
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// CaseRow - one mini-memo. Outer chrome matches the WorkspaceMemo:
// 1px hairline, 6px radius, oklch warm dark.
// ──────────────────────────────────────────────────────────────────────

function CaseRow({ c }: { c: ApiCase }) {
  const policyName = c.policy_match?.rule_name ?? null;
  const tldr = c.card_summary?.trim() || synthesizeDescription(c);
  const next = synthesizeNextAction(c);
  const statusMeta = synthesizeStatusMeta(c);

  return (
    <Link
      to={`/app/case/${c.id}`}
      className="block outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)] focus-visible:rounded-md"
    >
      <article
        className="row-shell transition-colors duration-200 cursor-pointer"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 6,
          overflow: "hidden",
        }}
      >
        <HeaderStrip
          shortId={c.short_id}
          customer={c.customer_ref ?? "Unknown customer"}
          policyMatched={policyName}
          status={c.status}
          statusMeta={statusMeta}
        />
        <RowBody c={c} />
        <RowFooter tldr={tldr} next={next} status={c.status} />

        <style>{`
          a:hover > .row-shell { background: var(--color-surface); }
        `}</style>
      </article>
    </Link>
  );
}

function HeaderStrip({
  shortId,
  customer,
  policyMatched,
  status,
  statusMeta,
}: {
  shortId: string;
  customer: string;
  policyMatched: string | null;
  status: CaseStatus;
  statusMeta: string | null;
}) {
  return (
    <header
      className="flex items-center px-7 gap-3"
      style={{
        minHeight: 40,
        paddingTop: 8,
        paddingBottom: 8,
        borderBottom: "1px solid var(--color-rule-soft)",
      }}
    >
      <span
        className="font-mono text-[12px] uppercase tabular-nums shrink-0"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.14em",
        }}
      >
        CASE {shortId}
      </span>

      <span
        className="shrink-0"
        style={{ color: "var(--color-rule-strong)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[15px] shrink-0"
        style={{
          fontFamily: "Spectral, serif",
          color: "var(--color-ink)",
          letterSpacing: "0.005em",
        }}
      >
        {customer}
      </span>

      {policyMatched && (
        <>
          <span
            className="shrink-0"
            style={{ color: "var(--color-rule-strong)" }}
            aria-hidden
          >
            ·
          </span>
          <span
            className="font-mono text-[11.5px] tabular-nums inline-flex items-baseline gap-2 min-w-0"
            style={{
              color: "var(--color-ink-faint)",
              letterSpacing: "0.04em",
            }}
            title={`policy match · ${policyMatched}`}
          >
            <span
              className="uppercase shrink-0"
              style={{
                letterSpacing: "0.18em",
                color: "var(--color-ink-ghost)",
              }}
            >
              policy
            </span>
            <span
              className="truncate"
              style={{ color: "var(--color-ink-muted)" }}
            >
              {policyMatched}
            </span>
          </span>
        </>
      )}

      <span className="ml-auto inline-flex items-baseline gap-3 shrink-0">
        {statusMeta && (
          <span
            className="font-mono text-[11.5px] tabular-nums"
            style={{
              color: "var(--color-ink-faint)",
              letterSpacing: "0.04em",
            }}
          >
            {statusMeta}
          </span>
        )}
        <span
          className="text-[12.5px] uppercase"
          style={{
            color: STATUS_COLOR[status],
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          {STATUS_LABEL[status]}
        </span>
      </span>
    </header>
  );
}

function RowBody({ c }: { c: ApiCase }) {
  const caseLine = synthesizeCaseLine(c);
  return (
    <div
      className="flex items-start justify-between gap-10 px-7"
      style={{ paddingTop: 22, paddingBottom: 22, minHeight: 80 }}
    >
      <h2
        className="leading-[1.18] min-w-0 flex-1"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: 22,
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.010em",
          fontWeight: 400,
        }}
      >
        <em
          style={{
            fontStyle: "italic",
            color: "var(--color-ink)",
          }}
        >
          {caseLine}
        </em>
      </h2>

      <DollarTransform c={c} />
    </div>
  );
}

function DollarTransform({ c }: { c: ApiCase }) {
  const investigating =
    c.status === "investigating" || c.status === "acting";
  const dispute = formatAmount(c.amount_minor, c.currency ?? "usd");
  const recommended =
    c.decision_amount_minor != null
      ? formatAmount(c.decision_amount_minor, c.currency ?? "usd")
      : null;

  // Tint the recommended slot by what was decided. Refund full = neutral
  // (the company concedes); refund partial = accent (the win); fight = accent.
  const recommendKind = classifyDecision(c);
  const recommendedColor =
    recommendKind === "credit" || recommendKind === "fight"
      ? "var(--color-accent)"
      : recommendKind === "refund"
        ? "var(--color-ink)"
        : "var(--color-ink-faint)";

  return (
    <div className="flex items-baseline gap-4 shrink-0">
      <span
        className="font-mono tabular-nums"
        style={{
          color: "var(--color-ink)",
          fontSize: 18,
          letterSpacing: "-0.005em",
        }}
      >
        {dispute}
      </span>
      <span
        style={{
          color: "var(--color-ink-ghost)",
          fontSize: 16,
          transform: "translateY(-1px)",
        }}
        aria-hidden
      >
        →
      </span>
      <span
        className="tabular-nums whitespace-nowrap"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 26,
          color: recommendedColor,
          letterSpacing: "-0.008em",
          lineHeight: 1,
        }}
        aria-label={investigating ? "recommendation pending" : undefined}
      >
        {recommended ?? "…"}
      </span>
    </div>
  );
}

function RowFooter({
  tldr,
  next,
  status,
}: {
  tldr: string;
  next: string;
  status: CaseStatus;
}) {
  return (
    <div
      className="flex items-center justify-between gap-8 px-7"
      style={{
        minHeight: 44,
        paddingTop: 10,
        paddingBottom: 10,
        borderTop: "1px solid var(--color-rule-soft)",
      }}
    >
      <p
        className="min-w-0 truncate"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 14,
          color: "var(--color-ink-muted)",
          letterSpacing: "-0.003em",
          lineHeight: 1.5,
        }}
      >
        {tldr}
      </p>

      <div className="shrink-0 inline-flex items-baseline gap-2.5">
        <span
          className="text-[10.5px] uppercase"
          style={{
            color: "var(--color-ink-faint)",
            letterSpacing: "0.20em",
            fontWeight: 500,
          }}
        >
          Next
        </span>
        <span
          className="font-mono text-[13px] tabular-nums"
          style={{
            color:
              status === "resolved"
                ? "var(--color-ink-faint)"
                : "var(--color-ink)",
            letterSpacing: "0.005em",
          }}
        >
          {next}
        </span>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Synthesizers - derive editorial copy from the raw API case row.
// ──────────────────────────────────────────────────────────────────────

function synthesizeCaseLine(c: ApiCase): string {
  const amt = formatAmount(c.amount_minor, c.currency ?? "usd");
  const kind = c.case_type?.replace(/_/g, " ") ?? "case";
  if (kind === "chargeback") {
    return `vs. an ${amt} chargeback`;
  }
  if (kind === "refund request") {
    return `over an ${amt} refund request`;
  }
  if (kind === "duplicate charge") {
    return `over an alleged ${amt} duplicate charge`;
  }
  return `vs. an ${amt} ${kind}`;
}

function synthesizeDescription(c: ApiCase): string {
  if (c.status === "investigating") {
    return "Manthan is mid-investigation - reading across the connected sources to write the brief.";
  }
  if (c.status === "acting") {
    return "Drafted actions are firing in sequence. Live receipts in the workspace.";
  }
  if (c.status === "awaiting_approval" && c.decision_action) {
    return `Recommends ${humanizeAction(c.decision_action)}. Waiting on your nod to fire the drafted actions.`;
  }
  if (c.status === "resolved") {
    return c.decision_action
      ? `Resolved - ${humanizeAction(c.decision_action)} fired and the customer was notified.`
      : "Resolved.";
  }
  if (c.status === "escalated") {
    return "Escalated to a human - beyond Manthan’s policy envelope.";
  }
  if (c.status === "errored") {
    return "Run errored mid-investigation; check the trace for the failure point.";
  }
  return `${c.case_type?.replace(/_/g, " ") ?? "Case"} from ${c.customer_ref ?? "this customer"}.`;
}

function synthesizeNextAction(c: ApiCase): string {
  if (c.status === "resolved") return "Closed · all actions fired";
  if (c.status === "escalated") return "Awaiting human review";
  if (c.status === "errored") return "Retry from the workspace";
  if (c.status === "investigating") return "Brief in flight";
  if (c.status === "acting") return "Actions firing now";
  // awaiting_approval
  if (c.decision_action) {
    return humanizeAction(c.decision_action);
  }
  return "Awaiting your nod";
}

function synthesizeStatusMeta(c: ApiCase): string | null {
  if (c.status === "investigating") return null;
  if (c.status === "awaiting_approval") return null;
  if (c.status === "resolved" && c.resolved_at) {
    return `${formatAge(c.resolved_at)} ago`;
  }
  return `${formatAge(c.created_at)} ago`;
}

function classifyDecision(c: ApiCase): "credit" | "fight" | "refund" | null {
  if (c.decision_action == null) return null;
  if (c.decision_action === "fight") return "fight";
  if (c.decision_action === "partial_credit") return "credit";
  if (
    c.decision_action === "refund" &&
    c.decision_amount_minor != null &&
    c.amount_minor != null &&
    c.decision_amount_minor < c.amount_minor
  ) {
    return "credit";
  }
  if (c.decision_action === "refund") return "refund";
  return null;
}

function humanizeAction(action: string): string {
  return ACTION_VERB[action] ?? action.replace(/_/g, " ");
}

function humanCount(n: number): string {
  const words = [
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
  ];
  if (n <= 12) return words[n];
  return String(n);
}

// ──────────────────────────────────────────────────────────────────────
// Empty state - quiet editorial card with the demo-scenarios CTA.
// ──────────────────────────────────────────────────────────────────────

/**
 * Empty inbox - the morning-quiet state. When no cases have come in
 * yet, we don't pile a CTA panel into the page; the desk sits empty,
 * the Manthan mark sits at center as the only sign of life, and a
 * Spectral italic line says what's true.
 *
 * If demo scenarios are available, we offer them quietly underneath
 * so the operator can seed a case without hunting through the top bar.
 */
/**
 * useDemoScenarios - fetch + fire helper shared between the empty-
 * inbox hero and the persistent strip on the filled inbox. Keeps the
 * scenarios cached for the page lifetime; fires by POST then routes
 * to the new case workspace.
 */
function useDemoScenarios() {
  const [scenarios, setScenarios] = useState<DemoScenario[] | null>(null);
  const [firingId, setFiringId] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    listDemoScenarios()
      .then((r) => {
        if (cancelled) return;
        setScenarios(r.scenarios);
      })
      .catch(() => {
        if (cancelled) return;
        setScenarios([]);
      });
    // Fire-and-forget the /api/me fetch - used to route demo emails to
    // the operator's own inbox instead of the env-level fallback. Demo
    // still works without it (falls back to MANTHAN_DEMO_EMAIL_OVERRIDE).
    getMe()
      .then((me) => {
        if (cancelled) return;
        setUserEmail(me?.member?.email ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setUserEmail(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fire = useCallback(
    async (id: string) => {
      setFiringId(id);
      try {
        const r = await triggerDemoScenario(id, {
          demoEmailTo: userEmail,
        });
        navigate(`/app/case/${r.case_id}`);
      } catch (e) {
        console.warn("manthan: scenario fire failed", e);
        setFiringId(null);
      }
    },
    [navigate, userEmail],
  );

  return { scenarios, firingId, fire, userEmail };
}

/**
 * useScenarioWithStory - wraps useDemoScenarios with the guided story
 * overlay. When a scenario has a registered story (currently just
 * "aperture"), clicking its card opens the ScenarioStory and the case
 * fires from the last slide's CTA. Other scenarios fire immediately.
 *
 * Returns the same { scenarios, firingId } the cards expect, plus
 * `onCardFire(id)` which is what cards should call, and the JSX of
 * the active story overlay (caller renders it as a sibling).
 */
function useScenarioWithStory() {
  const { scenarios, firingId, fire, userEmail } = useDemoScenarios();
  const [storyScenarioId, setStoryScenarioId] = useState<string | null>(null);

  const onCardFire = useCallback(
    (id: string) => {
      const story = storyFor(id);
      if (story) {
        setStoryScenarioId(id);
      } else {
        fire(id);
      }
    },
    [fire],
  );

  const activeStory = storyScenarioId ? storyFor(storyScenarioId) : null;

  return {
    scenarios,
    firingId,
    onCardFire,
    storyOverlay: activeStory && storyScenarioId ? (
      <ScenarioStory
        story={activeStory}
        scenarioId={storyScenarioId}
        firing={firingId === storyScenarioId}
        userEmail={userEmail}
        onClose={() => {
          if (firingId !== storyScenarioId) setStoryScenarioId(null);
        }}
        onFire={() => fire(storyScenarioId)}
      />
    ) : null,
  };
}

/**
 * The three big trigger-type cards on the empty inbox. Each one maps
 * to a single scenario id in the backend catalog. We hide `quill`
 * (redundant with `aperture`'s stripe-webhook surface) and show one
 * card per distinct trigger kind: Stripe / Email / Slack.
 *
 * `aperture` carries the guided ScenarioStory overlay; the other two
 * fire immediately on click via the standard scenario-trigger path.
 */
const TRIGGER_CARDS: { scenarioId: string; sourceId: string; label: string }[] =
  [
    { scenarioId: "aperture", sourceId: "stripe", label: "Stripe Chargeback" },
    { scenarioId: "maya", sourceId: "resend", label: "Customer Email" },
    { scenarioId: "vermillion", sourceId: "slack", label: "Slack Thread" },
  ];

function InboxEmptyState() {
  const { scenarios, firingId, onCardFire, storyOverlay } =
    useScenarioWithStory();

  // Resolve the simplified card configs against the live scenario list.
  // Filter to the ones the backend actually has so we degrade gracefully
  // if a scenario id ever gets renamed/removed.
  const visible = scenarios
    ? TRIGGER_CARDS.filter((c) =>
        scenarios.some((s) => s.id === c.scenarioId),
      )
    : [];

  return (
    <div
      className="h-full w-full flex flex-col items-center justify-center px-8 select-none"
      style={{
        maxWidth: 1240,
        margin: "0 auto",
        gap: "clamp(56px, 7vh, 96px)",
      }}
    >
      {/* Hero: just the title + the prompt. No subtitle prose, no
          listening pill, no "sources live / agent idle" footer.
          Density removed by request - only what's necessary. */}
      <div className="w-full flex flex-col items-center text-center gap-7">
        <Insignia />

        <h2
          className="leading-[0.95]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(72px, 9vw, 128px)",
            color: "var(--color-ink-strong)",
            letterSpacing: "-0.028em",
            fontWeight: 400,
          }}
        >
          Inbox Zero
        </h2>

        <p
          className="leading-[1.2]"
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: 13,
            color: "var(--color-ink-faint)",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
          }}
        >
          Launch a demo case from here
        </p>
      </div>

      {visible.length > 0 && (
        <div
          className="w-full grid"
          style={{
            gridTemplateColumns: `repeat(${visible.length}, minmax(0, 1fr))`,
            gap: 20,
            maxWidth: 1080,
          }}
        >
          {visible.map((card) => (
            <BigTriggerCard
              key={card.scenarioId}
              scenarioId={card.scenarioId}
              sourceId={card.sourceId}
              label={card.label}
              firing={firingId === card.scenarioId}
              disabled={
                firingId !== null && firingId !== card.scenarioId
              }
              onFire={() => onCardFire(card.scenarioId)}
            />
          ))}
        </div>
      )}

      {storyOverlay}

      <style>{`
        @keyframes pulse-soft {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.92); }
        }
        @keyframes radar-pulse {
          0%, 100% { opacity: 0.95; }
          50% { opacity: 0.55; }
        }
      `}</style>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// BigTriggerCard - empty-state hero card. Brand-tinted square, big
// logo, big Spectral label underneath. Used only for the three trigger-
// type cards on Inbox Zero; the bottom-strip DemoScenariosStrip still
// uses the original compact ScenarioCard.
// ──────────────────────────────────────────────────────────────────────

function BigTriggerCard({
  sourceId,
  label,
  firing,
  disabled,
  onFire,
}: {
  scenarioId: string;
  sourceId: string;
  label: string;
  firing: boolean;
  disabled: boolean;
  onFire: () => void;
}) {
  const [hover, setHover] = useState(false);
  const sourceMeta = getSource(sourceId);
  const brandHex = sourceMeta?.simpleIcon?.hex;
  const EXTREME = new Set(["000000", "FFFFFF", "FDFDFD", "FEFEFE"]);
  const isExtreme = !brandHex || EXTREME.has(brandHex.toUpperCase());
  const tint = isExtreme ? "var(--color-rule-soft)" : `#${brandHex}14`;
  const ring = isExtreme ? "var(--color-rule-soft)" : `#${brandHex}33`;
  const ringHover = isExtreme
    ? "var(--color-rule-strong)"
    : `#${brandHex}66`;
  const fill = isExtreme ? "var(--color-ink-strong)" : `#${brandHex}`;
  const viewBox = sourceMeta?.simpleIcon?.viewBox ?? "0 0 24 24";

  const interactive = !firing && !disabled;

  return (
    <button
      type="button"
      onClick={onFire}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      disabled={!interactive}
      className="flex flex-col items-center justify-center text-center outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-line)]"
      style={{
        background: tint,
        border: `1px solid ${hover && interactive ? ringHover : ring}`,
        borderRadius: 16,
        padding: "56px 24px 48px",
        gap: 28,
        cursor: interactive ? "pointer" : "default",
        transition:
          "transform 240ms ease, border-color 240ms ease, opacity 240ms ease, background 240ms ease",
        opacity: disabled ? 0.45 : 1,
        transform:
          hover && interactive ? "translateY(-4px)" : "translateY(0)",
        minHeight: 260,
      }}
    >
      {firing ? (
        <Loader2
          size={64}
          strokeWidth={1.4}
          className="animate-spin"
          style={{ color: fill }}
        />
      ) : sourceMeta?.simpleIcon ? (
        <svg
          width={72}
          height={72}
          viewBox={viewBox}
          fill={fill}
          aria-hidden
          style={{
            filter: `drop-shadow(0 10px 28px ${fill}33)`,
          }}
        >
          <path d={sourceMeta.simpleIcon.path} />
        </svg>
      ) : (
        <span style={{ width: 72, height: 72 }} />
      )}

      <span
        className="leading-[1.1]"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: "clamp(22px, 2vw, 28px)",
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.012em",
          fontWeight: 400,
        }}
      >
        {firing ? "Seeding…" : label}
      </span>
    </button>
  );
}

/**
 * Insignia - the Manthan mark drawn LARGE. Three concentric radar arcs
 * emitting from an emerald core, with a slow halo pulse behind so the
 * empty state breathes instead of sitting frozen.
 */
function Insignia() {
  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: 124, height: 124 }}
    >
      {/* Halo wash - a soft radial behind the mark, brand-emerald tint. */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at center, var(--color-accent-soft) 0%, rgba(86,207,131,0.00) 70%)",
          animation: "pulse-soft 4s ease-in-out infinite",
        }}
      />

      <svg
        width={116}
        height={116}
        viewBox="0 0 32 32"
        fill="none"
        aria-hidden
        style={{ animation: "radar-pulse 6s ease-in-out infinite" }}
      >
        {/* Outermost arc */}
        <path
          d="M 16 2 A 14 14 0 0 1 16 30"
          stroke="var(--color-ink-ghost)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        {/* Middle arc */}
        <path
          d="M 16 6 A 10 10 0 0 1 16 26"
          stroke="var(--color-ink)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        {/* Inner arc */}
        <path
          d="M 16 11 A 5 5 0 0 1 16 21"
          stroke="var(--color-ink-strong)"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
        {/* Emerald core - the steady center the radar emits from. */}
        <circle
          cx="16"
          cy="16"
          r="2.2"
          fill="var(--color-accent)"
          style={{
            filter: "drop-shadow(0 0 8px var(--color-accent-line))",
          }}
        />
      </svg>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow primitive.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}
