import type { SimpleRenderSpec } from "@/types/render-spec";
import { KPICard } from "./shared/KPICard";
import { NarrativeBlock } from "./shared/NarrativeBlock";
import { ChartRenderer } from "./charts/ChartRenderer";
import { CitationsFooter } from "./shared/CitationsFooter";

export function SimpleView({ spec }: { spec: SimpleRenderSpec }) {
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <KPICard kpi={spec.headline} size="lg" />
      <NarrativeBlock text={spec.narrative} />
      {spec.visuals.map((v, i) => (
        <ChartRenderer key={v.id || i} visual={v} />
      ))}
      {spec.caveats && spec.caveats.length > 0 && (
        <div className="text-xs text-warning space-y-1">
          {spec.caveats.map((c, i) => (
            <p key={i}>⚠ {c}</p>
          ))}
        </div>
      )}
      <CitationsFooter citations={spec.citations} />
    </div>
  );
}
