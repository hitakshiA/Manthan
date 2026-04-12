import type { DrillDown } from "@/types/render-spec";
import { ArrowRight } from "lucide-react";

interface Props {
  drillDowns: DrillDown[];
  onDrillDown?: (query: string) => void;
}

export function DrillDownBar({ drillDowns, onDrillDown }: Props) {
  if (drillDowns.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {drillDowns.map((dd, i) => (
        <button
          key={i}
          onClick={() => onDrillDown?.(dd.query_hint)}
          className="flex items-center gap-1.5 text-xs text-accent bg-accent-soft hover:bg-accent/10 px-2.5 py-1.5 rounded-md transition-colors"
        >
          {dd.label}
          <ArrowRight size={11} />
        </button>
      ))}
    </div>
  );
}
