/**
 * CaseCardGrid - shared card-grid renderer for any list of cases.
 *
 * Originally defined inline inside Inbox.tsx; extracted so the Done /
 * Active / Escalated pages (which previously rendered a thin
 * `divide-y` list - a flat, dense terminal vibe that read as "log"
 * rather than "ledger of decisions") can use the same editorial card
 * treatment. The card is the right unit of attention for a case: it
 * carries the customer + verdict + Gemini-Flash one-line summary that
 * the operator scans in their morning triage.
 */

import { motion } from "motion/react";
import { Link } from "react-router-dom";

import { SourceIcon } from "@/components/ui/SourceIcon";
import {
  formatAge,
  formatAmount,
  humanizeTrigger,
  triggerToSource,
  type ApiCase,
  type CaseStatus,
} from "@/lib/api";

const STATUS_LABEL: Record<CaseStatus, string> = {
  investigating: "investigating",
  awaiting_approval: "awaiting nod",
  acting: "acting",
  resolved: "resolved",
  errored: "errored",
  escalated: "escalated",
};

const STATUS_COLOR: Record<CaseStatus, string> = {
  investigating: "var(--color-info)",
  awaiting_approval: "var(--color-amber)",
  acting: "var(--color-amber)",
  resolved: "var(--color-accent)",
  errored: "var(--color-danger)",
  escalated: "var(--color-danger)",
};

const VERDICT_VERB: Record<string, string> = {
  refund: "Refund",
  fight: "Fight",
  partial_credit: "Partial credit",
  accept: "Accept",
  escalate: "Escalate",
};

export function CaseCardGrid({
  cases,
  muted,
  urgent,
}: {
  cases: ApiCase[];
  /** Lower the surface opacity - for "closed" / archival groupings. */
  muted?: boolean;
  /** Add the amber left-edge accent - for "awaiting your nod". */
  urgent?: boolean;
}) {
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}
    >
      {cases.map((c, i) => (
        <CaseCard
          key={c.id}
          c={c}
          muted={muted}
          urgent={urgent}
          index={i}
        />
      ))}
    </div>
  );
}

export function CaseCard({
  c,
  muted,
  urgent,
  index,
}: {
  c: ApiCase;
  muted?: boolean;
  urgent?: boolean;
  index: number;
}) {
  const source = triggerToSource(c.trigger_surface);
  const verdict = c.decision_action
    ? VERDICT_VERB[c.decision_action] ?? c.decision_action
    : null;
  const verdictAmount = formatAmount(
    c.decision_amount_minor ?? c.amount_minor,
    c.currency ?? "usd",
  );
  // For closed cases the original trigger-text summary (Stripe dispute
  // id + charge id dump) reads like a log line, not a result. Skip the
  // raw card_summary and use the synthesizer's clean one-liner that
  // says what was decided + how much.
  const isClosed =
    c.status === "resolved" ||
    c.status === "errored" ||
    c.status === "escalated";
  const description = isClosed
    ? synthesizeDescription(c)
    : c.card_summary?.trim() || synthesizeDescription(c);

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, delay: Math.min(index * 0.02, 0.18) }}
      style={{ opacity: muted ? 0.75 : 1 }}
    >
      <Link
        to={`/app/case/${c.id}`}
        className={
          `case-card ${urgent ? "case-card-urgent" : ""} relative ` +
          "outline-none focus-visible:ring-2 focus-visible:ring-offset-2 " +
          "focus-visible:ring-[color:var(--color-accent)] " +
          "focus-visible:ring-offset-[color:var(--color-surface-2)]"
        }
      >
        <div className="px-4 pt-3.5 pb-4 h-full flex flex-col gap-2.5">
          {/* Header - case id (mono) on left, status (small caps) on right */}
          <div className="flex items-baseline justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <SourceIcon id={source} size={12} tinted />
              <span
                className="font-mono text-[10.5px] tabular-nums truncate"
                style={{ color: "var(--color-ink-faint)" }}
              >
                {c.short_id}
              </span>
            </div>
            <span
              className="text-[10px] uppercase tracking-[0.13em] whitespace-nowrap shrink-0"
              style={{ color: STATUS_COLOR[c.status] }}
            >
              {STATUS_LABEL[c.status]}
            </span>
          </div>

          {/* Customer + verdict line */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span
              className="text-[14px] truncate"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {c.customer_ref ?? "Unknown customer"}
            </span>
            {verdict && (
              <span
                className="text-[12px] tabular-nums"
                style={{ color: "var(--color-ink-muted)" }}
              >
                {verdict} · {verdictAmount}
              </span>
            )}
          </div>

          {/* Description - Gemini-Flash one-liner, Spectral italic so it
              reads as narrative summary rather than data. */}
          {description && (
            <p
              className="font-display text-[13px] leading-[1.45] line-clamp-3"
              style={{ color: "var(--color-ink-muted)" }}
            >
              {description}
            </p>
          )}

          <div className="flex-1" />

          {/* Footer - trigger surface + age */}
          <div
            className="flex items-baseline justify-between text-[10.5px] tabular-nums"
            style={{ color: "var(--color-ink-ghost)" }}
          >
            <span>{humanizeTrigger(c.trigger_surface)}</span>
            <span>{formatAge(c.created_at)} ago</span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

/** Fallback when the prettifier hasn't written a card_summary yet - a
 *  sensible synthetic line so the card never looks empty. */
export function synthesizeDescription(c: ApiCase): string {
  const amount = formatAmount(c.amount_minor, c.currency ?? "usd");
  if (c.status === "investigating") {
    return `Manthan is investigating a ${c.case_type ?? "case"} of ${amount} from ${c.customer_ref ?? "this customer"}.`;
  }
  if (c.status === "awaiting_approval" && c.decision_action) {
    return `Recommends ${c.decision_action} for ${c.customer_ref ?? "the customer"}. Waiting on your nod to fire the drafted actions.`;
  }
  if (c.status === "resolved") {
    const verb = c.decision_action
      ? VERDICT_VERB[c.decision_action] ?? c.decision_action
      : null;
    const amt = formatAmount(
      c.decision_amount_minor ?? c.amount_minor,
      c.currency ?? "usd",
    );
    if (verb && c.decision_amount_minor) {
      return `${verb} of ${amt} fired against the ${amount} ${c.case_type ?? "case"}. All actions executed.`;
    }
    if (verb) {
      return `${verb} fired. All drafted actions executed.`;
    }
    return "Resolved - all drafted actions executed.";
  }
  if (c.status === "escalated") {
    return "Escalated to a human team for review beyond Manthan.";
  }
  if (c.status === "errored") {
    return "Run errored mid-investigation; check the trace for the failure point.";
  }
  return `${c.case_type ?? "Case"} from ${c.customer_ref ?? "this customer"}.`;
}
