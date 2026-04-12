import type { Appendix } from "@/types/render-spec";
import { AlertTriangle, HelpCircle } from "lucide-react";

export function AppendixPage({ appendix }: { appendix: Appendix }) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-bold text-text-primary">Appendix</h2>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
          Methodology
        </h3>
        <p className="text-sm text-text-secondary leading-relaxed">{appendix.methodology}</p>
      </div>

      {appendix.data_quality_notes.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
            Data Quality Notes
          </h3>
          <ul className="space-y-1.5">
            {appendix.data_quality_notes.map((note, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <AlertTriangle size={13} className="text-warning mt-0.5 shrink-0" />
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      {appendix.open_questions.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
            Open Questions
          </h3>
          <ul className="space-y-1.5">
            {appendix.open_questions.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <HelpCircle size={13} className="text-accent mt-0.5 shrink-0" />
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
