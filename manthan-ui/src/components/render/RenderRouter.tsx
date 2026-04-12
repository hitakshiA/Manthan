import type { RenderSpec } from "@/types/render-spec";
import { SimpleView } from "./SimpleView";
import { ModerateView } from "./ModerateView";
import { ComplexView } from "./ComplexView";

interface Props {
  spec: RenderSpec;
}

export function RenderRouter({ spec }: Props) {
  switch (spec.mode) {
    case "simple":
      return <SimpleView spec={spec} />;
    case "moderate":
      return <ModerateView spec={spec} />;
    case "complex":
      return <ComplexView spec={spec} />;
    default:
      return (
        <div className="text-sm text-text-tertiary p-4">
          Unknown render mode: {(spec as { mode: string }).mode}
        </div>
      );
  }
}
