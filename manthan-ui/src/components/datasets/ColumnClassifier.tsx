import { useState } from "react";
import type { ClarificationQuestion } from "@/types/api";
import { submitClarifications } from "@/api/clarification";
import { cn } from "@/lib/utils";
import { HelpCircle, Check } from "lucide-react";

interface Props {
  datasetId: string;
  questions: ClarificationQuestion[];
  onDone: () => void;
}

export function ColumnClassifier({ datasetId, questions, onDone }: Props) {
  const [answers, setAnswers] = useState<Record<string, { role: string; aggregation?: string }>>({});
  const [submitting, setSubmitting] = useState(false);

  const allAnswered = questions.every((q) => answers[q.column_name]);

  const handleSubmit = async () => {
    setSubmitting(true);
    await submitClarifications(
      datasetId,
      questions.map((q) => ({
        question_id: q.question_id,
        column_name: q.column_name,
        chosen_role: answers[q.column_name]?.role ?? q.current_role,
        aggregation: answers[q.column_name]?.aggregation,
      })),
    );
    setSubmitting(false);
    onDone();
  };

  return (
    <div className="px-6 py-5 space-y-5">
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-md bg-warning-soft flex items-center justify-center">
          <HelpCircle size={15} className="text-warning" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text-primary">
            Help us understand your data
          </h3>
          <p className="text-xs text-text-secondary mt-0.5">
            {questions.length} column{questions.length > 1 ? "s" : ""} need clarification before analysis
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {questions.map((q) => {
          const selected = answers[q.column_name]?.role;
          return (
            <div key={q.question_id} className="rounded-lg border border-border bg-surface-1 p-4">
              <p className="text-sm text-text-primary font-medium mb-1">
                <code className="text-accent bg-accent-soft px-1.5 py-0.5 rounded text-xs font-mono">
                  {q.column_name}
                </code>
              </p>
              <p className="text-sm text-text-secondary mb-3">{q.prompt}</p>
              <div className="flex flex-wrap gap-2">
                {q.options.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() =>
                      setAnswers((a) => ({
                        ...a,
                        [q.column_name]: { role: opt.value, aggregation: opt.aggregation ?? undefined },
                      }))
                    }
                    className={cn(
                      "px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150",
                      selected === opt.value
                        ? "bg-accent text-accent-text ring-2 ring-accent/30"
                        : "bg-surface-2 text-text-secondary hover:bg-surface-3",
                      q.recommended === opt.value && selected !== opt.value && "ring-1 ring-accent/20",
                    )}
                  >
                    {opt.label}
                    {q.recommended === opt.value && selected !== opt.value && (
                      <span className="ml-1 text-xs text-text-tertiary">suggested</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!allAnswered || submitting}
        className={cn(
          "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors",
          allAnswered && !submitting
            ? "bg-accent text-accent-text hover:bg-accent-hover"
            : "bg-surface-2 text-text-tertiary cursor-not-allowed",
        )}
      >
        <Check size={15} />
        {submitting ? "Submitting..." : "Confirm and continue"}
      </button>
    </div>
  );
}
