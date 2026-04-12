import type { ReportBlock } from "@/types/render-spec";
import { KPIRow } from "../shared/KPIRow";
import { ChartRenderer } from "../charts/ChartRenderer";
import { NarrativeBlock } from "../shared/NarrativeBlock";
import { LayoutGrid } from "../shared/LayoutGrid";
import { cn } from "@/lib/utils";

export function BlockRenderer({ block }: { block: ReportBlock }) {
  switch (block.type) {
    case "kpi_row":
      return block.items ? <KPIRow cards={block.items} /> : null;

    case "hero_chart":
      return block.visual ? <ChartRenderer visual={block.visual} /> : null;

    case "chart_grid":
      return block.visuals ? (
        <LayoutGrid layout={block.cols === 3 ? "three_col" : block.cols === 1 ? "single" : "two_col"}>
          {block.visuals.map((v, i) => (
            <ChartRenderer key={v.id || i} visual={v} />
          ))}
        </LayoutGrid>
      ) : null;

    case "table":
      return (
        <div className="overflow-x-auto">
          {block.title && <h4 className="text-sm font-medium text-text-primary mb-2">{block.title}</h4>}
          <table className="w-full text-sm">
            {block.columns && (
              <thead>
                <tr>
                  {block.columns.map((col) => (
                    <th key={col} className="text-left text-xs font-medium text-text-secondary border-b border-border pb-2 pr-4">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
          </table>
        </div>
      );

    case "narrative":
      return block.text ? <NarrativeBlock text={block.text} /> : null;

    case "callout":
      return (
        <div
          className={cn(
            "rounded-lg border p-4 text-sm leading-relaxed",
            block.style === "warning" && "border-warning bg-warning-soft text-warning",
            block.style === "insight" && "border-accent bg-accent-soft text-accent",
            block.style === "action" && "border-success bg-success-soft text-success",
            !block.style && "border-accent bg-accent-soft text-text-secondary",
          )}
        >
          {block.text}
        </div>
      );

    case "comparison":
      return (
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 rounded-lg bg-surface-1 border border-border">
            <p className="text-sm text-text-secondary">{JSON.stringify(block.left)}</p>
          </div>
          <div className="p-4 rounded-lg bg-surface-1 border border-border">
            <p className="text-sm text-text-secondary">{JSON.stringify(block.right)}</p>
          </div>
        </div>
      );

    default:
      return null;
  }
}
