import type { LayoutType } from "@/types/render-spec";
import { cn } from "@/lib/utils";

const GRID_CLASS: Record<LayoutType, string> = {
  single: "grid-cols-1",
  two_col: "grid-cols-1 md:grid-cols-2",
  three_col: "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
  hero_chart: "grid-cols-1",
  hero_plus_grid: "grid-cols-1",
  kpi_grid: "grid-cols-2 md:grid-cols-4",
  narrative_only: "grid-cols-1",
};

interface Props {
  layout: LayoutType;
  children: React.ReactNode;
  className?: string;
}

export function LayoutGrid({ layout, children, className }: Props) {
  return (
    <div className={cn("grid gap-4", GRID_CLASS[layout] ?? "grid-cols-1", className)}>
      {children}
    </div>
  );
}
