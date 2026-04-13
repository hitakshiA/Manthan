import type { Appendix } from "@/types/render-spec";
import { AlertTriangle, HelpCircle } from "lucide-react";

export function AppendixPage({ appendix }: { appendix: Appendix }) {
  const methodology = appendix?.methodology ?? "SQL-based analysis on the full dataset.";
  const notes = appendix?.data_quality_notes ?? [];
  const questions = appendix?.open_questions ?? [];

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-bold text-text-primary">Appendix</h2>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
          Methodology
        </h3>
        <p className="text-sm text-text-secondary leading-relaxed">{String(methodology)}</p>
      </div>

      {notes.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
            Data Quality Notes
          </h3>
          <ul className="space-y-1.5">
            {notes.map((note, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <AlertTriangle size={13} className="text-warning mt-0.5 shrink-0" />
                {String(note)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {questions.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2">
            Open Questions
          </h3>
          <ul className="space-y-1.5">
            {questions.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <HelpCircle size={13} className="text-accent mt-0.5 shrink-0" />
                {String(q)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
