import type { AgentEvent } from "@/types/events";
import {
  TableProperties, Brain, Sparkles,
  CheckCircle2, XCircle, ChevronDown,
  GitFork, GitMerge, AlertTriangle, Loader2,
} from "lucide-react";
import { formatMs } from "@/lib/utils";
import { AskUserCard } from "@/components/hitl/AskUserCard";
import { PlanApprovalCard } from "@/components/hitl/PlanApprovalCard";

const TOOL_LABELS: Record<string, string> = {
  run_sql: "Running SQL query",
  run_python: "Executing Python",
  get_schema: "Loading schema",
  get_context: "Reading data context",
  ask_user: "Asking for input",
  create_plan: "Creating plan",
  save_memory: "Saving to memory",
  recall_memory: "Checking memory",
};

export function ActivityEvent({ event }: { event: AgentEvent }) {
  if (event.type === "done") return null;

  // HITL cards
  if (event.type === "waiting_for_user") {
    return <AskUserCard questionId={event.question_id} prompt={event.prompt} options={event.options} />;
  }
  if (event.type === "plan_created") {
    return <PlanApprovalCard planId={event.plan_id} interpretation={event.interpretation} stepCount={event.steps} />;
  }

  // Turn dividers
  if (event.type === "turn_complete") {
    return (
      <div className="flex items-center gap-3 py-2">
        <div className="h-px flex-1 bg-border" />
        <span className="text-[10px] text-text-faint font-medium">Turn {event.turn}</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    );
  }

  // Tool calls — card treatment
  if (event.type === "tool_start") {
    return (
      <div className="animate-fade-up my-1.5 rounded-xl bg-surface-raised border border-border shadow-xs p-3 flex items-center gap-3 animate-tool-active">
        <div className="w-7 h-7 rounded-lg bg-warning-soft flex items-center justify-center shrink-0">
          <Loader2 size={14} className="text-warning animate-spin-slow" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-medium text-text-primary">
            {TOOL_LABELS[event.tool] ?? event.tool}
          </p>
          <p className="text-[11px] text-text-faint font-mono truncate mt-0.5">
            {event.args_preview.slice(0, 100)}
          </p>
        </div>
      </div>
    );
  }

  if (event.type === "tool_complete") {
    return (
      <div className="animate-fade-up my-1.5 rounded-xl bg-surface-raised border border-border shadow-xs p-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-success-soft flex items-center justify-center shrink-0">
          <CheckCircle2 size={14} className="text-success" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-medium text-text-primary">
            {TOOL_LABELS[event.tool] ?? event.tool}
          </p>
        </div>
        <span className="text-[10px] text-text-faint bg-surface-sunken px-1.5 py-0.5 rounded font-mono">
          {formatMs(event.elapsed_ms)}
        </span>
      </div>
    );
  }

  if (event.type === "tool_error") {
    return (
      <div className="animate-fade-up my-1.5 rounded-xl bg-error-soft border border-error/20 p-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-error/10 flex items-center justify-center shrink-0">
          <XCircle size={14} className="text-error" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-medium text-error">{event.tool} failed</p>
          <p className="text-[11px] text-text-secondary mt-0.5">{event.error.slice(0, 80)}</p>
        </div>
        {event.will_retry && (
          <span className="text-[10px] text-warning font-medium">retrying</span>
        )}
      </div>
    );
  }

  // Thinking — collapsible
  if (event.type === "thinking") {
    return (
      <details className="my-2 animate-fade-up">
        <summary className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer hover:text-text-primary transition-colors select-none">
          <Sparkles size={13} className="text-accent" />
          <span className="font-medium">Thinking</span>
          <ChevronDown size={12} className="text-text-faint ml-auto" />
        </summary>
        <div className="mt-2 pl-5 text-[13px] text-text-secondary leading-relaxed border-l-2 border-accent-soft">
          {event.text.slice(0, 400)}{event.text.length > 400 ? "…" : ""}
        </div>
      </details>
    );
  }

  // Discovery phase — subtle inline
  if (["session_start", "discovering_tables", "loading_schema", "checking_memory"].includes(event.type)) {
    const labels: Record<string, string> = {
      session_start: "Starting analysis",
      discovering_tables: "Scanning tables",
      loading_schema: "Loading schema",
      checking_memory: "Checking memory",
    };
    return (
      <div className="flex items-center gap-2 py-1 animate-fade-up">
        <Loader2 size={12} className="text-text-faint animate-spin-slow" />
        <span className="text-xs text-text-faint">{labels[event.type] ?? event.type}…</span>
      </div>
    );
  }

  if (event.type === "tables_found") {
    return (
      <div className="flex items-center gap-2 py-1 animate-fade-up">
        <TableProperties size={12} className="text-accent" />
        <span className="text-xs text-text-secondary">
          <span className="font-medium">{event.total}</span> tables found
        </span>
      </div>
    );
  }

  if (event.type === "memory_found") {
    return (
      <div className="flex items-center gap-2 py-1 animate-fade-up">
        <Brain size={12} className="text-accent" />
        <span className="text-xs text-text-secondary">
          <span className="font-medium">{event.prior_analyses}</span> prior analyses recalled
        </span>
      </div>
    );
  }

  if (event.type === "plan_approved") {
    return (
      <div className="flex items-center gap-2 py-1.5 animate-fade-up">
        <CheckCircle2 size={13} className="text-success" />
        <span className="text-[13px] text-success font-medium">Plan approved</span>
      </div>
    );
  }

  if (event.type === "subagent_spawned") {
    return (
      <div className="flex items-center gap-2 py-1.5 animate-fade-up">
        <GitFork size={13} className="text-accent" />
        <span className="text-[13px] text-text-secondary">Spawned agent: {event.task.slice(0, 60)}</span>
      </div>
    );
  }

  if (event.type === "subagent_complete") {
    return (
      <div className="flex items-center gap-2 py-1.5 animate-fade-up">
        <GitMerge size={13} className="text-success" />
        <span className="text-[13px] text-text-secondary">Agent finished</span>
      </div>
    );
  }

  if (event.type === "error") {
    return (
      <div className="my-2 rounded-xl bg-error-soft border border-error/20 p-4 animate-fade-up">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle size={14} className="text-error" />
          <span className="text-[13px] font-medium text-error">Error</span>
        </div>
        <p className="text-[13px] text-text-secondary">{event.message}</p>
        {!event.recoverable && (
          <p className="text-[11px] text-text-faint mt-1">Try rephrasing your question</p>
        )}
      </div>
    );
  }

  // Fallback for remaining types
  return null;
}
