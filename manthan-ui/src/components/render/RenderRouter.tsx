import { lazy, Suspense } from "react";
import type { RenderSpec } from "@/types/render-spec";

const SimpleView = lazy(() =>
  import("./SimpleView").then((m) => ({ default: m.SimpleView })),
);
const ModerateView = lazy(() =>
  import("./ModerateView").then((m) => ({ default: m.ModerateView })),
);
const ComplexView = lazy(() =>
  import("./ComplexView").then((m) => ({ default: m.ComplexView })),
);

function LoadingFallback() {
  return (
    <div className="space-y-4 py-4">
      <div className="h-20 rounded-lg animate-shimmer" />
      <div className="h-4 w-3/4 rounded animate-shimmer" />
      <div className="h-64 rounded-lg animate-shimmer" />
    </div>
  );
}

export function RenderRouter({ spec }: { spec: RenderSpec }) {
  // Normalize mode to lowercase — agent may return "SIMPLE", "MODERATE", "COMPLEX"
  const mode = (spec.mode as string).toLowerCase();

  return (
    <Suspense fallback={<LoadingFallback />}>
      {mode === "simple" && <SimpleView spec={{ ...spec, mode: "simple" }} />}
      {mode === "moderate" && <ModerateView spec={{ ...spec, mode: "moderate" } as RenderSpec & { mode: "moderate" }} />}
      {mode === "complex" && <ComplexView spec={{ ...spec, mode: "complex" } as RenderSpec & { mode: "complex" }} />}
      {!["simple", "moderate", "complex"].includes(mode) && (
        <div className="text-sm text-text-tertiary p-4">
          Unknown render mode: {spec.mode}
        </div>
      )}
    </Suspense>
  );
}
