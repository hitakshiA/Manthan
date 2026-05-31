/**
 * Audit log - every approval, policy match, action.
 *
 * Editorial direction: a day-grouped transcript that reads like a
 * print-period diary. Each day gets its own Spectral italic header
 * with a counter and a tabular wall-clock for the first event of the
 * day; within a day, rows are denser but still typeset (mono time +
 * uppercase TYPE label + body sentence + right-edge case ref).
 *
 * The previous version was a single flat `divide-y` list of 200 rows
 * that read as terminal output - visually dense in the worst way,
 * with no temporal anchors. The day groupings restore the rhythm a
 * compliance auditor would actually want.
 */

import { useEffect, useMemo, useState } from "react";

import {
  EmptyRow,
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import {
  listAuditRecent,
  formatAmount,
  type ApiAuditEvent,
} from "@/lib/api";
import { cn } from "@/lib/cn";

const TYPE_META: Record<string, { label: string; color: string }> = {
  case_opened:     { label: "Case opened",     color: "var(--color-info)" },
  brief_drafted:   { label: "Brief drafted",   color: "var(--color-ink-strong)" },
  policy_matched:  { label: "Policy matched",  color: "var(--color-amber)" },
  human_approved:  { label: "Approved",        color: "var(--color-accent)" },
  human_hold:      { label: "Held",            color: "var(--color-amber)" },
  human_denied:    { label: "Denied",          color: "var(--color-danger)" },
  human_escalated: { label: "Escalated",       color: "var(--color-danger)" },
  action_executed: { label: "Action fired",    color: "var(--color-accent)" },
  action_failed:   { label: "Action failed",   color: "var(--color-danger)" },
  agent_reply:     { label: "Agent replied",   color: "var(--color-info)" },
  case_closed:     { label: "Case closed",     color: "var(--color-ink-faint)" },
};

export default function AuditPage() {
  const [events, setEvents] = useState<ApiAuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    listAuditRecent(200)
      .then(setEvents)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Filter chain: apply the active type filter, then group by day.
  const filtered = useMemo(() => {
    if (!events) return null;
    return filter ? events.filter((e) => e.type === filter) : events;
  }, [events, filter]);

  const grouped = useMemo(() => {
    if (!filtered) return null;
    const map = new Map<string, ApiAuditEvent[]>();
    for (const e of filtered) {
      const key = startOfDayKey(e.created_at);
      const list = map.get(key);
      if (list) list.push(e);
      else map.set(key, [e]);
    }
    return Array.from(map.entries()); // already sorted because input is sorted desc
  }, [filtered]);

  const presentTypes = useMemo(
    () => (events ? Array.from(new Set(events.map((e) => e.type))) : []),
    [events],
  );

  return (
    <PageBody width="wide">
      <PageHeader
        eyebrow="Audit"
        title="Everything that happened"
        meta="Approvals, policy matches, actions. Immutable. Click a row to open the case."
      />

      {error && <ErrorRow>{error}</ErrorRow>}

      {events && events.length > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
          <FilterToken
            label="All"
            active={!filter}
            onClick={() => setFilter(null)}
          />
          {presentTypes.map((t) => {
            const meta = TYPE_META[t];
            return (
              <FilterToken
                key={t}
                label={meta?.label ?? t}
                active={filter === t}
                onClick={() => setFilter(t === filter ? null : t)}
                color={meta?.color}
              />
            );
          })}
        </div>
      )}

      {filtered === null && !error && <LoadingRow />}
      {filtered !== null && filtered.length === 0 && !error && (
        <EmptyRow>No events match this filter.</EmptyRow>
      )}

      {grouped && grouped.length > 0 && (
        <Section>
          <div className="flex flex-col gap-9">
            {grouped.map(([day, dayEvents]) => (
              <DayBlock key={day} day={day} events={dayEvents} />
            ))}
          </div>
        </Section>
      )}
    </PageBody>
  );
}

// ──────────────────────────────────────────────────────────────────────
// A day's worth of events - date header above, rows below with mono
// time-of-day prefix instead of a relative "Xh ago" suffix.
// ──────────────────────────────────────────────────────────────────────

function DayBlock({
  day,
  events,
}: {
  day: string;
  events: ApiAuditEvent[];
}) {
  const dateLabel = humanizeDay(day);
  return (
    <div>
      {/* Date header - Spectral italic + small count, like a diary entry */}
      <div
        className="flex items-baseline justify-between pb-2.5 mb-1 border-b"
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <h2
          className="font-display italic text-[22px] leading-[1.1] tracking-[-0.005em]"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {dateLabel}
        </h2>
        <span
          className="text-[10px] uppercase tracking-[0.14em] tabular-nums"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {events.length} {events.length === 1 ? "event" : "events"}
        </span>
      </div>

      <ol className="flex flex-col">
        {events.map((e, i) => (
          <AuditRow event={e} key={e.id} first={i === 0} />
        ))}
      </ol>
    </div>
  );
}

function AuditRow({ event, first }: { event: ApiAuditEvent; first?: boolean }) {
  const meta = TYPE_META[event.type] ?? {
    label: event.type,
    color: "var(--color-ink-muted)",
  };
  const detail = describeDetail(event);
  const time = formatTimeOfDay(event.created_at);

  return (
    <li
      className={cn("group", !first && "border-t")}
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <a
        href={`/app/case/${event.case_id}`}
        className="grid items-baseline gap-x-5 gap-y-1 py-3 px-1 hover:bg-[var(--color-surface)] transition-colors"
        style={{
          gridTemplateColumns:
            "72px 130px minmax(0, 1fr) minmax(0, auto)",
        }}
      >
        {/* Mono wall-clock - anchors the row temporally */}
        <span
          className="font-mono text-[11.5px] tabular-nums"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {time}
        </span>

        {/* TYPE label */}
        <span
          className="text-[10.5px] uppercase tracking-[0.13em]"
          style={{ color: meta.color }}
        >
          {meta.label}
        </span>

        {/* Body - actually readable size now (14.5px), one line */}
        <span
          className="text-[14px] leading-[1.4] truncate"
          style={{ color: "var(--color-ink)" }}
        >
          {event.summary || detail || "-"}
        </span>

        {/* Right - case ref + customer + amount, mono / tabular */}
        <span
          className="text-[11.5px] tabular-nums whitespace-nowrap text-right"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <span
            className="font-mono"
            style={{ color: "var(--color-ink)" }}
          >
            {event.case_short_id}
          </span>
          {event.customer_ref && (
            <>
              {" · "}
              <span style={{ color: "var(--color-ink-muted)" }}>
                {truncate(event.customer_ref, 26)}
              </span>
            </>
          )}
          {event.amount_minor != null && (
            <>
              {" · "}
              <span style={{ color: "var(--color-ink-strong)" }}>
                {formatAmount(event.amount_minor)}
              </span>
            </>
          )}
        </span>
      </a>
    </li>
  );
}

function describeDetail(e: ApiAuditEvent): string {
  const d = e.data;
  if (e.type === "policy_matched") {
    const name = (d.rule_name as string) || "rule";
    const mode = (d.mode as string) || "";
    return `${name}${mode ? ` (${mode})` : ""}`;
  }
  if (e.type === "human_approved") {
    const via = (d.via as string) || "ui";
    if (via === "policy_auto") return `auto via ${d.rule_name || "policy"}`;
    if (via === "slack") return `by ${d.slack_user_name || "operator"} via Slack`;
    return `by ${d.member_email || "operator"}`;
  }
  if (e.type === "action_executed") {
    return `${(d.kind as string) || "action"} → ${(d.summary as string) || "ok"}`;
  }
  if (e.type === "action_failed") {
    return `${(d.kind as string) || "action"} - ${(d.error as string) || "unknown"}`;
  }
  if (e.type === "agent_reply") {
    return String(d.text || "").slice(0, 140);
  }
  if (e.type === "case_opened") {
    return (
      String(d.trigger_surface || "") +
      (d.trigger_text ? ` · ${String(d.trigger_text).slice(0, 120)}` : "")
    );
  }
  return "";
}

function FilterToken({
  label,
  active,
  onClick,
  color,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className="text-[11px] uppercase tracking-[0.13em] transition-colors"
      style={{
        color: active
          ? "var(--color-ink-strong)"
          : color ?? "var(--color-ink-faint)",
        fontWeight: active ? 600 : 500,
        textDecoration: active ? "underline" : "none",
        textUnderlineOffset: 4,
        textDecorationColor: "var(--color-ink-faint)",
      }}
    >
      {label}
    </button>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Time helpers - wall-clock + relative-day display.
// ──────────────────────────────────────────────────────────────────────

function startOfDayKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function humanizeDay(dayKey: string): string {
  const [y, m, dd] = dayKey.split("-").map(Number);
  const day = new Date(y, m - 1, dd);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (day.getTime() === today.getTime()) return "Today";
  if (day.getTime() === yesterday.getTime()) return "Yesterday";
  // Within the same year - drop the year.
  const sameYear = day.getFullYear() === now.getFullYear();
  return day.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    weekday: "long",
    year: sameYear ? undefined : "numeric",
  });
}

function formatTimeOfDay(iso: string): string {
  const d = new Date(iso);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + "…";
}
