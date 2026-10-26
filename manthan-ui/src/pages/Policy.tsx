/**
 * Policy Center - the rulebook that decides which cases auto-execute
 * vs. wait for human approval.
 *
 * Editorial-memo direction: each rule renders as a mini-memo with a
 * HeaderStrip + two-column WHEN / DECISION canvas (mirrors the
 * WorkspaceMemo + DraftPolicies prototype). Page header is a Spectral
 * italic title with an eyebrow and an inline action button. Recent
 * matches reads as a slim ledger strip at the bottom.
 *
 * Wired to /api/policy/rules + /api/policy/matches + /api/policy/rules/:id
 * (toggle). Conditions arrive as the engine's clause-tree JSON; we
 * `flattenClauses` it and feed each clause through `humanizeClause`
 * so the operator reads prose ("Amount is at most $200"), not
 * `{"case.amount_minor":{"lte":20000}}`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";

import {
  listPolicyRules,
  listPolicyMatches,
  togglePolicyRule,
  type ApiPolicyRule,
  type ApiPolicyMatch,
} from "@/lib/api";
import { CreatePolicyRuleModal } from "@/components/app/CreatePolicyRuleModal";

// ──────────────────────────────────────────────────────────────────────
// Mode tokens - same palette as the WorkspaceMemo phase indicator.
// ──────────────────────────────────────────────────────────────────────

type Mode = "auto" | "recommend" | "suggest" | "hitl" | "escalate";

interface ModeToken {
  label: string;
  color: string;
  soft: string;
}

const MODE: Record<Mode, ModeToken> = {
  auto: {
    label: "auto",
    color: "var(--color-accent)",
    soft: "var(--color-accent-soft)",
  },
  recommend: {
    label: "recommend",
    color: "var(--color-amber)",
    soft: "var(--color-amber-soft)",
  },
  suggest: {
    label: "recommend",
    color: "var(--color-amber)",
    soft: "var(--color-amber-soft)",
  },
  hitl: {
    label: "hitl",
    color: "var(--color-info)",
    soft: "rgba(120, 178, 255, 0.10)",
  },
  escalate: {
    label: "escalate",
    color: "var(--color-danger)",
    soft: "rgba(255, 107, 107, 0.10)",
  },
};

function modeOf(rule: ApiPolicyRule): Mode {
  const m = String((rule.decision as { mode?: string }).mode ?? "recommend");
  if (m in MODE) return m as Mode;
  return "recommend";
}

// ──────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────

export default function PolicyPage() {
  const [rules, setRules] = useState<ApiPolicyRule[] | null>(null);
  const [matches, setMatches] = useState<ApiPolicyMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    Promise.all([listPolicyRules(), listPolicyMatches(20)])
      .then(([r, m]) => {
        setRules(r);
        setMatches(m);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(rule: ApiPolicyRule) {
    const updated = await togglePolicyRule(rule.id, !rule.enabled);
    setRules((prev) =>
      prev
        ? prev.map((r) =>
            r.id === rule.id ? { ...r, enabled: updated.enabled } : r,
          )
        : prev,
    );
  }

  const enabledCount = rules?.filter((r) => r.enabled).length ?? 0;

  return (
    <div
      className="h-full w-full overflow-y-auto px-6 py-6"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex flex-col flex-1 min-h-0"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 6,
          color: "var(--color-ink-strong)",
          overflow: "hidden",
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        }}
      >
        <PageHeader
          ruleCount={rules?.length ?? 0}
          enabledCount={enabledCount}
          loading={rules === null}
          onNewRule={() => setCreateOpen(true)}
        />

        <CreatePolicyRuleModal
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={load}
        />

        {error && (
          <div
            className="mx-12 mb-6 px-4 py-3 text-[13.5px]"
            style={{
              background: "var(--color-danger-soft)",
              border: "1px solid rgba(255, 107, 107, 0.30)",
              borderRadius: 4,
              color: "var(--color-danger)",
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
            }}
          >
            {error}
          </div>
        )}

        <div className="px-5 sm:px-8 lg:px-12 pb-10 pt-2 flex flex-col gap-5">
          {rules === null ? (
            <LoadingNote>Loading rules…</LoadingNote>
          ) : rules.length === 0 ? (
            <EmptyNote>
              No rules yet. Create one to let Manthan act on its own.
            </EmptyNote>
          ) : (
            rules.map((rule) => (
              <RuleMemo key={rule.id} rule={rule} onToggle={() => toggle(rule)} />
            ))
          )}
        </div>

        <div
          className="px-5 sm:px-8 lg:px-12 pt-10 pb-12"
          style={{ borderTop: "1px solid var(--color-rule-soft)" }}
        >
          <Eyebrow>Recent matches</Eyebrow>
          <div className="mt-5">
            <RecentMatches matches={matches} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Page header - eyebrow + Spectral italic title + subtitle + CTA.
// ──────────────────────────────────────────────────────────────────────

function PageHeader({
  ruleCount,
  enabledCount,
  loading,
  onNewRule,
}: {
  ruleCount: number;
  enabledCount: number;
  loading: boolean;
  onNewRule: () => void;
}) {
  return (
    <header className="px-5 sm:px-8 lg:px-12 pt-8 sm:pt-10 lg:pt-12 pb-7 sm:pb-9">
      <Eyebrow>Policies</Eyebrow>
      <div className="mt-3 flex items-end justify-between gap-6 flex-wrap">
        <div className="min-w-0">
          <h1
            className="leading-[1.06]"
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(34px, 3.4vw, 42px)",
              color: "var(--color-ink-strong)",
              letterSpacing: "-0.014em",
              fontStyle: "italic",
            }}
          >
            The rulebook.
          </h1>
          <p
            className="mt-3 text-[15px] max-w-[58ch]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "var(--color-ink-muted)",
              letterSpacing: "-0.003em",
              lineHeight: 1.5,
            }}
          >
            {loading
              ? "Loading…"
              : ruleCount === 0
                ? "No rules yet - Manthan defaults to escalating every case."
                : `${enabledCount} of ${ruleCount} ${ruleCount === 1 ? "rule" : "rules"} active. Each match is recorded - open a case to see which rule fired.`}
          </p>
        </div>
        <button
          type="button"
          onClick={onNewRule}
          data-tour-target="new-rule-button"
          className="inline-flex items-center gap-1.5 transition-all hover:opacity-95 hover:translate-y-[-1px] outline-none"
          style={{
            background: "var(--color-ink-strong)",
            color: "#0a0a0a",
            borderRadius: 4,
            fontSize: 13,
            fontWeight: 500,
            letterSpacing: "-0.002em",
            padding: "8px 14px",
            boxShadow:
              "0 1px 0 rgba(255,255,255,0.6) inset, " +
              "0 4px 14px rgba(0,0,0,0.30), " +
              "0 0 0 1px var(--color-ink-muted)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <Plus size={13} strokeWidth={2.4} />
          New rule
        </button>
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RuleMemo - one rule as a HeaderStrip + two-column card.
// ──────────────────────────────────────────────────────────────────────

function RuleMemo({
  rule,
  onToggle,
}: {
  rule: ApiPolicyRule;
  onToggle: () => void;
}) {
  const [hover, setHover] = useState(false);
  const dim = !rule.enabled;

  return (
    <section
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="overflow-hidden"
      style={{
        background: hover && !dim ? "var(--color-surface)" : "transparent",
        border: "1px solid var(--color-rule-soft)",
        borderRadius: 6,
        opacity: dim ? 0.55 : 1,
        transition: "background 200ms ease, opacity 200ms ease",
      }}
    >
      <RuleHeaderStrip rule={rule} onToggle={onToggle} />
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <RuleWhenColumn rule={rule} />
        <RuleDecisionColumn rule={rule} />
      </div>
    </section>
  );
}

function RuleHeaderStrip({
  rule,
  onToggle,
}: {
  rule: ApiPolicyRule;
  onToggle: () => void;
}) {
  const mode = MODE[modeOf(rule)];
  return (
    <header
      className="flex items-center px-7 shrink-0 gap-3 flex-wrap"
      style={{
        minHeight: 52,
        paddingTop: 14,
        paddingBottom: 14,
        borderBottom: "1px solid var(--color-rule-soft)",
      }}
    >
      <span
        className="font-mono text-[12.5px] uppercase tabular-nums"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.18em",
        }}
      >
        RULE&nbsp;{rule.priority.toString().padStart(2, "0")}
      </span>

      <span
        className="mx-1"
        style={{ color: "var(--color-rule-strong)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[16px]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.006em",
        }}
      >
        {rule.name}
      </span>

      <span
        className="ml-2 text-[11.5px] uppercase"
        style={{
          color: mode.color,
          letterSpacing: "0.20em",
          fontWeight: 500,
        }}
        title={`mode · ${mode.label}`}
      >
        {mode.label}
      </span>

      <div className="ml-auto inline-flex items-center gap-4">
        <span
          className="text-[11.5px] uppercase"
          style={{
            color: rule.enabled
              ? "var(--color-accent)"
              : "var(--color-ink-faint)",
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          {rule.enabled ? "Enabled" : "Disabled"}
        </span>
        <Toggle enabled={rule.enabled} onChange={onToggle} />
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// LEFT column - "When". Description + numbered prose conditions.
// ──────────────────────────────────────────────────────────────────────

function RuleWhenColumn({ rule }: { rule: ApiPolicyRule }) {
  const clauses = useMemo(
    () => flattenClauses(rule.conditions),
    [rule.conditions],
  );

  return (
    <div className="px-8 py-7 flex flex-col gap-5">
      {rule.description && (
        <div>
          <Eyebrow>When</Eyebrow>
          <p
            className="mt-3 text-[14px] leading-[1.55] max-w-[58ch]"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "var(--color-ink-muted)",
              letterSpacing: "-0.003em",
            }}
          >
            {rule.description}
          </p>
        </div>
      )}

      <div>
        <Eyebrow>Conditions</Eyebrow>
        {clauses.length === 0 ? (
          <p
            className="mt-3 text-[13.5px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-faint)",
            }}
          >
            applies to every case
          </p>
        ) : (
          <ol className="mt-3 space-y-2">
            {clauses.map((clause, i) => (
              <li
                key={i}
                className="grid"
                style={{
                  gridTemplateColumns: "26px minmax(0,1fr)",
                  gap: 10,
                }}
              >
                <span
                  className="text-[13px] tabular-nums pt-[1px]"
                  style={{
                    color: "var(--color-ink-faint)",
                    fontFamily: "Spectral, serif",
                    fontStyle: "italic",
                    letterSpacing: "0.04em",
                  }}
                >
                  {String(i + 1).padStart(2, "0")}.
                </span>
                <span
                  className="text-[13.5px] leading-[1.55]"
                  style={{
                    fontFamily: "Spectral, serif",
                    fontStyle: "italic",
                    color: "var(--color-ink)",
                    letterSpacing: "-0.002em",
                  }}
                >
                  {humanizeClause(clause)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RIGHT column - "Decision" + Matched counter.
// ──────────────────────────────────────────────────────────────────────

function RuleDecisionColumn({ rule }: { rule: ApiPolicyRule }) {
  const mode = MODE[modeOf(rule)];
  const d = rule.decision as Record<string, unknown>;
  const action = typeof d.action === "string" ? d.action : null;
  const reason = typeof d.reason === "string" ? d.reason : null;
  const replyToCustomer = d.reply_to_customer === true || d.replyToCustomer === true;
  const submitEvidence = d.submit_evidence === true || d.submitEvidence === true;

  return (
    <div
      className="px-8 py-7 flex flex-col gap-5"
      style={{ borderLeft: "1px solid var(--color-rule-soft)" }}
    >
      <div>
        <Eyebrow>Decision</Eyebrow>
        <dl className="mt-3 flex flex-col gap-2.5">
          <KeyValue
            label="Mode"
            value={
              <span
                className="text-[13.5px]"
                style={{
                  color: mode.color,
                  fontFamily: "Geist, sans-serif",
                  letterSpacing: "-0.002em",
                }}
              >
                {mode.label}
              </span>
            }
          />
          {action && (
            <KeyValue label="Action" value={humanizeAction(action)} />
          )}
          {reason && (
            <KeyValue label="Reason" value={humanizeReason(reason)} />
          )}
          {"reply_to_customer" in d || "replyToCustomer" in d ? (
            <KeyValue
              label="Reply to customer"
              value={replyToCustomer ? "yes" : "no"}
              mute={!replyToCustomer}
            />
          ) : null}
          {"submit_evidence" in d || "submitEvidence" in d ? (
            <KeyValue
              label="Submit evidence"
              value={submitEvidence ? "yes" : "no"}
              mute={!submitEvidence}
            />
          ) : null}
        </dl>
      </div>

      <div
        className="pt-5 flex items-baseline gap-3"
        style={{ borderTop: "1px solid var(--color-rule-soft)" }}
      >
        <Eyebrow>Matched</Eyebrow>
        <MatchedCount count={rule.match_count_90d} />
      </div>
    </div>
  );
}

function KeyValue({
  label,
  value,
  mute,
}: {
  label: string;
  value: React.ReactNode;
  mute?: boolean;
}) {
  const valueIsNode = typeof value !== "string";
  return (
    <div
      className="grid items-baseline"
      style={{
        gridTemplateColumns: "minmax(0, 150px) minmax(0, 1fr)",
        columnGap: 14,
      }}
    >
      <dt
        className="text-[14px]"
        style={{
          color: "var(--color-ink)",
          fontWeight: 500,
          letterSpacing: "-0.003em",
        }}
      >
        {label}
      </dt>
      <dd
        className="text-[14px] min-w-0 truncate"
        style={{
          color: mute
            ? "var(--color-ink-faint)"
            : "var(--color-ink-muted)",
          letterSpacing: "-0.002em",
        }}
      >
        {valueIsNode ? value : <span>{value}</span>}
      </dd>
    </div>
  );
}

function MatchedCount({ count }: { count: number }) {
  return (
    <span
      className="font-mono text-[12.5px] tabular-nums"
      style={{
        color: count === 0 ? "var(--color-ink-faint)" : "var(--color-ink)",
        letterSpacing: "0.04em",
      }}
    >
      {count.toLocaleString()} {count === 1 ? "time" : "times"} · last 90 days
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Recent matches - slim ledger strip grouped by day.
// ──────────────────────────────────────────────────────────────────────

function RecentMatches({ matches }: { matches: ApiPolicyMatch[] | null }) {
  const grouped = useMemo(() => {
    if (!matches) return null;
    const map = new Map<string, ApiPolicyMatch[]>();
    for (const m of matches) {
      const key = startOfDayKey(m.matched_at);
      const list = map.get(key);
      if (list) list.push(m);
      else map.set(key, [m]);
    }
    return Array.from(map.entries());
  }, [matches]);

  if (matches === null) return <LoadingNote>Loading matches…</LoadingNote>;
  if (matches.length === 0)
    return (
      <EmptyNote>
        No matches yet. When Manthan applies a rule, it shows up here.
      </EmptyNote>
    );

  return (
    <div className="flex flex-col gap-6">
      {grouped!.map(([day, dayMatches]) => (
        <div key={day}>
          <div
            className="flex items-baseline justify-between pb-2 mb-1"
            style={{ borderBottom: "1px solid var(--color-rule-soft)" }}
          >
            <h3
              className="leading-[1.1]"
              style={{
                fontFamily: "Spectral, serif",
                fontStyle: "italic",
                fontSize: 22,
                color: "var(--color-ink-strong)",
                letterSpacing: "-0.008em",
              }}
            >
              {humanizeDay(day)}
            </h3>
            <span
              className="font-mono text-[11px] uppercase tabular-nums"
              style={{
                color: "var(--color-ink-faint)",
                letterSpacing: "0.14em",
              }}
            >
              {dayMatches.length} {dayMatches.length === 1 ? "match" : "matches"}
            </span>
          </div>
          <ol className="flex flex-col">
            {dayMatches.map((m, i) => (
              <MatchRow match={m} key={m.id} first={i === 0} />
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function MatchRow({ match, first }: { match: ApiPolicyMatch; first?: boolean }) {
  const mode = MODE[(match.mode as Mode) ?? "recommend"];
  return (
    <li
      style={{
        borderTop: first ? "none" : "1px solid var(--color-rule-soft)",
      }}
    >
      <a
        href={`/app/case/${match.case_id}`}
        className="grid items-baseline gap-x-5 gap-y-1 py-2.5 px-1 transition-colors hover:bg-[var(--color-surface-2)]"
        style={{
          gridTemplateColumns: "64px 130px minmax(0, 1fr) auto",
        }}
      >
        <span
          className="font-mono text-[11.5px] tabular-nums"
          style={{ color: "var(--color-ink-faint)", letterSpacing: "0.04em" }}
        >
          {formatTimeOfDay(match.matched_at)}
        </span>
        <span
          className="text-[10.5px] uppercase"
          style={{ color: mode.color, letterSpacing: "0.18em" }}
        >
          {mode.label}
        </span>
        <span
          className="text-[13.5px] leading-[1.4] truncate"
          style={{
            color: "var(--color-ink)",
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            letterSpacing: "-0.002em",
          }}
        >
          {match.rule_name}
          {match.decision_action && (
            <>
              <span style={{ color: "var(--color-ink-ghost)" }}>{" → "}</span>
              <span style={{ color: "var(--color-ink-strong)" }}>
                {humanizeAction(match.decision_action)}
              </span>
            </>
          )}
        </span>
        <span
          className="font-mono text-[11.5px] tabular-nums"
          style={{ color: "var(--color-ink)", letterSpacing: "0.04em" }}
        >
          {match.case_short_id}
        </span>
      </a>
    </li>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow + small primitives.
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
          : "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

function LoadingNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[14px] italic"
      style={{
        fontFamily: "Spectral, serif",
        color: "var(--color-ink-faint)",
      }}
    >
      {children}
    </p>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[14px] italic"
      style={{
        fontFamily: "Spectral, serif",
        color: "var(--color-ink-faint)",
      }}
    >
      {children}
    </p>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Toggle.
// ──────────────────────────────────────────────────────────────────────

function Toggle({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: () => void;
}) {
  return (
    <button
      onClick={onChange}
      type="button"
      className="relative inline-flex h-[18px] w-9 items-center transition-colors outline-none"
      style={{
        background: enabled
          ? "rgba(86, 207, 131, 0.20)"
          : "var(--color-rule-soft)",
        borderRadius: 999,
        border: "none",
        cursor: "pointer",
      }}
      aria-label={enabled ? "Disable rule" : "Enable rule"}
    >
      <span
        className="inline-block h-3 w-3 transition-transform"
        style={{
          background: enabled
            ? "var(--color-accent)"
            : "var(--color-ink-muted)",
          borderRadius: 999,
          transform: `translateX(${enabled ? "21px" : "3px"})`,
        }}
      />
    </button>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Condition flattening - clause-tree JSON → flat list.
// Handles `{all: [...]}`, `{any: [...]}`, `{not: …}`, plus the leaf
// shape `{field: {op: value}}`.
// ──────────────────────────────────────────────────────────────────────

interface FlatClause {
  field: string;
  op: string;
  value: unknown;
}

function flattenClauses(node: unknown): FlatClause[] {
  if (!node || typeof node !== "object") return [];
  const obj = node as Record<string, unknown>;
  if (Array.isArray(obj.all)) return obj.all.flatMap(flattenClauses);
  if (Array.isArray(obj.any)) return obj.any.flatMap(flattenClauses);
  if ("not" in obj) return flattenClauses(obj.not);
  const out: FlatClause[] = [];
  for (const [field, pred] of Object.entries(obj)) {
    if (!pred || typeof pred !== "object") {
      // Allow shorthand `{field: value}` which we treat as eq.
      if (pred !== undefined) {
        out.push({ field, op: "eq", value: pred });
      }
      continue;
    }
    for (const [op, value] of Object.entries(pred as Record<string, unknown>)) {
      out.push({ field, op, value });
    }
  }
  return out;
}

// ──────────────────────────────────────────────────────────────────────
// Humanizers - JSON → prose a Director would read.
// ──────────────────────────────────────────────────────────────────────

function humanizeClause(c: FlatClause): string {
  const subject = humanizeField(c.field);
  const isAmount = c.field.endsWith("amount_minor");
  const isConfidence =
    c.field.endsWith("model_confidence") ||
    c.field.endsWith("evidence_score") ||
    c.field.endsWith("decision_confidence");

  const formatVal = (v: unknown): string => {
    if (isAmount && typeof v === "number") {
      const dollars = v / 100;
      return dollars >= 1000
        ? `$${(dollars / 1000).toFixed(dollars % 1000 === 0 ? 0 : 1)}k`
        : `$${dollars.toFixed(dollars % 1 === 0 ? 0 : 2)}`;
    }
    if (isConfidence && typeof v === "number") {
      return `${Math.round(v * 100)}%`;
    }
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "string") return humanizeEnum(v);
    if (Array.isArray(v))
      return joinNatural(v.map((x) => humanizeEnum(String(x))));
    return String(v);
  };

  switch (c.op) {
    case "eq":
      return `${subject} is ${formatVal(c.value)}`;
    case "ne":
    case "neq":
      return `${subject} is not ${formatVal(c.value)}`;
    case "lt":
      return `${subject} is less than ${formatVal(c.value)}`;
    case "lte":
      return `${subject} is at most ${formatVal(c.value)}`;
    case "gt":
      return `${subject} is more than ${formatVal(c.value)}`;
    case "gte":
      return `${subject} is at least ${formatVal(c.value)}`;
    case "in":
      return `${subject} is one of ${formatVal(c.value)}`;
    case "nin":
    case "not_in":
      return `${subject} is none of ${formatVal(c.value)}`;
    case "is_true":
      return `${subject} is true`;
    case "is_false":
      return `${subject} is false`;
    case "contains":
      return `${subject} contains ${formatVal(c.value)}`;
    case "starts_with":
      return `${subject} starts with ${formatVal(c.value)}`;
    case "ends_with":
      return `${subject} ends with ${formatVal(c.value)}`;
    case "exists":
      return c.value === false
        ? `${subject} is missing`
        : `${subject} is set`;
    default:
      return `${subject} ${c.op} ${formatVal(c.value)}`;
  }
}

function humanizeField(path: string): string {
  const overrides: Record<string, string> = {
    "case.amount_minor": "Amount",
    "case.case_type": "Case type",
    "case.decision_action": "Decision action",
    "case.decision_confidence": "Decision confidence",
    "case.is_partial_refund": "Partial refund",
    "case.model_confidence": "Model confidence",
    "case.evidence_score": "Evidence score",
    "case.contract_on_file": "Contract on file",
    "case.incident_overlap_days": "Incident overlap",
    "case.trigger_surface": "Trigger source",
    "customer.prior_chargeback_count": "Prior chargebacks",
    "customer.prior_dispute_count": "Prior disputes",
    "customer.tenure_months": "Customer tenure (months)",
    "customer.has_prior_disputes": "Prior disputes",
  };
  if (overrides[path]) return overrides[path];
  const leaf = path.split(".").pop() ?? path;
  return leaf
    .replace(/_/g, " ")
    .replace(/^\w/, (m) => m.toUpperCase());
}

function humanizeEnum(s: string): string {
  return s.replace(/_/g, " ");
}

function joinNatural(parts: string[]): string {
  if (parts.length <= 1) return parts.join("");
  if (parts.length === 2) return parts.join(" or ");
  return `${parts.slice(0, -1).join(", ")}, or ${parts[parts.length - 1]}`;
}

function humanizeAction(action: string): string {
  const map: Record<string, string> = {
    escalate_to_human: "escalate",
    require_two_approvers: "require two approvers",
    hold_for_human: "hold for human review",
    refund_full: "refund (full)",
    refund: "refund",
    submit_evidence_fight: "fight (submit evidence)",
    recommend_prorata_credit: "credit (pro-rata)",
  };
  return map[action] ?? action.replace(/_/g, " ");
}

function humanizeReason(reason: string): string {
  const map: Record<string, string> = {
    repeat_disputer_pattern: "repeat disputer",
    amount_above_threshold: "amount above threshold",
    low_model_confidence: "low model confidence",
    clean_customer_under_threshold: "clean customer · under threshold",
    strong_evidence_packet: "strong evidence packet",
    documented_incident_overlap: "documented incident overlap",
  };
  return map[reason] ?? reason.replace(/_/g, " ");
}

// ──────────────────────────────────────────────────────────────────────
// Time helpers.
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
