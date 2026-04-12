import type { ModerateRenderSpec } from "@/types/render-spec";
import { KPIRow } from "./shared/KPIRow";
import { CitationsFooter } from "./shared/CitationsFooter";
import { DashboardSection } from "./moderate/DashboardSection";

export function ModerateView({ spec }: { spec: ModerateRenderSpec }) {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <h2 className="text-xl font-bold text-text-primary text-balance">
          {spec.title}
        </h2>
        {spec.subtitle && (
          <p className="text-sm text-text-secondary mt-1">{spec.subtitle}</p>
        )}
      </div>

      <div className="stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        <KPIRow cards={spec.kpi_row} />
      </div>

      <div className="space-y-8">
        {spec.sections.map((section, i) => (
          <div key={section.id || i} className="stagger-item" style={{ "--i": i + 2 } as React.CSSProperties}>
            <DashboardSection section={section} index={i} />
          </div>
        ))}
      </div>

      {spec.caveats && spec.caveats.length > 0 && (
        <div className="text-xs text-warning space-y-1 mt-4">
          {spec.caveats.map((c, i) => (
            <p key={i}>⚠ {c}</p>
          ))}
        </div>
      )}

      <CitationsFooter citations={spec.citations} />

      {spec.plan_id && (
        <p className="text-xs text-text-tertiary">
          Plan: <code className="font-mono text-accent">{spec.plan_id}</code>
        </p>
      )}
    </div>
  );
}
