import { useState } from "react";
import { MessageCircle, Check, Send } from "lucide-react";
import { answerQuestion } from "@/api/ask-user";
import { cn } from "@/lib/utils";

interface Props {
  questionId: string;
  prompt: string;
  options: string[];
  onAnswered?: () => void;
}

export function AskUserCard({ questionId, prompt, options, onAnswered }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [freeText, setFreeText] = useState("");
  const [answered, setAnswered] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (answer: string) => {
    setSubmitting(true);
    await answerQuestion(questionId, answer);
    setAnswered(true);
    setSubmitting(false);
    onAnswered?.();
  };

  if (answered) {
    return (
      <div className="flex items-center gap-2 py-2 text-sm text-success">
        <Check size={14} />
        <span>Answered: <span className="font-medium text-text-primary">{selected || freeText}</span></span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border-l-3 border-l-warning border border-border bg-surface-1 p-4 my-2 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-warning">
        <MessageCircle size={15} />
        Agent needs your input
      </div>
      <p className="text-sm text-text-primary">{prompt}</p>

      {options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => {
                setSelected(opt);
                submit(opt);
              }}
              disabled={submitting}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium border transition-all duration-150",
                selected === opt
                  ? "bg-accent text-accent-text border-accent"
                  : "bg-surface-0 text-text-secondary border-border hover:border-accent/40 hover:bg-surface-2",
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && freeText.trim()) submit(freeText.trim());
          }}
          placeholder="Or type your answer..."
          className="flex-1 bg-surface-0 border border-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent"
          disabled={submitting}
        />
        <button
          onClick={() => freeText.trim() && submit(freeText.trim())}
          disabled={!freeText.trim() || submitting}
          className={cn(
            "w-8 h-8 flex items-center justify-center rounded-md transition-colors",
            freeText.trim() ? "bg-accent text-accent-text" : "text-text-tertiary",
          )}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
