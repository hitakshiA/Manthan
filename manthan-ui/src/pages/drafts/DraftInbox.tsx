/**
 * DraftInbox - Inbox, editorial-memo direction (DRAFT).
 *
 * The inbox is a stack of mini-memos. Each row is a horizontally-laid-out
 * compact version of the Workspace memo: HeaderStrip on top, the case-line
 * in Spectral italic with the dollar transform on the right, and a quiet
 * bottom row with TLDR + next action.
 *
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │ CASE [id] · [Customer]    [policy badge]      [STATUS RIGHT]│
 *   │ ─────────────────────────────────────────────────────────── │
 *   │  [Spectral italic case-line]         $X,XXX  →  $XXX        │
 *   │  One-sentence TLDR.                                         │
 *   │  Next: [verb the agent's about to fire]                     │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * Sort by status priority: investigating → awaiting → resolved (newest-
 * resolved first within each group). No tabs, no filters. Just six cases
 * on the desk, presented as if a senior analyst left a stack of memos on
 * your chair overnight.
 *
 * Throwaway draft - route /app/draft-inbox.
 */

import { motion } from "motion/react";

// ──────────────────────────────────────────────────────────────────────
// Mock data - six cases across three status states.
// Sorted in this array as: investigating → awaiting → resolved
// (newest-resolved first within each group).
// ──────────────────────────────────────────────────────────────────────

type Status = "investigating" | "awaiting_approval" | "resolved";

interface InboxCase {
  shortId: string;
  customer: string;
  caseLine: string;
  disputedAmount: string;
  /** null when investigation has not yet produced a recommendation */
  recommendedAmount: string | null;
  status: Status;
  /** policy id like "documented-incident-prorata-credit" or null */
  policyMatched: string | null;
  /** one-sentence summary, Spectral italic muted */
  tldr: string;
  /** next thing the agent is queued to do or the closing line for resolved */
  nextAction: string;
  /** investigating → ETA string · resolved → "2h ago" · awaiting → null */
  statusMeta: string | null;
  /** whether the recommended action is "fight" (full deny) - colors the recommended amount neutral instead of accent green when $X→$0 */
  recommendKind: "credit" | "fight" | "refund" | null;
}

const CASES: InboxCase[] = [
  // ── INVESTIGATING (top priority) ──────────────────────────────────
  {
    shortId: "CSE-104287",
    customer: "TechCorp",
    caseLine: "vs. a $1,200 chargeback over a duplicate-charge claim",
    disputedAmount: "$1,200",
    recommendedAmount: null,
    status: "investigating",
    policyMatched: null,
    tldr:
      "Manthan is cross-referencing Stripe charge history against PostHog session data to confirm or refute the duplicate-charge claim.",
    nextAction: "Brief in ~47s",
    statusMeta: "ETA 47s",
    recommendKind: null,
  },

  // ── AWAITING APPROVAL (your desk) ─────────────────────────────────
  {
    shortId: "W7R-APERTURE",
    customer: "Aperture Analytics",
    caseLine: "vs. an $8,400 chargeback over Custom Reports degradation",
    disputedAmount: "$8,400",
    recommendedAmount: "$560",
    status: "awaiting_approval",
    policyMatched: "documented-incident-prorata-credit",
    tldr:
      "Datadog confirms a 48h SLA breach during the disputed window. Notion policy mandates 2/30 × $8,400 = $560 partial credit.",
    nextAction: "Issue Stripe refund $560",
    statusMeta: null,
    recommendKind: "credit",
  },
  {
    shortId: "NWL-19284",
    customer: "Northwind Logistics",
    caseLine: "vs. a $9,200 chargeback claiming vendor failure",
    disputedAmount: "$9,200",
    recommendedAmount: "$0",
    status: "awaiting_approval",
    policyMatched: "friendly-fraud-fight",
    tldr:
      "Nineteen months of healthy usage, fourteen active users two days after dispute, NPS 9 three weeks prior. Recommend fight.",
    nextAction: "Submit Stripe dispute evidence",
    statusMeta: null,
    recommendKind: "fight",
  },
  {
    shortId: "CSE-104291",
    customer: "Helix Bio",
    caseLine: "vs. an $11,000 chargeback after refund-SLA breach",
    disputedAmount: "$11,000",
    recommendedAmount: "$11,000",
    status: "awaiting_approval",
    policyMatched: "refund-sla-breach-concede",
    tldr:
      "Refund request from 2026-05-04 went unactioned for 23 days; our SLA is 5. Stripe arbitration would not favor us - concede in full.",
    nextAction: "Issue full Stripe refund $11,000",
    statusMeta: null,
    recommendKind: "refund",
  },

  // ── RESOLVED (newest first) ───────────────────────────────────────
  {
    shortId: "CSE-104255",
    customer: "Summit Payments",
    caseLine: "vs. a $7,000 chargeback over allegedly unfulfilled service",
    disputedAmount: "$7,000",
    recommendedAmount: "$0",
    status: "resolved",
    policyMatched: "friendly-fraud-fight",
    tldr:
      "Closed: evidence packet submitted to Stripe with PostHog usage logs and signed contract. Customer notified; case logged in HubSpot.",
    nextAction: "Closed · all actions fired",
    statusMeta: "2h ago",
    recommendKind: "fight",
  },
  {
    shortId: "CSE-104101",
    customer: "Quill Logistics",
    caseLine: "vs. a $9,000 chargeback over a non-renewal dispute",
    disputedAmount: "$9,000",
    recommendedAmount: "$0",
    status: "resolved",
    policyMatched: "friendly-fraud-fight",
    tldr:
      "Closed: contract clearly auto-renewed with 60-day notice; customer missed the window. Evidence submitted, decision logged.",
    nextAction: "Closed · all actions fired",
    statusMeta: "6h ago",
    recommendKind: "fight",
  },
];

// Counts derived for the subtitle line. Memoized at module scope since
// the data is static.
const STATUS_COUNTS = CASES.reduce(
  (acc, c) => {
    acc[c.status] += 1;
    return acc;
  },
  { investigating: 0, awaiting_approval: 0, resolved: 0 } as Record<Status, number>,
);

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

export default function DraftInbox() {
  return (
    <div
      className="h-full w-full overflow-y-auto"
      style={{ background: "var(--color-bg)" }}
    >
      {/* Outer padding mirrors WorkspaceMemo (px-6 py-6) so the inbox sits
           in the same gutter as the case workspace it leads to. The inner
           column caps at ~1100px for editorial readability - the AppShell
           sidebar consumes the remainder. */}
      <div
        className="mx-auto flex flex-col"
        style={{
          maxWidth: 1100,
          padding: "40px 24px 64px",
          color: "rgba(255,255,255,0.92)",
        }}
      >
        {/* ── PAGE HEADER ────────────────────────────────────────── */}
        <PageHeader />

        {/* ── STACK ────────────────────────────────────────────────
              16px vertical gap between rows. Each row stagger-fades on
              mount: 6px slide + opacity, 60ms apart. */}
        <ol className="flex flex-col gap-4 mt-12 list-none p-0">
          {CASES.map((c, i) => (
            <motion.li
              key={c.shortId}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.45,
                delay: i * 0.06,
                ease: [0.22, 0.61, 0.36, 1],
              }}
            >
              <CaseRow c={c} />
            </motion.li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// PageHeader - eyebrow + Spectral italic title + italic subtitle.
// Mirrors the WorkspaceMemo hero typography ramp.
// ──────────────────────────────────────────────────────────────────────

function PageHeader() {
  const awaiting = STATUS_COUNTS.awaiting_approval;
  const investigating = STATUS_COUNTS.investigating;
  return (
    <header className="flex flex-col gap-5">
      <Eyebrow>Inbox</Eyebrow>

      <h1
        className="leading-[1.06]"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: "clamp(30px, 3vw, 38px)",
          color: "rgba(255,255,255,0.96)",
          letterSpacing: "-0.014em",
          fontStyle: "italic",
          fontWeight: 400,
        }}
      >
        Six cases on your desk.
      </h1>

      <p
        className="leading-[1.5]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 15,
          color: "rgba(255,255,255,0.55)",
          letterSpacing: "-0.003em",
        }}
      >
        {awaiting} awaiting your nod
        <span className="mx-2" style={{ color: "rgba(255,255,255,0.22)" }}>
          ·
        </span>
        {investigating === 1
          ? "one in flight"
          : `${investigating} in flight`}
        .
      </p>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// CaseRow - the mini-memo. Same outer chrome as WorkspaceMemo:
//   1px hairline border, 6px radius, oklch warm dark fill.
// Hover: row background brightens from 0.00 → 0.025 over the surface.
// ──────────────────────────────────────────────────────────────────────

function CaseRow({ c }: { c: InboxCase }) {
  return (
    <article
      className="group transition-colors duration-200 cursor-pointer"
      style={{
        background: "oklch(0.135 0.006 75)",
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      {/* Hover brighten - a quiet 0.02 → 0.04 wash inside the frame,
           not on the border, so the hairline stays consistent. */}
      <div
        className="row-surface transition-colors duration-200"
        style={{
          background: "transparent",
        }}
      >
        <HeaderStrip c={c} />
        <RowBody c={c} />
        <RowFooter c={c} />
      </div>

      {/* Scoped hover style - uses :hover on the article and bubbles to
           a child so we don't have to track hover state in React. The
           selector targets the .row-surface inside the article. */}
      <style>{`
        article:hover > .row-surface { background: rgba(255,255,255,0.025); }
      `}</style>
    </article>
  );
}

// ──────────────────────────────────────────────────────────────────────
// HeaderStrip - case identity. 40px tall. Mirrors WorkspaceMemo's
// HeaderStrip exactly, just compressed for the inbox.
// ──────────────────────────────────────────────────────────────────────

function HeaderStrip({ c }: { c: InboxCase }) {
  return (
    <header
      className="flex items-center px-7"
      style={{
        height: 40,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span
        className="font-mono text-[12px] uppercase tabular-nums shrink-0"
        style={{
          color: "rgba(255,255,255,0.60)",
          letterSpacing: "0.14em",
        }}
      >
        CASE {c.shortId}
      </span>

      <span
        className="mx-3 shrink-0"
        style={{ color: "rgba(255,255,255,0.22)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[15px] shrink-0"
        style={{
          fontFamily: "Spectral, serif",
          color: "rgba(255,255,255,0.86)",
          letterSpacing: "0.005em",
        }}
      >
        {c.customer}
      </span>

      {c.policyMatched && (
        <>
          <span
            className="mx-3 shrink-0"
            style={{ color: "rgba(255,255,255,0.18)" }}
            aria-hidden
          >
            ·
          </span>
          {/* Policy badge - small mono, matches WorkspaceMemo's pattern */}
          <span
            className="font-mono text-[11.5px] tabular-nums inline-flex items-baseline gap-2 min-w-0"
            style={{
              color: "rgba(255,255,255,0.48)",
              letterSpacing: "0.04em",
            }}
            title={`policy match · ${c.policyMatched}`}
          >
            <span
              className="uppercase shrink-0"
              style={{
                letterSpacing: "0.18em",
                color: "rgba(255,255,255,0.34)",
              }}
            >
              policy
            </span>
            <span
              className="truncate"
              style={{ color: "rgba(255,255,255,0.58)" }}
            >
              {c.policyMatched}
            </span>
          </span>
        </>
      )}

      {/* Status - right-aligned, color-on-text per the design constraint
           (no chips for status). */}
      <StatusLabel status={c.status} meta={c.statusMeta} />
    </header>
  );
}

function StatusLabel({
  status,
  meta,
}: {
  status: Status;
  meta: string | null;
}) {
  const { label, color } = STATUS_PRESENTATION[status];
  return (
    <span className="ml-auto inline-flex items-baseline gap-3 shrink-0">
      {meta && (
        <span
          className="font-mono text-[11.5px] tabular-nums"
          style={{
            color: "rgba(255,255,255,0.42)",
            letterSpacing: "0.04em",
          }}
        >
          {meta}
        </span>
      )}
      <span
        className="text-[13px] uppercase"
        style={{
          color,
          letterSpacing: "0.22em",
          fontWeight: 500,
        }}
      >
        {label}
      </span>
    </span>
  );
}

const STATUS_PRESENTATION: Record<Status, { label: string; color: string }> = {
  investigating: { label: "Investigating", color: "rgba(85, 135, 198, 0.92)" },
  awaiting_approval: {
    label: "Awaiting nod",
    color: "rgba(232, 162, 58, 0.92)",
  },
  resolved: { label: "Resolved", color: "var(--color-accent, #56cf83)" },
};

// ──────────────────────────────────────────────────────────────────────
// RowBody - the headline. Spectral italic case-line on the left, the
// dollar transform on the right.
//
//   ~80px tall. The case-line gets clamp to keep it from ever wrapping
//   awkwardly past two lines; the dollar transform is rigid-width and
//   never breaks.
// ──────────────────────────────────────────────────────────────────────

function RowBody({ c }: { c: InboxCase }) {
  return (
    <div
      className="flex items-start justify-between gap-10 px-7"
      style={{ paddingTop: 22, paddingBottom: 22, minHeight: 80 }}
    >
      {/* LEFT - case-line. Customer name in regular Spectral, the
           "vs. an $X chargeback over Y" in italic muted. */}
      <h2
        className="leading-[1.18] min-w-0 flex-1"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: 22,
          color: "rgba(255,255,255,0.96)",
          letterSpacing: "-0.010em",
          fontWeight: 400,
        }}
      >
        <em
          style={{
            fontStyle: "italic",
            color: "rgba(255,255,255,0.66)",
          }}
        >
          {c.caseLine}
        </em>
      </h2>

      {/* RIGHT - dollar transform. $X,XXX → $XXX
           Claim is mono tabular 18px muted. Arrow is muted ascii →.
           Recommended is Spectral italic 26px green (or muted ink when
           investigating / when it's a $X → $X full-refund). */}
      <DollarTransform c={c} />
    </div>
  );
}

function DollarTransform({ c }: { c: InboxCase }) {
  // While investigating, the recommended slot reads as a placeholder
  // ellipsis in muted ink - we don't pretend to know the verdict yet.
  const investigating = c.status === "investigating";
  const recommendedColor =
    c.recommendKind === "credit" || c.recommendKind === "fight"
      ? "var(--color-accent, #56cf83)"
      : c.recommendKind === "refund"
        ? "rgba(255,255,255,0.88)" // full-refund concedes are neutral
        : "rgba(255,255,255,0.36)";

  return (
    <div className="flex items-baseline gap-4 shrink-0">
      <span
        className="font-mono tabular-nums"
        style={{
          color: "rgba(255,255,255,0.74)",
          fontSize: 18,
          letterSpacing: "-0.005em",
        }}
      >
        {c.disputedAmount}
      </span>
      <span
        style={{
          color: "rgba(255,255,255,0.28)",
          fontSize: 16,
          transform: "translateY(-1px)",
        }}
        aria-hidden
      >
        →
      </span>
      {investigating ? (
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
          aria-label="recommendation pending"
        >
          …
        </span>
      ) : (
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
        >
          {c.recommendedAmount}
        </span>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RowFooter - bottom row. TLDR italic muted on left, "Next: ..." mono
// on the right. ~32px tall. Hairline above to separate from the body.
// ──────────────────────────────────────────────────────────────────────

function RowFooter({ c }: { c: InboxCase }) {
  return (
    <div
      className="flex items-center justify-between gap-8 px-7"
      style={{
        height: 44,
        borderTop: "1px solid rgba(255,255,255,0.05)",
      }}
    >
      <p
        className="min-w-0 truncate"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 14,
          color: "rgba(255,255,255,0.54)",
          letterSpacing: "-0.003em",
          lineHeight: 1.5,
        }}
      >
        {c.tldr}
      </p>

      <div className="shrink-0 inline-flex items-baseline gap-2.5">
        <span
          className="text-[10.5px] uppercase"
          style={{
            color: "rgba(255,255,255,0.40)",
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
              c.status === "resolved"
                ? "rgba(255,255,255,0.46)"
                : "rgba(255,255,255,0.78)",
            letterSpacing: "0.005em",
          }}
        >
          {c.nextAction}
        </span>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow - uppercase letterspaced section label. Identical to the
// helper in WorkspaceMemo.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: "rgba(255,255,255,0.50)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}
