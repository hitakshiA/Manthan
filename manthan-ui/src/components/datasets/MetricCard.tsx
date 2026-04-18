import { TrendingUp, Info } from "lucide-react";
import type { SchemaSummary } from "@/types/api";
import { cn } from "@/lib/utils";

type Metric = NonNullable<SchemaSummary["entity"]>["metrics"][number];

/**
 * Governed metric card — one per DcdMetric declared on the active entity.
 * The card is the exec-facing face of a business definition: label, unit,
 * aggregation function, baked-in filter, and the synonyms the exec might
 * naturally say. Clicking opens a popover with the full definition.
 */
export function MetricCard({ metric, compact = false }: { metric: Metric; compact?: boolean }) {
  const unitLabel =
    metric.unit === "USD"
      ? "$"
      : metric.unit === "percent"
        ? "%"
        : metric.unit === "count"
          ? "#"
          : null;

  return (
    <div
      className={cn(
        "group relative rounded-xl border border-border bg-surface-raised p-4 transition-all hover:border-border-strong hover:shadow-xs font-body",
        compact && "p-3",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            {unitLabel && (
              <span className="text-[11px] font-mono text-text-faint">
                {unitLabel}
              </span>
            )}
            <h3 className="text-[15px] font-semibold text-text-primary truncate">
              {metric.label}
            </h3>
          </div>
          <p className="text-[11px] text-text-faint font-mono mt-0.5">
            {metric.slug}
          </p>
        </div>
        <span
          className={cn(
            "text-[9px] font-medium px-1.5 py-0.5 rounded-full uppercase tracking-wider shrink-0",
            metric.aggregation_semantics === "ratio_unsafe"
              ? "bg-warning-soft text-warning"
              : metric.aggregation_semantics === "non_additive"
                ? "bg-surface-sunken text-text-faint"
                : "bg-accent-soft text-accent",
          )}
          title={
            metric.aggregation_semantics === "ratio_unsafe"
              ? "Ratio — do not SUM across slices"
              : metric.aggregation_semantics === "non_additive"
                ? "Non-additive"
                : "Additive across slices"
          }
        >
          {metric.aggregation_semantics === "ratio_unsafe"
            ? "Ratio"
            : metric.aggregation_semantics === "non_additive"
              ? "NA"
              : "Additive"}
        </span>
      </div>

      {metric.description && !compact && (
        <p className="text-[12px] text-text-tertiary leading-relaxed mt-2.5 line-clamp-2">
          {metric.description}
        </p>
      )}

      {(metric.filter || metric.default_grain) && (
        <div className="mt-3 space-y-1.5">
          {metric.filter && (
            <div className="flex items-start gap-1.5 text-[11px]">
              <Info size={10} className="text-accent mt-0.5 shrink-0" />
              <code className="font-mono text-text-secondary bg-accent-soft/30 px-1.5 py-0.5 rounded text-[10.5px] break-all">
                WHERE {metric.filter}
              </code>
            </div>
          )}
          {metric.default_grain && (
            <div className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
              <TrendingUp size={10} />
              <span>Default grain: {metric.default_grain}</span>
            </div>
          )}
        </div>
      )}

      {metric.synonyms.length > 0 && !compact && (
        <div className="mt-3 pt-2.5 border-t border-border/60">
          <p className="text-[10px] text-text-faint uppercase tracking-wider mb-1">
            Also called
          </p>
          <div className="flex flex-wrap gap-1">
            {metric.synonyms.slice(0, 4).map((s) => (
              <span
                key={s}
                className="text-[10.5px] text-text-secondary bg-surface-sunken px-1.5 py-0.5 rounded"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
