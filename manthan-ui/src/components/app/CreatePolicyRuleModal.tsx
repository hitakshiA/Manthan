/**
 * CreatePolicyRuleModal - visual condition builder for new policy rules.
 *
 * Lets an operator compose a rule like:
 *   IF case.trigger_surface = inbound_email
 *      AND case.case_type IN [refund_request, duplicate_charge]
 *      AND case.amount_minor ≤ 20000
 *      AND case.decision_action = refund
 *      AND customer.has_prior_disputes = false
 *   THEN mode=auto
 *
 * Conditions get assembled into the policy engine's DSL:
 *   { "all": [ { "<field>": { "<op>": <value> } }, ... ] }
 *
 * POSTs to /api/policy/rules via createPolicyRule(). Caller refreshes
 * the list on success.
 */

import { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "motion/react";
import { Trash2, X, Loader2 } from "lucide-react";
import { createPolicyRule } from "@/lib/api";

type FieldKey =
  | "case.trigger_surface"
  | "case.case_type"
  | "case.amount_minor"
  | "case.decision_action"
  | "case.decision_confidence"
  | "case.age_days"
  | "case.findings_count"
  | "customer.has_prior_disputes"
  | "customer.prior_dispute_count";

type Op = "eq" | "neq" | "in" | "nin" | "lt" | "lte" | "gt" | "gte";

interface ConditionRow {
  id: string;
  field: FieldKey;
  op: Op;
  value: string; // Raw text - parsed at submit time
}

const FIELDS: { key: FieldKey; label: string; type: "string" | "number" | "bool" }[] = [
  { key: "case.trigger_surface", label: "Trigger surface", type: "string" },
  { key: "case.case_type", label: "Case type", type: "string" },
  { key: "case.amount_minor", label: "Amount (cents)", type: "number" },
  { key: "case.decision_action", label: "Decision action", type: "string" },
  { key: "case.decision_confidence", label: "Decision confidence (0-1)", type: "number" },
  { key: "case.age_days", label: "Age (days)", type: "number" },
  { key: "case.findings_count", label: "Findings count", type: "number" },
  { key: "customer.has_prior_disputes", label: "Customer has prior disputes", type: "bool" },
  { key: "customer.prior_dispute_count", label: "Customer prior dispute count", type: "number" },
];

const OPS_BY_TYPE: Record<"string" | "number" | "bool", { op: Op; label: string }[]> = {
  string: [
    { op: "eq", label: "=" },
    { op: "neq", label: "≠" },
    { op: "in", label: "in" },
    { op: "nin", label: "not in" },
  ],
  number: [
    { op: "eq", label: "=" },
    { op: "neq", label: "≠" },
    { op: "lt", label: "<" },
    { op: "lte", label: "≤" },
    { op: "gt", label: ">" },
    { op: "gte", label: "≥" },
  ],
  bool: [
    { op: "eq", label: "=" },
    { op: "neq", label: "≠" },
  ],
};

const MODES = ["auto", "suggest", "escalate"] as const;

export function CreatePolicyRuleModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]>("suggest");
  const [priority, setPriority] = useState(100);
  const [conds, setConds] = useState<ConditionRow[]>([
    { id: crypto.randomUUID(), field: "case.case_type", op: "eq", value: "" },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addCond = () => {
    setConds((c) => [
      ...c,
      { id: crypto.randomUUID(), field: "case.amount_minor", op: "lte", value: "" },
    ]);
  };
  const removeCond = (id: string) => {
    setConds((c) => (c.length === 1 ? c : c.filter((r) => r.id !== id)));
  };
  const updateCond = (id: string, patch: Partial<ConditionRow>) => {
    setConds((c) => c.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const compiledConds = compileConditions(conds);
      await createPolicyRule({
        name: name.trim(),
        description: description.trim() || undefined,
        conditions: compiledConds,
        decision: { mode },
        priority,
        enabled: true,
      });
      onCreated();
      onClose();
      resetForm();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setName("");
    setDescription("");
    setMode("suggest");
    setPriority(100);
    setConds([{ id: crypto.randomUUID(), field: "case.case_type", op: "eq", value: "" }]);
  };

  // Portal the modal to <body> so it escapes any transformed/animated
  // ancestor's containing block. Without this, `position: fixed` ends
  // up anchored to e.g. a parent Framer motion.div (which adds an
  // implicit transform during entrance), shrinking the backdrop to
  // that container's bounds and leaving sidebar/user-widget strips
  // unblurred at the edges of the viewport.
  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.97 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-[100] flex items-center justify-center p-6 pointer-events-none"
          >
            <div
              className="pointer-events-auto w-full max-w-2xl overflow-hidden flex flex-col max-h-[88vh] border"
              style={{
                background: "var(--color-bg)",
                borderColor: "var(--color-rule)",
                borderRadius: "var(--radius-md)",
                boxShadow: "0 24px 64px rgba(0,0,0,0.55)",
              }}
            >
              <header
                className="px-6 py-4 border-b flex items-baseline justify-between"
                style={{ borderColor: "var(--color-rule-soft)" }}
              >
                <div>
                  <div
                    className="eyebrow"
                    style={{ color: "var(--color-ink-faint)" }}
                  >
                    New rule
                  </div>
                  <h2
                    className="font-display text-[22px] leading-tight mt-1.5"
                    style={{ color: "var(--color-ink-strong)" }}
                  >
                    Create a policy rule
                  </h2>
                </div>
                <button
                  onClick={onClose}
                  className="p-1.5 hover:opacity-90"
                  style={{ color: "var(--color-ink-faint)" }}
                >
                  <X className="h-4 w-4" />
                </button>
              </header>

              <form onSubmit={submit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
                <FieldGroup label="Name" hint="A short, unique identifier (kebab-case recommended).">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. small-refund-auto"
                    required
                    data-tour-target="rule-name-input"
                    className="w-full h-9 px-2.5 rounded-[3px] border bg-transparent text-[13px] focus:outline-none"
                    style={{
                      borderColor: "var(--color-rule)",
                      color: "var(--color-ink-strong)",
                    }}
                  />
                </FieldGroup>

                <FieldGroup label="Description" optional>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What this rule does. Plain English."
                    rows={2}
                    className="w-full px-2.5 py-2 rounded-[3px] border bg-transparent text-[13px] focus:outline-none resize-none"
                    style={{
                      borderColor: "var(--color-rule)",
                      color: "var(--color-ink-strong)",
                    }}
                  />
                </FieldGroup>

                <div data-tour-target="rule-conditions">
                  <FieldGroup label="When ALL of these are true">
                    <div className="space-y-2">
                      {conds.map((row, i) => (
                        <ConditionRowEditor
                          key={row.id}
                          row={row}
                          canDelete={conds.length > 1}
                          isFirst={i === 0}
                          onChange={(patch) => updateCond(row.id, patch)}
                          onDelete={() => removeCond(row.id)}
                        />
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={addCond}
                      className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] uppercase tracking-[0.13em] hover:opacity-90"
                      style={{ color: "var(--color-accent)" }}
                    >
                      + Add condition
                    </button>
                  </FieldGroup>
                </div>

                <FieldGroup label="Then">
                  <div className="flex items-baseline gap-5" data-tour-target="rule-mode-group">
                    {MODES.map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMode(m)}
                        data-tour-target={m === "auto" ? "rule-mode-auto" : undefined}
                        data-tour-selected={mode === m ? "true" : "false"}
                        className="text-[11.5px] uppercase tracking-[0.13em] transition-opacity hover:opacity-90"
                        style={{
                          color:
                            mode === m
                              ? "var(--color-ink-strong)"
                              : "var(--color-ink-faint)",
                          fontWeight: mode === m ? 600 : 500,
                          textDecoration: mode === m ? "underline" : "none",
                          textUnderlineOffset: 4,
                        }}
                      >
                        {{ auto: "auto-execute", suggest: "recommend", escalate: "escalate" }[m]}
                      </button>
                    ))}
                  </div>
                </FieldGroup>

                <FieldGroup label="Priority" hint="Lower number = evaluated first.">
                  <input
                    type="number"
                    value={priority}
                    onChange={(e) => setPriority(Number(e.target.value))}
                    className="w-24 h-9 px-2.5 rounded-[3px] border bg-transparent text-[13px] tabular-nums focus:outline-none"
                    style={{
                      borderColor: "var(--color-rule)",
                      color: "var(--color-ink-strong)",
                    }}
                  />
                </FieldGroup>

                {error && (
                  <div
                    className="text-[12.5px] py-2"
                    style={{ color: "var(--color-danger)" }}
                  >
                    {error}
                  </div>
                )}
              </form>

              <footer
                className="px-6 py-4 border-t flex items-center justify-between"
                style={{ borderColor: "var(--color-rule-soft)" }}
              >
                <p
                  className="text-[11px] italic font-display"
                  style={{ color: "var(--color-ink-ghost)" }}
                >
                  Compiles to the engine&apos;s JSON DSL.
                </p>
                <div className="flex items-center gap-4">
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-[12.5px] hover:opacity-90"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submit}
                    disabled={submitting || !name.trim()}
                    data-tour-target="rule-save"
                    className="h-8 px-3.5 text-[12.5px] font-medium disabled:opacity-50 inline-flex items-center gap-1.5 rounded-[3px]"
                    style={{
                      background: "var(--color-ink-strong)",
                      color: "var(--color-bg)",
                    }}
                  >
                    {submitting && <Loader2 className="h-3 w-3 animate-spin" />}
                    Create rule
                  </button>
                </div>
              </footer>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}

function FieldGroup({
  label,
  hint,
  optional,
  children,
}: {
  label: string;
  hint?: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <label
          className="eyebrow"
          style={{ color: "var(--color-ink-faint)" }}
        >
          {label}
        </label>
        {optional && (
          <span
            className="text-[10px] italic font-display"
            style={{ color: "var(--color-ink-ghost)" }}
          >
            optional
          </span>
        )}
      </div>
      {children}
      {hint && (
        <div
          className="text-[11px] italic font-display"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

function ConditionRowEditor({
  row,
  canDelete,
  isFirst,
  onChange,
  onDelete,
}: {
  row: ConditionRow;
  canDelete: boolean;
  isFirst: boolean;
  onChange: (patch: Partial<ConditionRow>) => void;
  onDelete: () => void;
}) {
  const fieldMeta = FIELDS.find((f) => f.key === row.field)!;
  const ops = OPS_BY_TYPE[fieldMeta.type];
  const sharedStyle = {
    borderColor: "var(--color-rule)",
    color: "var(--color-ink-strong)",
  } as const;
  return (
    <div className="flex items-center gap-2">
      <span
        className="text-[10px] uppercase tracking-[0.13em] w-10 shrink-0"
        style={{ color: "var(--color-ink-ghost)" }}
      >
        {isFirst ? "where" : "and"}
      </span>
      <select
        value={row.field}
        onChange={(e) => onChange({ field: e.target.value as FieldKey })}
        className="h-9 px-2 rounded-[3px] border bg-transparent text-[12.5px] focus:outline-none flex-1 min-w-0"
        style={sharedStyle}
      >
        {FIELDS.map((f) => (
          <option
            key={f.key}
            value={f.key}
            style={{ background: "var(--color-bg)" }}
          >
            {f.label}
          </option>
        ))}
      </select>
      <select
        value={row.op}
        onChange={(e) => onChange({ op: e.target.value as Op })}
        className="h-9 px-2 rounded-[3px] border bg-transparent text-[12.5px] focus:outline-none w-20"
        style={sharedStyle}
      >
        {ops.map((o) => (
          <option
            key={o.op}
            value={o.op}
            style={{ background: "var(--color-bg)" }}
          >
            {o.label}
          </option>
        ))}
      </select>
      <input
        value={row.value}
        onChange={(e) => onChange({ value: e.target.value })}
        placeholder={
          fieldMeta.type === "bool"
            ? "true / false"
            : row.op === "in" || row.op === "nin"
              ? "a, b, c"
              : "value"
        }
        className="h-9 px-2 rounded-[3px] border bg-transparent text-[12.5px] focus:outline-none flex-1 min-w-0"
        style={sharedStyle}
      />
      <button
        type="button"
        disabled={!canDelete}
        onClick={onDelete}
        className="p-1 disabled:opacity-30 hover:opacity-90"
        style={{ color: "var(--color-ink-faint)" }}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** Convert UI rows into the engine's JSON DSL. */
function compileConditions(rows: ConditionRow[]): Record<string, unknown> {
  const all = rows
    .filter((r) => r.value.trim() !== "")
    .map((r) => {
      const meta = FIELDS.find((f) => f.key === r.field)!;
      let value: unknown;

      if (r.op === "in" || r.op === "nin") {
        // Comma-separated list
        value = r.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .map((s) => coerce(s, meta.type));
      } else {
        value = coerce(r.value.trim(), meta.type);
      }

      return { [r.field]: { [r.op]: value } };
    });

  return { all };
}

function coerce(raw: string, type: "string" | "number" | "bool"): unknown {
  if (type === "number") return Number(raw);
  if (type === "bool") {
    const v = raw.toLowerCase();
    if (v === "true" || v === "1") return true;
    if (v === "false" || v === "0") return false;
    return raw;
  }
  return raw;
}
