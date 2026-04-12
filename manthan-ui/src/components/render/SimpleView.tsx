import type { SimpleRenderSpec } from "@/types/render-spec";
import { KPICard } from "./shared/KPICard";
import { NarrativeBlock } from "./shared/NarrativeBlock";
import { ChartRenderer } from "./charts/ChartRenderer";
import { CitationsFooter } from "./shared/CitationsFooter";

export function SimpleView({ spec }: { spec: SimpleRenderSpec }) {
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <KPICard kpi={spec.headline} size="lg" />
      </div>
      <div className="stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        <NarrativeBlock text={spec.narrative} />
      </div>
      {spec.visuals.map((v, i) => (
        <div key={v.id || i} className="stagger-item" style={{ "--i": i + 2 } as React.CSSProperties}>
          <ChartRenderer visual={v} />
        </div>
      ))}
      {spec.caveats && spec.caveats.length > 0 && (
        <div className="stagger-item text-xs text-warning space-y-1" style={{ "--i": spec.visuals.length + 2 } as React.CSSProperties}>
          {spec.caveats.map((c, i) => (
            <p key={i}>⚠ {c}</p>
          ))}
        </div>
      )}
      <div className="stagger-item" style={{ "--i": spec.visuals.length + 3 } as React.CSSProperties}>
        <CitationsFooter citations={spec.citations} />
      </div>
    </div>
  );
}
