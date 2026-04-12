import type { KPICard as KPICardType } from "@/types/render-spec";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  kpi: KPICardType;
  size?: "sm" | "lg";
}

export function KPICard({ kpi, size = "sm" }: Props) {
  const sentimentColor =
    kpi.sentiment === "positive"
      ? "text-success"
      : kpi.sentiment === "negative"
        ? "text-error"
        : "text-text-tertiary";

  const SentimentIcon =
    kpi.sentiment === "positive"
      ? TrendingUp
      : kpi.sentiment === "negative"
        ? TrendingDown
        : Minus;

  return (
    <div
      className={cn(
        "flex flex-col gap-1 py-3 px-4 rounded-lg bg-surface-1 border border-border",
        "transition-all duration-200",
        "hover:border-border-strong hover:shadow-[0_1px_3px_0_oklch(18%_0.01_65_/_0.04)]",
      )}
    >
      <p
        className={cn(
          "font-bold text-text-primary tabular-nums tracking-tight",
          size === "lg" ? "text-3xl" : "text-xl",
        )}
      >
        {kpi.value}
      </p>
      <p className="text-xs text-text-secondary leading-snug">{kpi.label}</p>
      {kpi.delta && (
        <div className={cn("flex items-center gap-1 text-xs font-medium mt-0.5", sentimentColor)}>
          <SentimentIcon size={12} aria-hidden="true" />
          <span>{kpi.delta}</span>
        </div>
      )}
    </div>
  );
}
