import { useEffect, useState, type ReactNode } from "react";
import {
  X,
  ChevronDown,
  ChevronRight,
  Database,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useClaimDescription } from "@/hooks/use-claim-description";
import { useSmoothText } from "@/lib/smooth-text";
import type { NumericClaim } from "@/types/conversation";

/**
 * Exec-facing audit drawer — opens when a numeric claim is clicked in
 * the conversation. Plain-English lead, technical detail tucked behind
 * a collapsible section for the minority of users who want the SQL.
 *
 * Design goals (learned from exec review):
 *   1. The first thing the exec reads must be a one-sentence
 *      interpretation of the number — NOT a SQL statement.
 *   2. "Where did this come from?" — dataset, filters, rows — in
 *      natural language, not column names or WHERE clauses.
 *   3. SQL + run_id still available for auditors and power users, but
 *      defaulted closed so they don't dominate the view.
 */

export function CalculationDrawer() {
  const claim = useAgentStore((s) => s.inspectedClaim);
  const close = useAgentStore((s) => s.setInspectedClaim);
  const [showTechnical, setShowTechnical] = useState(false);
  // Fire the rich-description side-call when the drawer opens. While
  // it's in flight we still render the regex description so the
  // exec never stares at an empty section — the LLM result just
  // upgrades the text in place when it lands.
  const rich = useClaimDescription(claim);

  // Derive the raw summary BEFORE any early return so all hooks
  // below run unconditionally on every render (rules-of-hooks).
  // When claim is null these defaults are harmless — the engine
  // idles on an empty string and we bail out below.
  const regexSummary = claim
    ? (claim.description && claim.description.trim()) ||
      buildPlainEnglishSummary(claim)
    : "";
  // Show the LLM text the moment *any* token has arrived. If the
  // call ended with nothing (errored), fall back to the regex line
  // silently. While the call is still in flight with no tokens yet
  // we feed the engine an empty string so the drawer shows the
  // prominent "tracing" placeholder below, *not* the pre-LLM
  // regex — the regex summary is only a last-resort fallback, not
  // the lead.
  const summaryRaw = rich.description
    ? rich.description
    : rich.errored
      ? regexSummary
      : "";
  const streamKey = claim
    ? rich.description
      ? `claim-${claim.value}-llm`
      : `claim-${claim.value}-regex`
    : "claim-empty";
  // Jitter buffer. Holds a cursor into summaryRaw and reveals chars
  // at an adaptive cadence — even when tokens arrive bursty over
  // SSE, the rendered text moves at a steady word-per-beat.
  const { visibleText: summary, isAnimating: summaryAnimating } =
    useSmoothText(summaryRaw, {
      streamKey,
      isStreaming: rich.loading || rich.streaming,
    });

  // Close on Escape; reset technical toggle when a new claim is opened.
  useEffect(() => {
    if (!claim) return;
    setShowTechnical(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [claim, close]);

  if (!claim) return null;

  // Unverified state — the agent cited a number without calling a
  // data tool. We render an honest "no audit trail" drawer so the
  // exec can see the number ISN'T backed by this session's data,
  // rather than silently showing nothing on click.
  const isUnverified = claim.label === "Unverified number";

  // Whether this claim has ANYTHING we could cite in an audit
  // trail. The backend emits many real compute_metric / SQL cells
  // with the generic label ``Cited number`` (because the column
  // isn't a named metric), so we can't gate on the label — we
  // gate on whether there's any provenance to feed the LLM. The
  // freeform synthesizer in NarrativeBlock deliberately strips
  // entity/sql/filters/row_count for no-match clicks, and those
  // correctly fall on the empty side of this predicate.
  const hasProvenance = Boolean(
    claim.entity ||
      claim.metric_ref ||
      (claim.sql && claim.sql.trim()) ||
      claim.filters_applied.length > 0 ||
      (claim.dimensions && claim.dimensions.length > 0) ||
      claim.row_count_scanned != null,
  );

  const provenance = buildProvenanceLine(claim);
  const filterLines = claim.filters_applied.map(humanizeFilter);
  const dims = claim.dimensions.filter(Boolean);

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 bg-black/20 z-40 animate-fade-in"
        onClick={() => close(null)}
        aria-hidden
      />
      {/* Drawer */}
      <aside
        className="fixed top-0 right-0 h-full w-[520px] max-w-[92vw] bg-surface-0 border-l border-border shadow-2xl z-50 flex flex-col animate-fade-rise-delay"
        role="dialog"
        aria-label="How was this calculated?"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-1 shrink-0">
          <span className="text-[11px] text-text-faint font-body uppercase tracking-wider">
            How was this calculated?
          </span>
          <button
            onClick={() => close(null)}
            className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 font-body">
          {/* The number itself — giant, unambiguous */}
          <section>
            <div className="text-[11px] text-text-faint uppercase tracking-wider mb-1.5">
              {claim.label || "Cited number"}
            </div>
            <div className="text-5xl font-serif text-text-primary leading-none">
              {claim.formatted}
            </div>
          </section>

          {/* Unverified banner — shown when the agent cited a
              number without calling any data tool. Honest > silent. */}
          {isUnverified && (
            <section className="rounded-lg border border-warning/30 bg-warning-soft/40 p-3 flex gap-2 items-start">
              <AlertTriangle
                size={14}
                className="mt-0.5 shrink-0 text-warning"
              />
              <div className="text-[13px] text-text-primary leading-relaxed">
                <strong className="font-semibold">No audit trail.</strong>{" "}
                The agent cited this number without running a data tool
                in this session, so we can't show the query that
                produced it. Re-ask the question to force a verified
                calculation.
              </div>
            </section>
          )}

          {/* Audit trail — the FIRST thing the exec reads.
              While the LLM is tracing, we render a prominent
              "tracing to semantic layer…" placeholder at the same
              font size as the real audit text (NOT the regex
              fallback — that used to leak in and made the drawer
              feel pre-computed). Once tokens arrive we swap to
              the real sentence; if the LLM errors, we silently
              fall back to the regex line. */}
          {hasProvenance && !isUnverified && (
            <section>
              <div className="text-[11px] text-text-faint uppercase tracking-wider mb-2">
                Audit trail
              </div>
              {!summary && (rich.loading || rich.streaming) ? (
                <div className="flex items-start gap-2.5 text-[16px] text-text-secondary leading-relaxed py-0.5">
                  <Sparkles
                    size={18}
                    className="mt-[3px] shrink-0 text-accent animate-pulse"
                  />
                  <span>
                    Tracing to the semantic layer
                    <span className="inline-block animate-pulse">…</span>
                  </span>
                </div>
              ) : (
                <p className="text-[16px] text-text-primary leading-relaxed">
                  {renderWithBackticks(summary)}
                  {(rich.streaming || summaryAnimating) && (
                    <span
                      className="inline-block w-[2px] h-[1em] ml-[2px] align-[-2px] bg-accent animate-pulse"
                      aria-hidden
                    />
                  )}
                </p>
              )}
            </section>
          )}

          {/* Natural-language filters (no SQL) */}
          {filterLines.length > 0 && (
            <section>
              <div className="text-[11px] text-text-faint uppercase tracking-wider mb-2">
                Filtered to
              </div>
              <ul className="space-y-1.5">
                {filterLines.map((f, i) => (
                  <li
                    key={i}
                    className="text-[14px] text-text-primary leading-relaxed flex gap-2"
                  >
                    <span className="text-accent mt-0.5">•</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Dimensions + grain (light, natural) */}
          {(dims.length > 0 || claim.grain) && (
            <section>
              <div className="text-[11px] text-text-faint uppercase tracking-wider mb-2">
                Broken down by
              </div>
              <p className="text-[14px] text-text-primary leading-relaxed">
                {[
                  dims.length > 0 ? dims.map(humanizeColumnLabel).join(", ") : null,
                  claim.grain ? `${claim.grain} time grain` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </section>
          )}

          {/* Provenance — dataset + row count in one line */}
          <section className="flex items-start gap-2 text-[13px] text-text-tertiary border-t border-border pt-4">
            <Database size={14} className="mt-0.5 shrink-0 text-text-faint" />
            <span className="leading-relaxed">{provenance}</span>
          </section>

          {/* Technical detail — always available (even when SQL is
              absent we still want to expose metric slug, dimensions,
              grain, run id). The point of this panel is that an
              analyst can reproduce the number, so bare ``run: X``
              with nothing else is worse than useless. */}
          <section className="border-t border-border pt-4">
            <button
              onClick={() => setShowTechnical((v) => !v)}
              className="flex items-center gap-1.5 text-[11px] text-text-tertiary hover:text-text-secondary uppercase tracking-wider font-medium"
            >
              {showTechnical ? (
                <ChevronDown size={12} />
              ) : (
                <ChevronRight size={12} />
              )}
              Technical detail
            </button>

            {showTechnical && (
              <div className="mt-3 space-y-3">
                {/* Metadata chips — rows scanned, metric slug, grain,
                    dimensions. Compact, one row each for readability. */}
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  {claim.metric_ref && (
                    <MetaChip label="metric" value={claim.metric_ref} mono />
                  )}
                  {claim.entity && (
                    <MetaChip label="entity" value={claim.entity} mono />
                  )}
                  {claim.row_count_scanned != null && (
                    <MetaChip
                      label="rows scanned"
                      value={claim.row_count_scanned.toLocaleString()}
                    />
                  )}
                  {claim.grain && (
                    <MetaChip label="grain" value={claim.grain} />
                  )}
                  {dims.length > 0 && (
                    <MetaChip
                      label="dimensions"
                      value={dims.map(humanizeColumnLabel).join(", ")}
                    />
                  )}
                </div>

                {claim.sql && (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-[10px] text-text-faint uppercase tracking-wider">
                        SQL executed
                      </div>
                      <CopyButton text={claim.sql} />
                    </div>
                    <pre className="text-[11px] font-mono bg-surface-sunken px-3 py-2 rounded-md text-text-secondary overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[260px]">
                      {claim.sql}
                    </pre>
                  </div>
                )}
                {!claim.sql && !claim.metric_ref && (
                  <div className="text-[12px] text-text-tertiary italic">
                    This number came from a tool call that didn't emit
                    a SQL string. The semantic-layer audit above is the
                    authoritative trail.
                  </div>
                )}
                {claim.run_id && (
                  <div
                    className="text-[10px] text-text-faint font-mono"
                    title="Backend trace id — pair this with server logs to re-run or debug."
                  >
                    run trace id: {claim.run_id}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}

// ── Technical-detail helpers ───────────────────────────────────────

function MetaChip({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-border bg-surface-1">
      <span className="text-text-faint uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span
        className={
          mono
            ? "font-mono text-[11px] text-text-primary"
            : "text-[11px] text-text-primary"
        }
      >
        {value}
      </span>
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        } catch {
          /* silent */
        }
      }}
      className="text-[10px] text-text-faint hover:text-accent uppercase tracking-wider transition-colors"
    >
      {copied ? "copied" : "copy SQL"}
    </button>
  );
}

// ── Plain-English builders ─────────────────────────────────────────

/** One-sentence interpretation of what the cited number represents. */
function buildPlainEnglishSummary(c: NumericClaim): string {
  const label = humanizeColumnLabel(c.label) || "Cited number";
  const entity = c.entity ? ` from the ${prettyEntity(c.entity)} dataset` : "";
  const metric = c.metric_ref ? ` (governed metric)` : "";
  return `${label}${entity}${metric}.`;
}

/** Short dataset + row-count provenance line. */
function buildProvenanceLine(c: NumericClaim): string {
  const parts: string[] = [];
  if (c.entity) parts.push(`from the ${prettyEntity(c.entity)} dataset`);
  if (typeof c.row_count_scanned === "number" && c.row_count_scanned > 0) {
    parts.push(
      `calculated from ${c.row_count_scanned.toLocaleString()} ${
        c.row_count_scanned === 1 ? "row" : "rows"
      }`,
    );
  }
  if (parts.length === 0) return "Pulled from the current analysis.";
  return parts.join(" · ");
}

/** Turn a WHERE-clause fragment into something a human can read.
 *  Covers the 3-4 shapes our agent emits; falls through to the raw
 *  SQL for anything exotic so we're never lying about the filter. */
function humanizeFilter(raw: string): string {
  if (!raw) return raw;
  let s = raw.trim();
  // Strip leading AND/OR
  s = s.replace(/^(AND|OR)\s+/i, "");
  // "Year" = 2019  →  year 2019
  let m = /^"?([A-Za-z_][\w. ]*)"?\s*=\s*(\d+)$/.exec(s);
  if (m) return `${humanizeColumnLabel(m[1])} ${m[2]}`;
  // "status" = 'delivered'  →  status is "delivered"
  m = /^"?([A-Za-z_][\w. ]*)"?\s*=\s*'([^']*)'$/.exec(s);
  if (m) return `${humanizeColumnLabel(m[1])} is "${m[2]}"`;
  // "State" IN ('A','B','C')
  m = /^"?([A-Za-z_][\w. ]*)"?\s+IN\s*\(([^)]+)\)$/i.exec(s);
  if (m) {
    const vals = m[2]
      .split(",")
      .map((v) => v.trim().replace(/^'|'$/g, ""))
      .filter(Boolean);
    const col = humanizeColumnLabel(m[1]);
    if (vals.length <= 4) return `${col}: ${vals.join(", ")}`;
    return `${col}: ${vals.slice(0, 3).join(", ")} + ${vals.length - 3} more`;
  }
  // "Year" >= 2015
  m = /^"?([A-Za-z_][\w. ]*)"?\s*(>=|<=|>|<)\s*(\d+)$/.exec(s);
  if (m) {
    const op = { ">=": "at or after", "<=": "at or before", ">": "after", "<": "before" }[m[2]] || m[2];
    return `${humanizeColumnLabel(m[1])} ${op} ${m[3]}`;
  }
  // BETWEEN — skip parsing, render tidied
  return s.replace(/"/g, "");
}

/** Turn "Totals.Revenue" / "debt_to_revenue_pct" into "Revenue" / "Debt To Revenue Pct" */
function humanizeColumnLabel(name: string): string {
  if (!name) return name;
  const last = name.split(".").pop()!.trim();
  return last
    .replace(/_/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Make an entity slug feel like a dataset name. */
function prettyEntity(slug: string): string {
  return slug
    .split(/[_-]/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

/** Style `slug`-style identifiers as inline chips so the audit trail
 *  visibly points at the semantic-layer handles (metric slug, entity
 *  slug, filter predicate) it's claiming trace to. */
function renderWithBackticks(text: string): ReactNode {
  if (!text) return null;
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      const inner = part.slice(1, -1);
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 mx-0.5 rounded bg-accent/10 text-accent font-mono text-[13px] border border-accent/20"
        >
          {inner}
        </code>
      );
    }
    return <span key={i}>{part}</span>;
  });
}
