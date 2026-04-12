import type { ExecSummary as ExecSummaryType } from "@/types/render-spec";
import { RecommendationCard } from "./RecommendationCard";

export function ExecSummary({ summary }: { summary: ExecSummaryType }) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-bold text-text-primary leading-snug text-balance">
        {summary.headline}
      </h2>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3">
          Key Findings
        </h3>
        <ul className="space-y-2">
          {summary.key_findings.map((finding, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed">
              <span className="w-5 h-5 rounded-full bg-accent-soft text-accent text-xs font-semibold flex items-center justify-center shrink-0 mt-0.5">
                {i + 1}
              </span>
              {finding}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-3">
          Recommendations
        </h3>
        <div className="space-y-3">
          {summary.recommendations.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} />
          ))}
        </div>
      </div>
    </div>
  );
}
