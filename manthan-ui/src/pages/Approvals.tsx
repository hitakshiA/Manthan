/**
 * Approvals - cross-case queue. Editorial ledger form, not a card grid.
 *
 * Each row is a single hairline-separated line: customer, decision +
 * amount as inline text, drafted-action count as a tabular numeral,
 * approve/hold to the right. Compresses what used to take ~140px per
 * card into ~52px per row, so a queue of 12 reads at a glance.
 */

import { Link } from "react-router-dom";
import {
  CheckCircle2,
  Loader2,
  ThumbsDown,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  EmptyRow,
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import {
  actionTitle,
  approveCase,
  formatAge,
  formatAmount,
  holdCase,
  humanizeTrigger,
  listCases,
  listCaseActions,
  type ApiActionRow,
  type ApiCase,
} from "@/lib/api";

interface PendingCase {
  caseId: string;
  shortId: string;
  customer: string;
  triggerSurface: ApiCase["trigger_surface"];
  decision: string;
  amountLabel: string;
  age: string;
  drafted: ApiActionRow[];
}

export default function Approvals() {
  const [rows, setRows] = useState<PendingCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setError(null);
    try {
      const { cases } = await listCases({ status: "awaiting_approval", limit: 100 });
      const actionsByCase = await Promise.all(
        cases.map((c) => listCaseActions(c.id).catch(() => [] as ApiActionRow[])),
      );
      const built: PendingCase[] = cases.map((c, i) => ({
        caseId: c.id,
        shortId: c.short_id,
        customer: c.customer_ref ?? "-",
        triggerSurface: c.trigger_surface,
        decision: c.decision_action ?? "-",
        amountLabel: formatAmount(
          c.decision_amount_minor ?? c.amount_minor,
          c.currency ?? "usd",
        ),
        age: formatAge(c.created_at),
        drafted: actionsByCase[i].filter((a) => a.status === "drafted"),
      }));
      setRows(built);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const totalDrafted = useMemo(
    () => rows?.reduce((acc, r) => acc + r.drafted.length, 0) ?? 0,
    [rows],
  );

  const mark = (id: string, on: boolean) =>
    setActing((s) => {
      const next = new Set(s);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const runApprove = async (caseId: string) => {
    mark(caseId, true);
    try {
      await approveCase(caseId);
      await load();
    } finally {
      mark(caseId, false);
    }
  };
  const runHold = async (caseId: string) => {
    mark(caseId, true);
    try {
      await holdCase(caseId);
      await load();
    } finally {
      mark(caseId, false);
    }
  };
  const runApproveAll = async () => {
    if (!rows?.length) return;
    if (!confirm(`Approve ${rows.length} cases (${totalDrafted} actions)?`)) return;
    await Promise.allSettled(rows.map((r) => approveCase(r.caseId)));
    await load();
  };

  const metaLine = rows
    ? rows.length === 0
      ? "Nothing waiting for your nod."
      : `${rows.length} case${rows.length === 1 ? "" : "s"} · ${totalDrafted} action${totalDrafted === 1 ? "" : "s"} drafted. Manthan is paused on each until you decide.`
    : null;

  return (
    <PageBody>
      <PageHeader
        eyebrow="Approvals"
        title="Pending approvals"
        meta={metaLine}
        actions={
          rows && rows.length > 0 ? (
            <Button
              variant="accent"
              size="sm"
              leftIcon={<CheckCircle2 className="h-3.5 w-3.5" />}
              onClick={runApproveAll}
            >
              Approve all
            </Button>
          ) : null
        }
      />

      {error && <ErrorRow>Couldn&apos;t load the queue: {error}</ErrorRow>}
      {rows === null && !error && <LoadingRow />}
      {rows !== null && rows.length === 0 && !error && (
        <EmptyRow>
          Inbox zero. Manthan is either still investigating or running on
          auto-approve via policy.
        </EmptyRow>
      )}

      {rows && rows.length > 0 && (
        <Section>
          <ul className="divide-y" style={{ borderColor: "var(--color-rule-soft)" }}>
            {rows.map((r) => (
              <ApprovalLine
                key={r.caseId}
                row={r}
                busy={acting.has(r.caseId)}
                onApprove={() => runApprove(r.caseId)}
                onHold={() => runHold(r.caseId)}
              />
            ))}
          </ul>
        </Section>
      )}
    </PageBody>
  );
}

function ApprovalLine({
  row,
  busy,
  onApprove,
  onHold,
}: {
  row: PendingCase;
  busy: boolean;
  onApprove: () => void;
  onHold: () => void;
}) {
  return (
    <li
      style={{ borderColor: "var(--color-rule-soft)" }}
      className="first:border-t"
    >
      <div className="grid grid-cols-[1fr_auto] items-center gap-6 py-4">
        <div className="min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <Link
              to={`/app/case/${row.caseId}`}
              className="text-[14.5px] hover:underline truncate"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {row.customer}
            </Link>
            <span
              className="font-mono text-[10.5px]"
              style={{ color: "var(--color-ink-ghost)" }}
            >
              {row.shortId}
            </span>
          </div>

          <div
            className="mt-1 text-[12.5px] tabular-nums"
            style={{ color: "var(--color-ink-muted)" }}
          >
            <span style={{ color: "var(--color-ink)" }}>
              {row.decision}
            </span>
            {" · "}
            {row.amountLabel}
            {" · "}
            <span style={{ color: "var(--color-ink-faint)" }}>
              {humanizeTrigger(row.triggerSurface)}, {row.age} ago
            </span>
          </div>

          {row.drafted.length > 0 && (
            <ul
              className="mt-2 text-[12px] tabular-nums space-y-0.5"
              style={{ color: "var(--color-ink-muted)" }}
            >
              {row.drafted.slice(0, 3).map((a) => (
                <li key={a.id} className="truncate">
                  <span
                    className="font-mono text-[10px] mr-1.5"
                    style={{ color: "var(--color-ink-ghost)" }}
                  >
                    {String(a.seq).padStart(2, "0")}
                  </span>
                  {actionTitle(a)}
                </li>
              ))}
              {row.drafted.length > 3 && (
                <li
                  className="text-[11px] italic font-display"
                  style={{ color: "var(--color-ink-ghost)" }}
                >
                  + {row.drafted.length - 3} more
                </li>
              )}
            </ul>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="accent"
            size="sm"
            leftIcon={
              busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )
            }
            onClick={onApprove}
            disabled={busy || row.drafted.length === 0}
          >
            Approve
          </Button>
          <button
            onClick={onHold}
            disabled={busy}
            className="h-8 px-2 text-[12px] tracking-[0.02em] hover:opacity-90 disabled:opacity-40"
            style={{ color: "var(--color-ink-faint)" }}
          >
            <ThumbsDown className="h-3 w-3 inline-block mr-1 -mt-px" />
            Hold
          </button>
        </div>
      </div>
    </li>
  );
}
