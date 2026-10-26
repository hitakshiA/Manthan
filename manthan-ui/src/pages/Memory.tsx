/**
 * Memory - per-customer episodic recall.
 *
 * Editorial form: a customer ledger, not a bubble-pill card grid. Each
 * customer is one row in a hairline-separated stack with the counts as
 * tabular numerals, the verdicts as inline text, never as four chips
 * crammed into the headline.
 */

import { Link, useParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  EmptyRow,
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import { Badge } from "@/components/ui/Badge";
import {
  formatAge,
  formatAmount,
  getCustomerCases,
  humanizeTrigger,
  listMemoryCustomers,
  type CustomerCaseRow,
  type CustomerMemoryRow,
} from "@/lib/api";

export default function Memory() {
  const params = useParams<{ customerRef?: string }>();
  if (params.customerRef) return <CustomerDrillDown ref_={params.customerRef} />;
  return <CustomerList />;
}

// ──────────────────────────────────────────────────────────────────────
// Index - list every customer Manthan has touched.
// ──────────────────────────────────────────────────────────────────────

function CustomerList() {
  const [rows, setRows] = useState<CustomerMemoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMemoryCustomers()
      .then((r) => setRows(r.customers))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <PageBody>
      <PageHeader
        eyebrow="Episodic memory"
        title="What Manthan remembers"
        meta="Every customer this workspace has seen and what was decided. Click through for the full case history."
      />

      {error && <ErrorRow>Couldn&apos;t load customer memory: {error}</ErrorRow>}

      {rows === null && !error && <LoadingRow />}

      {rows?.length === 0 && (
        <EmptyRow>
          Nothing here yet. Manthan populates this once cases land.
        </EmptyRow>
      )}

      {rows && rows.length > 0 && (
        <Section>
          <ul className="divide-y" style={{ borderColor: "var(--color-rule-soft)" }}>
            {rows.map((r) => (
              <CustomerRow key={r.customer_ref} row={r} />
            ))}
          </ul>
        </Section>
      )}
    </PageBody>
  );
}

function CustomerRow({ row }: { row: CustomerMemoryRow }) {
  const refunded =
    row.refunded_total_minor > 0
      ? formatAmount(row.refunded_total_minor, "usd")
      : null;

  // Build the "decisions" inline line as tracked text, not pills.
  const decisionParts: string[] = [];
  if (row.refunds > 0) decisionParts.push(`${row.refunds} refunded`);
  if (row.fights > 0) decisionParts.push(`${row.fights} fought`);
  if (row.escalated > 0) decisionParts.push(`${row.escalated} escalated`);
  const decisionsLine = decisionParts.join(" · ");

  return (
    <li
      style={{ borderColor: "var(--color-rule-soft)" }}
      className="first:border-t"
    >
      <Link
        to={`/app/memory/${encodeURIComponent(row.customer_ref)}`}
        className="grid grid-cols-[1fr_auto_auto] items-baseline gap-6 px-1 py-4 hover:bg-[var(--color-surface)] transition-colors"
      >
        <div className="min-w-0">
          <div
            className="text-[15px] truncate"
            style={{ color: "var(--color-ink-strong)" }}
          >
            {row.customer_ref}
          </div>
          {decisionsLine && (
            <div
              className="mt-1 text-[12px] tabular-nums"
              style={{ color: "var(--color-ink-muted)" }}
            >
              {decisionsLine}
              {refunded && (
                <>
                  {" · "}
                  <span style={{ color: "var(--color-accent)" }}>{refunded}</span> recovered
                </>
              )}
            </div>
          )}
        </div>

        <div
          className="text-right text-[12.5px] tabular-nums"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <div style={{ color: "var(--color-ink-strong)" }}>
            {row.total_cases}
          </div>
          <div className="text-[10.5px] uppercase tracking-[0.12em] mt-0.5">
            case{row.total_cases === 1 ? "" : "s"}
          </div>
        </div>

        <div
          className="text-right text-[11.5px] tabular-nums whitespace-nowrap"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {row.last_seen ? formatAge(row.last_seen) + " ago" : "-"}
          <ArrowRight
            className="inline h-3 w-3 ml-2 opacity-0 group-hover:opacity-100"
            style={{ color: "var(--color-ink-faint)" }}
          />
        </div>
      </Link>
    </li>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Drill-down - one customer's full case history.
// ──────────────────────────────────────────────────────────────────────

function CustomerDrillDown({ ref_ }: { ref_: string }) {
  const [data, setData] = useState<CustomerCaseRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCustomerCases(ref_)
      .then((r) => setData(r.cases))
      .catch((e: Error) => setError(e.message));
  }, [ref_]);

  const stats = useMemo(() => {
    if (!data) return null;
    return {
      total: data.length,
      refunds: data.filter((c) => c.decision_action === "refund").length,
      fights: data.filter((c) => c.decision_action === "fight").length,
      refundedMinor: data
        .filter((c) => c.decision_action === "refund")
        .reduce((acc, c) => acc + (c.decision_amount_minor ?? 0), 0),
    };
  }, [data]);

  const metaLine = stats ? (
    <span className="tabular-nums">
      {stats.total} case{stats.total === 1 ? "" : "s"} · {stats.refunds} refunded
      {stats.refundedMinor > 0 && (
        <>
          {" "}({formatAmount(stats.refundedMinor, "usd")})
        </>
      )}
      {stats.fights > 0 && <> · {stats.fights} fought</>}
    </span>
  ) : null;

  return (
    <PageBody>
      <Link
        to="/app/memory"
        className="text-[11px] tracking-[0.04em] hover:opacity-90"
        style={{ color: "var(--color-ink-faint)" }}
      >
        ← All customers
      </Link>
      <PageHeader eyebrow="Customer memory" title={ref_} meta={metaLine} />

      {error && <ErrorRow>{error}</ErrorRow>}
      {data === null && !error && <LoadingRow />}

      {data && (
        <ul className="divide-y" style={{ borderColor: "var(--color-rule-soft)" }}>
          {data.map((c) => (
            <CaseLine key={c.id} c={c} />
          ))}
        </ul>
      )}
    </PageBody>
  );
}

function CaseLine({ c }: { c: CustomerCaseRow }) {
  const isResolved = c.status === "resolved";
  const isProblem = c.status === "errored" || c.status === "escalated";

  const statusColor = isResolved
    ? "var(--color-accent)"
    : isProblem
      ? "var(--color-danger)"
      : c.status === "investigating"
        ? "var(--color-info)"
        : "var(--color-amber)";

  return (
    <li
      style={{ borderColor: "var(--color-rule-soft)" }}
      className="first:border-t"
    >
      <Link
        to={`/app/case/${c.id}`}
        className="grid grid-cols-[auto_1fr_auto] items-baseline gap-4 px-1 py-3 hover:bg-[var(--color-surface)] transition-colors"
      >
        <span
          className="font-mono text-[11.5px]"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {c.short_id}
        </span>
        <div className="min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <Badge tone="neutral" dot style={{ color: statusColor }}>
              {c.status.replace(/_/g, " ")}
            </Badge>
            {c.decision_action && (
              <span
                className="text-[12.5px] tabular-nums"
                style={{ color: "var(--color-ink-strong)" }}
              >
                {c.decision_action}
                {" · "}
                {formatAmount(
                  c.decision_amount_minor ?? c.amount_minor,
                  c.currency,
                )}
              </span>
            )}
            <span
              className="text-[11px]"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              {humanizeTrigger(c.trigger_surface)}
            </span>
          </div>
        </div>
        <span
          className="text-[11.5px] tabular-nums whitespace-nowrap"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {formatAge(c.created_at)} ago
        </span>
      </Link>
    </li>
  );
}
