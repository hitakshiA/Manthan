import { useState } from "react";
import { ListChecks, Check, X, ChevronDown } from "lucide-react";
import { approvePlan, rejectPlan } from "@/api/plans";
import { cn } from "@/lib/utils";

interface Props {
  planId: string;
  interpretation: string;
  stepCount: number;
  onDecided?: () => void;
}

export function PlanApprovalCard({ planId, interpretation, stepCount, onDecided }: Props) {
  const [decided, setDecided] = useState<"approved" | "rejected" | null>(null);
  const [showReject, setShowReject] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleApprove = async () => {
    setSubmitting(true);
    await approvePlan(planId);
    setDecided("approved");
    setSubmitting(false);
    onDecided?.();
  };

  const handleReject = async () => {
    setSubmitting(true);
    await rejectPlan(planId, feedback || undefined);
    setDecided("rejected");
    setSubmitting(false);
    onDecided?.();
  };

  if (decided) {
    return (
      <div className={cn(
        "flex items-center gap-2 py-2 text-sm",
        decided === "approved" ? "text-success" : "text-error",
      )}>
        {decided === "approved" ? <Check size={14} /> : <X size={14} />}
        <span className="font-medium">
          Plan {decided}
          {decided === "rejected" && feedback && (
            <span className="font-normal text-text-secondary"> — {feedback}</span>
          )}
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border-l-3 border-l-accent border border-border bg-surface-1 p-4 my-2 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-accent">
        <ListChecks size={15} />
        Review analysis plan
      </div>

      <p className="text-sm text-text-primary leading-relaxed">{interpretation}</p>

      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
      >
        <ChevronDown size={12} className={cn("transition-transform", expanded && "rotate-180")} />
        {stepCount} steps planned
      </button>

      {!showReject ? (
        <div className="flex items-center gap-2">
          <button
            onClick={handleApprove}
            disabled={submitting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-success text-white hover:opacity-90 transition-opacity"
          >
            <Check size={14} />
            Approve
          </button>
          <button
            onClick={() => setShowReject(true)}
            disabled={submitting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-surface-2 text-text-secondary hover:bg-surface-3 transition-colors"
          >
            <X size={14} />
            Reject
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Why? (optional)"
            className="flex-1 bg-surface-0 border border-border rounded-md px-3 py-1.5 text-sm outline-none focus:border-error"
            onKeyDown={(e) => e.key === "Enter" && handleReject()}
          />
          <button
            onClick={handleReject}
            disabled={submitting}
            className="px-3 py-1.5 rounded-md text-sm font-medium bg-error text-white hover:opacity-90"
          >
            Reject
          </button>
          <button
            onClick={() => setShowReject(false)}
            className="px-3 py-1.5 rounded-md text-sm text-text-tertiary hover:bg-surface-2"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
