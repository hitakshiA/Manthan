import type { DashboardSection as SectionType } from "@/types/render-spec";
import { NarrativeBlock } from "../shared/NarrativeBlock";
import { ChartRenderer } from "../charts/ChartRenderer";
import { LayoutGrid } from "../shared/LayoutGrid";
import { DrillDownBar } from "../shared/DrillDownBar";

interface Props {
  section: SectionType;
  index: number;
}

export function DashboardSection({ section, index }: Props) {
  return (
    <section className="space-y-3">
      <div className="flex items-start gap-3">
        <div className="w-0.5 h-6 bg-accent rounded-full mt-0.5 shrink-0" />
        <h3 className="text-base font-semibold text-text-primary leading-snug text-balance">
          {section.title}
        </h3>
      </div>

      <div className="pl-4">
        <NarrativeBlock text={section.narrative} />

        {section.visuals.length > 0 && (
          <LayoutGrid layout={section.layout} className="mt-4">
            {section.visuals.map((v, i) => (
              <ChartRenderer key={v.id || `${index}-${i}`} visual={v} />
            ))}
          </LayoutGrid>
        )}

        <DrillDownBar drillDowns={section.drill_downs} />
      </div>
    </section>
  );
}
