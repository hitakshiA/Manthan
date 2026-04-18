import { Clock, Layers } from "lucide-react";
import type { SchemaSummaryRollup } from "@/types/api";
import { cn } from "@/lib/utils";

/**
 * Pre-materialized rollup chip — one per declared rollup on the
 * active entity. The agent can point `compute_metric` at these to
 * skip a full-table aggregation; surfacing them here tells the exec
 * "the expensive math is already done for this slice."
 *
 * Exec-facing labels are derived from the dimension/grain — raw slug
 * names (``airport_code``, ``by_customer_segment``) are never shown.
 */

const GRAIN_LABEL: Record<string, string> = {
  day: "Daily",
  daily: "Daily",
  week: "Weekly",
  weekly: "Weekly",
  month: "Monthly",
  monthly: "Monthly",
  quarter: "Quarterly",
  quarterly: "Quarterly",
  year: "Yearly",
  yearly: "Yearly",
};

function humanizeDimension(dim: string): string {
  // Strip FK-style suffixes (_code/_id/_key/_sku/_number) so
  // ``airport_code`` reads as "airport", then humanize underscores.
  const stripped = dim.replace(/_(code|id|key|sku|number)$/i, "");
  return stripped.replace(/_/g, " ").toLowerCase().trim() || dim;
}

export function RollupChip({
  rollup,
  compact = false,
}: {
  rollup: SchemaSummaryRollup;
  compact?: boolean;
}) {
  const hasGrain = !!rollup.grain;
  const hasDims = rollup.dimensions.length > 0;

  // Primary label — grains get a named cadence, dimensional rollups
  // read as "By <thing>". Single-dim and multi-dim both collapse
  // cleanly so the chip never shows the raw slug.
  let primary: string;
  if (hasGrain) {
    primary = GRAIN_LABEL[rollup.grain!.toLowerCase()] ?? rollup.grain!;
  } else if (hasDims) {
    const labels = rollup.dimensions.map(humanizeDimension);
    primary =
      labels.length === 1
        ? `By ${labels[0]}`
        : `By ${labels.slice(0, 2).join(" × ")}${labels.length > 2 ? ` +${labels.length - 2}` : ""}`;
  } else {
    primary = rollup.slug.replace(/_/g, " ");
  }

  // Secondary — grain rollups optionally annotate with dim breakdown.
  // Dim-only rollups already expressed everything in primary.
  const secondary =
    hasGrain && hasDims
      ? `by ${rollup.dimensions.map(humanizeDimension).slice(0, 2).join(" × ")}`
      : null;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border bg-surface-raised px-3 py-1.5 font-body transition-colors hover:border-border-strong",
        compact && "px-2.5 py-1",
      )}
      title={`Pre-materialized rollup · physical: ${rollup.physical_table}`}
    >
      {hasGrain ? (
        <Clock size={11} className="text-accent shrink-0" />
      ) : (
        <Layers size={11} className="text-accent shrink-0" />
      )}
      <span className="text-[12px] font-semibold text-text-primary capitalize">
        {primary}
      </span>
      {secondary && (
        <span className="text-[11px] text-text-tertiary">{secondary}</span>
      )}
    </div>
  );
}
