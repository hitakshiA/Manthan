import type { Recommendation } from "@/types/render-spec";
import { cn } from "@/lib/utils";

const CONFIDENCE_STYLES = {
  high: "bg-success-soft text-success",
  medium: "bg-warning-soft text-warning",
  low: "bg-error-soft text-error",
};

export function RecommendationCard({ rec }: { rec: Recommendation }) {
  return (
    <div className="rounded-lg border border-border bg-surface-1 p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-text-primary leading-snug flex-1">
          {rec.action}
        </h4>
        <span
          className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider shrink-0",
            CONFIDENCE_STYLES[rec.confidence],
          )}
        >
          {rec.confidence}
        </span>
      </div>
      <p className="text-sm text-text-secondary leading-relaxed">{rec.rationale}</p>
      <p className="text-xs text-text-tertiary">
        Impact: <span className="text-text-secondary">{rec.expected_impact}</span>
      </p>
    </div>
  );
}
