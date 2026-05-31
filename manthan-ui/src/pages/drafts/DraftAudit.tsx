/**
 * DraftAudit - Audit log, editorial direction (DRAFT).
 *
 * Scales the landing's tiny AuditVisual up to a full-page surface that
 * lives inside the existing AppShell. Vocabulary borrowed 1:1 from
 * WorkspaceMemo: HeaderStrip / Eyebrow / hairline rules / Spectral
 * italic accents / tabular mono for IDs and amounts.
 *
 *   ┌─────────────────────────────────────────────────────┐
 *   │ AUDIT · 12 actions today               ◴ live       │  HEADER
 *   │ ─────────────────────────────────────────────────── │
 *   │  Audit                                              │
 *   │  Everything that happened.                          │
 *   │  Immutable. Every action signed.                    │
 *   │                                                     │
 *   │  FILTERS    all 12 · you 4 · manthan 8              │
 *   │                                                     │
 *   │  ┌───── Today ─────────────────────────────────┐    │
 *   │  │ ● Manthan refunded $1,200 to TechCorp ·…    │    │
 *   │  │   via Stripe · ch_3Tch1L                    │    │
 *   │  │ ● You approved CASE W7R-APERTURE-PRORATA…   │    │
 *   │  │   via case workspace                        │    │
 *   │  └─────────────────────────────────────────────┘    │
 *   │  ┌───── Yesterday ─────────────────────────────┐    │
 *   │  │ ● Manthan posted daily summary to…          │    │
 *   │  └─────────────────────────────────────────────┘    │
 *   │ ─────────────────────────────────────────────────── │
 *   │ every action signed & exportable to your SIEM · live│  FOOTER
 *   └─────────────────────────────────────────────────────┘
 *
 * Throwaway draft - route /app/draft-audit.
 */

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { SourceIcon } from "@/components/ui/SourceIcon";

// ──────────────────────────────────────────────────────────────────────
// Mock data - twelve events grouped into two days.
// Mix of "you" and "manthan" actors. Real-sounding verbs + objects.
// ──────────────────────────────────────────────────────────────────────

type Actor = "you" | "manthan";

interface AuditEvent {
  id: string;
  who: Actor;
  /** Lowercase verb phrase, e.g. "refunded", "posted brief to". */
  verb: string;
  /** The "object" - case id / customer / channel / amount. */
  object: string;
  /** Source the action was routed through (matches SourceIcon ids). */
  src: string;
  /** Human-readable "via" suffix shown after the source name. */
  refLabel: string;
  /** "6 min ago" / "11:42 UTC" - already formatted. */
  ago: string;
}

interface AuditDay {
  /** "Today", "Yesterday", or full date heading. */
  heading: string;
  /** Compact UTC range to print beside the heading. */
  range: string;
  events: AuditEvent[];
}

const DAYS: AuditDay[] = [
  {
    heading: "Today",
    range: "2026-05-30 · UTC",
    events: [
      {
        id: "evt_01",
        who: "manthan",
        verb: "refunded",
        object: "$560 to Aperture Analytics",
        src: "stripe",
        refLabel: "ch_3Tch1L",
        ago: "6 min ago",
      },
      {
        id: "evt_02",
        who: "you",
        verb: "approved",
        object: "CASE W7R-APERTURE-PRORATA-REAL",
        src: "case-workspace",
        refLabel: "case workspace",
        ago: "7 min ago",
      },
      {
        id: "evt_03",
        who: "manthan",
        verb: "posted brief to",
        object: "#ar-ops",
        src: "slack",
        refLabel: "ts=1716492073.42",
        ago: "8 min ago",
      },
      {
        id: "evt_04",
        who: "manthan",
        verb: "emailed billing contact at",
        object: "billing@aperture-analytics.co",
        src: "resend",
        refLabel: "msg_3F8K2pAx",
        ago: "9 min ago",
      },
      {
        id: "evt_05",
        who: "manthan",
        verb: "filed concede response on",
        object: "dispute du_1Tch1O",
        src: "stripe",
        refLabel: "du_1Tch1O · concede=true",
        ago: "11 min ago",
      },
      {
        id: "evt_06",
        who: "manthan",
        verb: "matched policy",
        object: "documented-incident-prorata-credit",
        src: "notion",
        refLabel: "policy engine · page/37043656",
        ago: "14 min ago",
      },
      {
        id: "evt_07",
        who: "manthan",
        verb: "opened case",
        object: "W7R-APERTURE-PRORATA-REAL",
        src: "stripe",
        refLabel: "stripe webhook · evt_charge.dispute.created",
        ago: "21 min ago",
      },
      {
        id: "evt_08",
        who: "you",
        verb: "tightened the refund policy to",
        object: "max $1,500 / case",
        src: "policy-editor",
        refLabel: "policy editor · refunds.max_amount",
        ago: "1h 12m ago",
      },
    ],
  },
  {
    heading: "Yesterday",
    range: "2026-05-29 · UTC",
    events: [
      {
        id: "evt_09",
        who: "manthan",
        verb: "appended resolution note to",
        object: "Aperture Analytics",
        src: "hubspot",
        refLabel: "company/324974146247",
        ago: "yesterday · 18:04",
      },
      {
        id: "evt_10",
        who: "manthan",
        verb: "posted daily summary to",
        object: "#billing-ops",
        src: "slack",
        refLabel: "ts=1716405481.18",
        ago: "yesterday · 17:58",
      },
      {
        id: "evt_11",
        who: "you",
        verb: "held",
        object: "CASE CSE-104287",
        src: "case-workspace",
        refLabel: "case workspace · hold·48h",
        ago: "yesterday · 14:21",
      },
      {
        id: "evt_12",
        who: "manthan",
        verb: "opened case",
        object: "CSE-104291",
        src: "zendesk",
        refLabel: "zendesk webhook · ticket=104291",
        ago: "yesterday · 09:07",
      },
    ],
  },
];

const TOTAL_TODAY = DAYS[0].events.length;
const TOTAL_ALL = DAYS.reduce((n, d) => n + d.events.length, 0);

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

type Filter = "all" | "you" | "manthan";

export default function DraftAudit() {
  const [filter, setFilter] = useState<Filter>("all");

  // Counts are stable - derived once from the static mock.
  const counts = useMemo(() => {
    const all = TOTAL_ALL;
    let you = 0;
    let manthan = 0;
    for (const day of DAYS) {
      for (const e of day.events) {
        if (e.who === "you") you += 1;
        else manthan += 1;
      }
    }
    return { all, you, manthan };
  }, []);

  // Apply filter per-day so we can drop empty days entirely.
  const filteredDays = useMemo(() => {
    return DAYS.map((day) => ({
      ...day,
      events:
        filter === "all"
          ? day.events
          : day.events.filter((e) => e.who === filter),
    })).filter((day) => day.events.length > 0);
  }, [filter]);

  return (
    <div
      className="h-full w-full flex items-stretch px-6 py-6"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex flex-col flex-1 min-h-0"
        style={{
          background: "oklch(0.135 0.006 75)",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 6,
          color: "rgba(255,255,255,0.92)",
          overflow: "hidden",
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        }}
      >
        <HeaderStrip todayCount={TOTAL_TODAY} />

        <div className="relative flex-1 min-h-0 overflow-y-auto">
          <AuditCanvas
            filter={filter}
            setFilter={setFilter}
            counts={counts}
            days={filteredDays}
          />
        </div>

        <StatusStrip />
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// HeaderStrip - surface identity. Always present.
// ──────────────────────────────────────────────────────────────────────

function HeaderStrip({ todayCount }: { todayCount: number }) {
  return (
    <header
      className="flex items-center px-9 shrink-0"
      style={{
        height: 56,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "oklch(0.135 0.006 75)",
      }}
    >
      <span
        className="font-mono text-[13px] uppercase tabular-nums"
        style={{
          color: "rgba(255,255,255,0.60)",
          letterSpacing: "0.16em",
        }}
      >
        AUDIT
      </span>

      <span
        className="mx-3"
        style={{ color: "rgba(255,255,255,0.22)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[15px]"
        style={{
          color: "rgba(255,255,255,0.82)",
          letterSpacing: "0.005em",
        }}
      >
        <span className="font-mono tabular-nums">{todayCount}</span> actions
        today
      </span>

      <span
        className="mx-4"
        style={{ color: "rgba(255,255,255,0.18)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="font-mono text-[12px] tabular-nums inline-flex items-baseline gap-2"
        style={{
          color: "rgba(255,255,255,0.50)",
          letterSpacing: "0.04em",
        }}
        title="retention window"
      >
        <span
          className="uppercase"
          style={{ letterSpacing: "0.18em", color: "rgba(255,255,255,0.36)" }}
        >
          retain
        </span>
        <span style={{ color: "rgba(255,255,255,0.62)" }}>
          90d · immutable
        </span>
      </span>

      <span className="ml-auto inline-flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
          style={{ background: "var(--color-accent, #56cf83)" }}
        />
        <span
          className="text-[12.5px] uppercase"
          style={{
            color: "rgba(86, 207, 131, 0.92)",
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          live
        </span>
      </span>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Canvas - title block, filter row, day-grouped feed.
// ──────────────────────────────────────────────────────────────────────

function AuditCanvas({
  filter,
  setFilter,
  counts,
  days,
}: {
  filter: Filter;
  setFilter: (f: Filter) => void;
  counts: { all: number; you: number; manthan: number };
  days: AuditDay[];
}) {
  return (
    <div className="px-14 pt-12 pb-10 flex flex-col gap-9 max-w-[1100px] mx-auto w-full">
      {/* Title block */}
      <div className="flex flex-col gap-5">
        <Eyebrow>Audit</Eyebrow>
        <h2
          className="leading-[1.08]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(30px, 3.0vw, 38px)",
            color: "rgba(255,255,255,0.96)",
            letterSpacing: "-0.014em",
          }}
        >
          Everything that happened.
        </h2>
        <p
          className="leading-[1.5]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 15,
            fontStyle: "italic",
            color: "rgba(255,255,255,0.58)",
            maxWidth: "56ch",
          }}
        >
          Immutable. Every action signed. Exportable to your SIEM.
        </p>
      </div>

      {/* Filter row - eyebrow on the left, pills on the right */}
      <div
        className="flex items-center pb-5"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Filters</Eyebrow>
        <div className="ml-auto flex items-center gap-1">
          {(["all", "you", "manthan"] as const).map((f) => (
            <FilterPill
              key={f}
              label={f}
              active={filter === f}
              count={counts[f]}
              onClick={() => setFilter(f)}
            />
          ))}
        </div>
      </div>

      {/* Activity feed - one container, day-grouped */}
      <div
        className="relative"
        style={{
          background: "oklch(0.142 0.006 75)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 6,
          minHeight: 600,
        }}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={filter}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.25, 1, 0.5, 1] }}
            className="flex flex-col"
          >
            {days.length === 0 ? (
              <EmptyDay filter={filter} />
            ) : (
              days.map((day, dayIdx) => (
                <DaySection
                  key={day.heading}
                  day={day}
                  isFirst={dayIdx === 0}
                />
              ))
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Day section - Spectral italic date heading + events list.
// ──────────────────────────────────────────────────────────────────────

function DaySection({ day, isFirst }: { day: AuditDay; isFirst: boolean }) {
  return (
    <section
      className="px-9 py-7"
      style={
        isFirst
          ? undefined
          : { borderTop: "1px solid rgba(255,255,255,0.06)" }
      }
    >
      {/* Day heading */}
      <div className="flex items-baseline gap-4 mb-6">
        <h3
          style={{
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            fontSize: 22,
            color: "rgba(255,255,255,0.86)",
            letterSpacing: "-0.006em",
            lineHeight: 1,
          }}
        >
          {day.heading}
        </h3>
        <span
          className="font-mono text-[11.5px] tabular-nums"
          style={{
            color: "rgba(255,255,255,0.36)",
            letterSpacing: "0.10em",
          }}
        >
          {day.range}
        </span>
        <span
          className="ml-auto text-[11.5px] uppercase"
          style={{
            color: "rgba(255,255,255,0.36)",
            letterSpacing: "0.18em",
            fontWeight: 500,
          }}
        >
          {day.events.length}{" "}
          {day.events.length === 1 ? "action" : "actions"}
        </span>
      </div>

      <ol className="flex flex-col gap-5">
        {day.events.map((e, i) => (
          <EventRow key={e.id} event={e} isNewest={i === 0} />
        ))}
      </ol>
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────
// EventRow - avatar dot + text line + via line.
// ──────────────────────────────────────────────────────────────────────

function EventRow({
  event,
  isNewest,
}: {
  event: AuditEvent;
  isNewest: boolean;
}) {
  const isYou = event.who === "you";
  const actorColor = isYou ? "#e8a23a" : "var(--color-accent, #56cf83)";
  const actorRing = isYou
    ? "rgba(232, 162, 58, 0.22)"
    : "rgba(86, 207, 131, 0.22)";

  // Mono-style object text whenever it looks like an ID, amount, or
  // case-ref. Pure heuristic - keeps the typography honest.
  const objectIsCode =
    /^\$/.test(event.object) ||
    /^(CASE\s|CSE-|W7R-|BIL-|du_|ch_|evt_|#)/.test(event.object) ||
    /@/.test(event.object);

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.25, 1, 0.5, 1] }}
      className="grid"
      style={{
        gridTemplateColumns: "26px minmax(0,1fr)",
        gap: 16,
      }}
    >
      {/* Avatar dot - colored by actor, ringed if newest */}
      <span
        className="shrink-0 inline-flex items-center justify-center rounded-full"
        aria-hidden
        style={{
          height: 10,
          width: 10,
          marginTop: 8,
          background: actorColor,
          boxShadow: isNewest ? `0 0 0 3px ${actorRing}` : "none",
        }}
      />

      <div className="min-w-0 flex-1">
        {/* Main text line */}
        <div
          className="text-[16px] leading-[1.45]"
          style={{ color: "rgba(255,255,255,0.86)" }}
        >
          <span
            style={{ color: "rgba(255,255,255,0.96)", fontWeight: 500 }}
          >
            {isYou ? "You" : "Manthan"}
          </span>{" "}
          <span style={{ color: "rgba(255,255,255,0.65)" }}>{event.verb}</span>{" "}
          <span
            className={
              objectIsCode ? "font-mono tabular-nums text-[15px]" : ""
            }
            style={{
              color: "rgba(255,255,255,0.96)",
              fontWeight: 500,
              letterSpacing: objectIsCode ? "0.005em" : undefined,
            }}
          >
            {event.object}
          </span>
          <span
            className="mx-1.5"
            style={{ color: "rgba(255,255,255,0.28)" }}
            aria-hidden
          >
            ·
          </span>
          <span style={{ color: "rgba(255,255,255,0.50)" }}>{event.ago}</span>
        </div>

        {/* "via" line - small mono, with the source icon */}
        <div
          className="mt-2.5 inline-flex items-center gap-2 font-mono text-[12.5px] tabular-nums"
          style={{
            color: "rgba(255,255,255,0.45)",
            letterSpacing: "0.02em",
          }}
        >
          <span
            aria-hidden
            style={{
              display: "inline-flex",
              transform: "translateY(-0.5px)",
              opacity: 0.85,
            }}
          >
            <SourceIcon id={event.src} size={11} tinted />
          </span>
          <span style={{ color: "rgba(255,255,255,0.62)" }}>via</span>
          <span style={{ color: "rgba(255,255,255,0.74)" }}>
            {sourceLabel(event.src)}
          </span>
          <span
            className="mx-1"
            style={{ color: "rgba(255,255,255,0.22)" }}
            aria-hidden
          >
            ·
          </span>
          <span style={{ color: "rgba(255,255,255,0.50)" }}>
            {event.refLabel}
          </span>
        </div>
      </div>
    </motion.li>
  );
}

// ──────────────────────────────────────────────────────────────────────
// FilterPill - quiet, hairline-only outline. Soft green tint when active.
// ──────────────────────────────────────────────────────────────────────

function FilterPill({
  label,
  active,
  count,
  onClick,
}: {
  label: Filter;
  active: boolean;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-baseline gap-2 px-3 py-1.5 outline-none transition-colors"
      style={{
        background: active
          ? "var(--color-accent-soft, rgba(86,207,131,0.10))"
          : "transparent",
        border: active
          ? "1px solid rgba(86,207,131,0.32)"
          : "1px solid rgba(255,255,255,0.10)",
        borderRadius: 4,
        color: active
          ? "var(--color-accent, #56cf83)"
          : "rgba(255,255,255,0.58)",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 500,
        letterSpacing: "0.10em",
        textTransform: "uppercase",
      }}
    >
      <span>{label}</span>
      <span
        className="font-mono tabular-nums"
        style={{
          color: active
            ? "var(--color-accent, #56cf83)"
            : "rgba(255,255,255,0.40)",
          fontSize: 12,
          letterSpacing: "0.04em",
        }}
      >
        {count}
      </span>
    </button>
  );
}

// ──────────────────────────────────────────────────────────────────────
// EmptyDay - when a filter zeroes everything out.
// ──────────────────────────────────────────────────────────────────────

function EmptyDay({ filter }: { filter: Filter }) {
  return (
    <div className="px-9 py-14 flex flex-col items-start gap-3">
      <span
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 20,
          color: "rgba(255,255,255,0.62)",
        }}
      >
        No {filter === "you" ? "operator" : "agent"} actions in this window.
      </span>
      <span
        className="text-[13.5px]"
        style={{ color: "rgba(255,255,255,0.45)", maxWidth: "44ch" }}
      >
        Try switching back to{" "}
        <span style={{ color: "rgba(255,255,255,0.78)", fontWeight: 500 }}>
          all
        </span>{" "}
        to see the combined feed, or widen the date range.
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// StatusStrip - wall-clock counterpart to the memo's footer.
// ──────────────────────────────────────────────────────────────────────

function StatusStrip() {
  return (
    <footer
      className="flex items-center px-9 shrink-0"
      style={{
        height: 48,
        borderTop: "1px solid rgba(255,255,255,0.06)",
        background: "oklch(0.135 0.006 75)",
      }}
    >
      <span
        className="text-[12px]"
        style={{
          color: "rgba(255,255,255,0.46)",
          letterSpacing: "0.02em",
        }}
      >
        every action signed & exportable to your SIEM
      </span>
      <span className="ml-auto inline-flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full animate-pulse-dot"
          style={{ background: "var(--color-accent, #56cf83)" }}
        />
        <span
          className="font-mono text-[12px] uppercase tabular-nums"
          style={{
            color: "rgba(255,255,255,0.62)",
            letterSpacing: "0.18em",
          }}
        >
          live
        </span>
      </span>
    </footer>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow - mirrors WorkspaceMemo's primitive 1:1.
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
      className="text-[12.5px] uppercase"
      style={{
        color: accent
          ? "var(--color-accent, #56cf83)"
          : "rgba(255,255,255,0.50)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Pretty source labels - keeps brand casing where we have a logo;
// falls back to a hand-written label for our internal surfaces.
// ──────────────────────────────────────────────────────────────────────

function sourceLabel(src: string): string {
  switch (src) {
    case "stripe":
      return "Stripe";
    case "slack":
      return "Slack";
    case "resend":
      return "Resend";
    case "notion":
      return "Notion";
    case "hubspot":
      return "HubSpot";
    case "zendesk":
      return "Zendesk";
    case "case-workspace":
      return "case workspace";
    case "policy-editor":
      return "policy editor";
    default:
      return src;
  }
}
