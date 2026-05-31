/**
 * DraftPolicies - Policies page, editorial-memo direction (DRAFT).
 *
 * Each rule is a mini-memo, same vocabulary as WorkspaceMemo:
 * HeaderStrip + two-column canvas separated by a hairline. The page
 * itself reads as a stack of small editorial cards under a Spectral
 * italic title.
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ RULE 75 · documented-incident-prorata-credit  [mode] [on]    │
 *   │ ──────────────────────────────────────────────────────────── │
 *   │  WHEN                       │  DECISION                      │
 *   │  italic description         │  Mode: recommend               │
 *   │  Conditions                 │  Action: refund …              │
 *   │  01. amount is at most $200 │  ───────────────               │
 *   │  02. case is a chargeback   │  MATCHED · 1 time (90d)        │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Six hardcoded rules. No links. Disabled rules at 50% opacity.
 *
 * Throwaway draft - route /app/policies-memo.
 */

import { useState } from "react";
import { motion } from "motion/react";
import { Plus } from "lucide-react";

// ──────────────────────────────────────────────────────────────────────
// Mock data - the real Manthan policy seed shape.
// Conditions are stored as the raw clause-tree JSON so we can render
// the same humanizer twice (engine consumes JSON, humans read prose).
// ──────────────────────────────────────────────────────────────────────

type Mode = "auto" | "recommend" | "escalate" | "hitl";

type Op = "eq" | "neq" | "lt" | "lte" | "gt" | "gte" | "in" | "nin" | "is_true" | "is_false";

interface Clause {
  field: string;
  op: Op;
  value?: unknown;
}

interface Decision {
  action: string;
  reason: string;
  replyToCustomer: boolean;
  submitEvidence: boolean;
}

interface Rule {
  priority: number;
  name: string;
  description: string;
  mode: Mode;
  enabled: boolean;
  conditions: Clause[];
  decision: Decision;
  matched: { count: number; windowDays: number };
}

const RULES: Rule[] = [
  {
    priority: 10,
    name: "repeat-disputer-escalate",
    description:
      "Customers with a history of chargebacks need a human in the loop - the agent should never silently fight or concede their next case.",
    mode: "escalate",
    enabled: true,
    conditions: [
      { field: "customer.prior_chargeback_count", op: "gte", value: 2 },
      { field: "case.case_type", op: "eq", value: "chargeback" },
    ],
    decision: {
      action: "escalate_to_human",
      reason: "repeat_disputer_pattern",
      replyToCustomer: false,
      submitEvidence: false,
    },
    matched: { count: 0, windowDays: 90 },
  },
  {
    priority: 20,
    name: "large-amount-two-approvers",
    description:
      "Any decision moving more than five thousand dollars requires a second approver. The agent stages the action and pauses for a co-sign.",
    mode: "escalate",
    enabled: true,
    conditions: [
      { field: "case.amount_minor", op: "gte", value: 500000 },
      { field: "case.decision_action", op: "in", value: ["refund", "concede"] },
    ],
    decision: {
      action: "require_two_approvers",
      reason: "amount_above_threshold",
      replyToCustomer: false,
      submitEvidence: false,
    },
    matched: { count: 2, windowDays: 90 },
  },
  {
    priority: 30,
    name: "low-confidence-require-human",
    description:
      "When the model's confidence on a recommended verdict drops below seventy percent, hold the case for a human to decide.",
    mode: "hitl",
    enabled: true,
    conditions: [
      { field: "case.model_confidence", op: "lt", value: 0.7 },
      { field: "case.case_type", op: "neq", value: "informational" },
    ],
    decision: {
      action: "hold_for_human",
      reason: "low_model_confidence",
      replyToCustomer: false,
      submitEvidence: false,
    },
    matched: { count: 14, windowDays: 90 },
  },
  {
    priority: 50,
    name: "email-refund-clean-customer",
    description:
      "An email refund request from a long-tenured customer with no prior disputes can be auto-approved up to two hundred dollars.",
    mode: "auto",
    enabled: true,
    conditions: [
      { field: "case.case_type", op: "eq", value: "email_refund" },
      { field: "case.amount_minor", op: "lte", value: 20000 },
      { field: "customer.tenure_months", op: "gte", value: 12 },
      { field: "customer.prior_chargeback_count", op: "eq", value: 0 },
    ],
    decision: {
      action: "refund_full",
      reason: "clean_customer_under_threshold",
      replyToCustomer: true,
      submitEvidence: false,
    },
    matched: { count: 47, windowDays: 90 },
  },
  {
    priority: 60,
    name: "chargeback-fight-strong-evidence",
    description:
      "When a chargeback case carries a strong evidence packet - contract, usage, and customer-satisfaction confirmations - fight automatically.",
    mode: "auto",
    enabled: true,
    conditions: [
      { field: "case.case_type", op: "eq", value: "chargeback" },
      { field: "case.evidence_score", op: "gte", value: 0.85 },
      { field: "case.contract_on_file", op: "is_true" },
    ],
    decision: {
      action: "submit_evidence_fight",
      reason: "strong_evidence_packet",
      replyToCustomer: false,
      submitEvidence: true,
    },
    matched: { count: 8, windowDays: 90 },
  },
  {
    priority: 75,
    name: "documented-incident-prorata-credit",
    description:
      "If the customer disputes during a documented incident window, offer a pro-rata credit for the degraded days rather than the full amount.",
    mode: "recommend",
    enabled: true,
    conditions: [
      { field: "case.case_type", op: "eq", value: "chargeback" },
      {
        field: "case.decision_action",
        op: "in",
        value: ["refund_partial", "credit_partial"],
      },
      { field: "case.is_partial_refund", op: "is_true" },
      { field: "case.incident_overlap_days", op: "gte", value: 1 },
    ],
    decision: {
      action: "recommend_prorata_credit",
      reason: "documented_incident_overlap",
      replyToCustomer: true,
      submitEvidence: false,
    },
    matched: { count: 1, windowDays: 90 },
  },
];

// ──────────────────────────────────────────────────────────────────────
// Mode tokens - color, label, and dim variant.
// ──────────────────────────────────────────────────────────────────────

interface ModeToken {
  label: string;
  color: string;
  /** Faint version of the same hue for the row background on hover. */
  soft: string;
}

const MODE: Record<Mode, ModeToken> = {
  auto: {
    label: "auto",
    color: "rgba(86, 207, 131, 0.92)",
    soft: "rgba(86, 207, 131, 0.10)",
  },
  recommend: {
    label: "recommend",
    color: "rgba(255, 182, 77, 0.92)",
    soft: "rgba(255, 182, 77, 0.10)",
  },
  escalate: {
    label: "escalate",
    color: "rgba(255, 107, 107, 0.92)",
    soft: "rgba(255, 107, 107, 0.10)",
  },
  hitl: {
    label: "hitl",
    color: "rgba(120, 178, 255, 0.92)",
    soft: "rgba(120, 178, 255, 0.10)",
  },
};

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

export default function DraftPolicies() {
  return (
    <div
      className="h-full w-full overflow-y-auto px-6 py-6"
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
        <PageHeader />
        <div className="px-12 pb-14 pt-2 flex flex-col gap-5">
          {RULES.map((rule) => (
            <RuleMemo key={rule.priority} rule={rule} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Page header - eyebrow + title + subtitle + CTA.
// ──────────────────────────────────────────────────────────────────────

function PageHeader() {
  const enabledCount = RULES.filter((r) => r.enabled).length;
  return (
    <header className="px-12 pt-12 pb-9">
      <Eyebrow>Policies</Eyebrow>
      <div className="mt-3 flex items-end justify-between gap-6 flex-wrap">
        <div className="min-w-0">
          <h1
            className="leading-[1.06]"
            style={{
              fontFamily: "Spectral, serif",
              fontSize: "clamp(34px, 3.4vw, 42px)",
              color: "rgba(255,255,255,0.96)",
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
              color: "rgba(255,255,255,0.55)",
              letterSpacing: "-0.003em",
              lineHeight: 1.5,
            }}
          >
            {enabledCount === RULES.length ? "Six" : enabledCount} rules ·
            last reload 14 minutes ago. Click a rule to edit.
          </p>
        </div>
        <NewRuleButton />
      </div>
    </header>
  );
}

function NewRuleButton() {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1.5 transition-all hover:opacity-95 hover:translate-y-[-1px] outline-none"
      style={{
        background: "rgba(255,255,255,0.96)",
        color: "#0a0a0a",
        borderRadius: 4,
        fontSize: 13,
        fontWeight: 500,
        letterSpacing: "-0.002em",
        padding: "8px 14px",
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.6) inset, " +
          "0 4px 14px rgba(0,0,0,0.30), " +
          "0 0 0 1px rgba(255,255,255,0.55)",
        border: "none",
        cursor: "pointer",
      }}
    >
      <Plus size={13} strokeWidth={2.4} />
      New rule
    </button>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RuleMemo - one rule as a HeaderStrip + two-column body card.
// ──────────────────────────────────────────────────────────────────────

function RuleMemo({ rule }: { rule: Rule }) {
  const [hover, setHover] = useState(false);
  const mode = MODE[rule.mode];
  const dim = !rule.enabled;

  return (
    <motion.section
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      animate={{ opacity: dim ? 0.5 : 1 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden"
      style={{
        background: hover && !dim ? "rgba(255,255,255,0.018)" : "transparent",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 6,
        cursor: "pointer",
        transition: "background 200ms ease",
      }}
    >
      <RuleHeaderStrip rule={rule} />

      <div
        className="grid"
        style={{
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
        }}
      >
        <RuleWhenColumn rule={rule} />
        <RuleDecisionColumn rule={rule} mode={mode} />
      </div>
    </motion.section>
  );
}

// ──────────────────────────────────────────────────────────────────────
// HeaderStrip - RULE NN · name + mode badge + ENABLED status.
// ──────────────────────────────────────────────────────────────────────

function RuleHeaderStrip({ rule }: { rule: Rule }) {
  const mode = MODE[rule.mode];
  return (
    <header
      className="flex items-center px-7 shrink-0"
      style={{
        height: 52,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span
        className="font-mono text-[12.5px] uppercase tabular-nums"
        style={{
          color: "rgba(255,255,255,0.55)",
          letterSpacing: "0.18em",
        }}
      >
        RULE&nbsp;{rule.priority.toString().padStart(2, "0")}
      </span>

      <span
        className="mx-3"
        style={{ color: "rgba(255,255,255,0.22)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[16px]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          color: "rgba(255,255,255,0.92)",
          letterSpacing: "-0.006em",
        }}
      >
        {rule.name}
      </span>

      <span
        className="ml-5 text-[11.5px] uppercase"
        style={{
          color: mode.color,
          letterSpacing: "0.20em",
          fontWeight: 500,
        }}
        title={`mode · ${mode.label}`}
      >
        {mode.label}
      </span>

      <span
        className="ml-auto text-[11.5px] uppercase"
        style={{
          color: rule.enabled
            ? "rgba(86, 207, 131, 0.85)"
            : "rgba(255,255,255,0.36)",
          letterSpacing: "0.22em",
          fontWeight: 500,
        }}
      >
        {rule.enabled ? "Enabled" : "Disabled"}
      </span>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// LEFT column - "When". Description + numbered prose conditions.
// ──────────────────────────────────────────────────────────────────────

function RuleWhenColumn({ rule }: { rule: Rule }) {
  return (
    <div className="px-8 py-7 flex flex-col gap-5">
      <div>
        <Eyebrow>When</Eyebrow>
        <p
          className="mt-3 text-[14px] leading-[1.55] max-w-[58ch]"
          style={{
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
            color: "rgba(255,255,255,0.62)",
            letterSpacing: "-0.003em",
          }}
        >
          {rule.description}
        </p>
      </div>

      <div>
        <Eyebrow>Conditions</Eyebrow>
        <ol className="mt-3 space-y-2">
          {rule.conditions.map((clause, i) => (
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
                  color: "rgba(255,255,255,0.36)",
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
                  color: "rgba(255,255,255,0.86)",
                  letterSpacing: "-0.002em",
                }}
              >
                {humanizeClause(clause)}
              </span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// RIGHT column - "Decision" + Matched counter.
// ──────────────────────────────────────────────────────────────────────

function RuleDecisionColumn({
  rule,
  mode,
}: {
  rule: Rule;
  mode: ModeToken;
}) {
  return (
    <div
      className="px-8 py-7 flex flex-col gap-5"
      style={{ borderLeft: "1px solid rgba(255,255,255,0.06)" }}
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
          <KeyValue label="Action" value={humanizeAction(rule.decision.action)} />
          <KeyValue label="Reason" value={humanizeReason(rule.decision.reason)} />
          <KeyValue
            label="Reply to customer"
            value={rule.decision.replyToCustomer ? "yes" : "no"}
            mute={!rule.decision.replyToCustomer}
          />
          <KeyValue
            label="Submit evidence"
            value={rule.decision.submitEvidence ? "yes" : "no"}
            mute={!rule.decision.submitEvidence}
          />
        </dl>
      </div>

      <div
        className="pt-5 flex items-baseline gap-3"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Eyebrow>Matched</Eyebrow>
        <MatchedCount count={rule.matched.count} windowDays={rule.matched.windowDays} />
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
          color: "rgba(255,255,255,0.88)",
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
            ? "rgba(255,255,255,0.42)"
            : "rgba(255,255,255,0.62)",
          letterSpacing: "-0.002em",
        }}
      >
        {valueIsNode ? value : <span>{value}</span>}
      </dd>
    </div>
  );
}

function MatchedCount({
  count,
  windowDays,
}: {
  count: number;
  windowDays: number;
}) {
  if (count === 0) {
    return (
      <span
        className="font-mono text-[12.5px] tabular-nums"
        style={{
          color: "rgba(255,255,255,0.40)",
          letterSpacing: "0.04em",
        }}
      >
        0 times · last {windowDays} days
      </span>
    );
  }
  return (
    <span
      className="font-mono text-[12.5px] tabular-nums"
      style={{
        color: "rgba(255,255,255,0.72)",
        letterSpacing: "0.04em",
      }}
    >
      {count.toLocaleString()} {count === 1 ? "time" : "times"} · last {windowDays} days
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Eyebrow primitive - mirrors the WorkspaceMemo one 1:1.
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
// Humanizers - turn the engine JSON into prose a Director would read.
// Per .impeccable.md: render `{"case.amount_minor":{"lte":20000}}` as
// "Amount is at most $200" - not as the raw clause.
// ──────────────────────────────────────────────────────────────────────

/**
 * Pretty-print a single clause. The same JSON that drives the rule
 * engine, rendered for the human reader.
 */
function humanizeClause(c: Clause): string {
  const subject = humanizeField(c.field);
  const isAmount = c.field.endsWith("amount_minor");
  const formatVal = (v: unknown): string => {
    if (isAmount && typeof v === "number") {
      // amount_minor is cents
      const dollars = v / 100;
      return dollars >= 1000
        ? `$${(dollars / 1000).toFixed(dollars % 1000 === 0 ? 0 : 1)}k`
        : `$${dollars.toFixed(dollars % 1 === 0 ? 0 : 2)}`;
    }
    if (typeof v === "number" && c.field.endsWith("model_confidence")) {
      return `${Math.round(v * 100)}%`;
    }
    if (typeof v === "number" && c.field.endsWith("evidence_score")) {
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
      return `${subject} is none of ${formatVal(c.value)}`;
    case "is_true":
      return `${subject} is true`;
    case "is_false":
      return `${subject} is false`;
  }
}

/**
 * Turn a dotted field path into a Title-case subject. We special-case
 * fields where the literal translation would read awkwardly.
 */
function humanizeField(path: string): string {
  const overrides: Record<string, string> = {
    "case.amount_minor": "Amount",
    "case.case_type": "Case",
    "case.decision_action": "Decision action",
    "case.is_partial_refund": "Partial refund",
    "case.model_confidence": "Model confidence",
    "case.evidence_score": "Evidence score",
    "case.contract_on_file": "Contract on file",
    "case.incident_overlap_days": "Incident overlap",
    "customer.prior_chargeback_count": "Prior chargebacks",
    "customer.tenure_months": "Customer tenure (months)",
  };
  if (overrides[path]) return overrides[path];
  // Default - strip the namespace and Title-Case the leaf.
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
