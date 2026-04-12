import type { AgentEvent } from "@/types/events";
import {
  Play, Search, TableProperties, FileJson, Brain, Sparkles,
  GitBranch, Wrench, CheckCircle, XCircle, MessageCircle,
  ListChecks, ArrowRight, GitFork, GitMerge,
  AlertTriangle, Loader, Database,
} from "lucide-react";
import { cn, formatMs } from "@/lib/utils";

const TOOL_ICONS: Record<string, string> = {
  run_sql: "SQL",
  run_python: "PY",
  get_schema: "SCH",
  get_context: "DCD",
  ask_user: "ASK",
  create_plan: "PLAN",
  save_memory: "MEM",
  recall_memory: "RCL",
};

function EventIcon({ type }: { type: string }) {
  const size = 14;
  const sw = 1.8;
  switch (type) {
    case "session_start": return <Play size={size} strokeWidth={sw} />;
    case "discovering_tables": return <Search size={size} strokeWidth={sw} />;
    case "tables_found": return <TableProperties size={size} strokeWidth={sw} />;
    case "loading_schema": return <FileJson size={size} strokeWidth={sw} />;
    case "checking_memory": case "memory_found": return <Brain size={size} strokeWidth={sw} />;
    case "thinking": return <Sparkles size={size} strokeWidth={sw} />;
    case "deciding": return <GitBranch size={size} strokeWidth={sw} />;
    case "tool_start": return <Wrench size={size} strokeWidth={sw} />;
    case "tool_complete": return <CheckCircle size={size} strokeWidth={sw} />;
    case "tool_error": return <XCircle size={size} strokeWidth={sw} />;
    case "waiting_for_user": return <MessageCircle size={size} strokeWidth={sw} />;
    case "user_answered": return <CheckCircle size={size} strokeWidth={sw} />;
    case "plan_created": case "plan_pending": return <ListChecks size={size} strokeWidth={sw} />;
    case "plan_approved": return <CheckCircle size={size} strokeWidth={sw} />;
    case "progress": return <Loader size={size} strokeWidth={sw} />;
    case "turn_complete": return <ArrowRight size={size} strokeWidth={sw} />;
    case "subagent_spawned": return <GitFork size={size} strokeWidth={sw} />;
    case "subagent_complete": return <GitMerge size={size} strokeWidth={sw} />;
    case "error": return <AlertTriangle size={size} strokeWidth={sw} />;
    default: return <Database size={size} strokeWidth={sw} />;
  }
}

function eventColor(type: string): string {
  if (type === "tool_error" || type === "error") return "text-error";
  if (type === "tool_complete" || type === "plan_approved" || type === "user_answered" || type === "subagent_complete") return "text-success";
  if (type === "tool_start" || type === "waiting_for_user" || type === "plan_pending") return "text-warning";
  if (type === "thinking" || type === "plan_created" || type === "subagent_spawned" || type === "tables_found" || type === "session_start") return "text-accent";
  return "text-text-tertiary";
}

export function ActivityEvent({ event }: { event: AgentEvent }) {
  // Skip done events — the RenderRouter handles those
  if (event.type === "done") return null;

  // Turn dividers are subtle
  if (event.type === "turn_complete") {
    return (
      <div className="flex items-center gap-3 py-1 text-xs text-text-tertiary">
        <div className="h-px flex-1 bg-border" />
        <span>Turn {event.turn}</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 py-1.5 text-sm animate-in fade-in slide-in-from-left-2 duration-200",
        event.type === "tool_start" && "font-medium",
      )}
    >
      <span className={cn("mt-0.5 shrink-0", eventColor(event.type))}>
        <EventIcon type={event.type} />
      </span>
      <div className="flex-1 min-w-0">
        <EventContent event={event} />
      </div>
    </div>
  );
}

function EventContent({ event }: { event: AgentEvent }) {
  switch (event.type) {
    case "session_start":
      return <span className="text-text-secondary">Starting analysis with <span className="text-accent font-medium">{event.model}</span></span>;
    case "discovering_tables":
      return <span className="text-text-secondary">Scanning available tables...</span>;
    case "tables_found":
      return <span className="text-text-secondary"><span className="font-medium text-text-primary">{event.total}</span> tables found</span>;
    case "loading_schema":
      return <span className="text-text-secondary">Loading schema...</span>;
    case "checking_memory":
      return <span className="text-text-secondary">Checking prior analyses...</span>;
    case "memory_found":
      return <span className="text-text-secondary"><span className="font-medium text-text-primary">{event.prior_analyses}</span> prior analyses found</span>;
    case "thinking":
      return <span className="text-text-secondary italic">{event.text.slice(0, 200)}{event.text.length > 200 ? "..." : ""}</span>;
    case "deciding":
      return <span className="text-text-secondary">{event.gate}: <span className="font-medium text-text-primary">{event.decision}</span></span>;
    case "tool_start":
      return (
        <span className="text-text-primary">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-warning-soft text-warning text-xs font-mono font-semibold mr-1.5">
            {TOOL_ICONS[event.tool] ?? event.tool}
          </span>
          <span className="text-text-secondary text-xs font-mono truncate">{event.args_preview.slice(0, 80)}</span>
        </span>
      );
    case "tool_complete":
      return (
        <span className="text-text-secondary">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-success-soft text-success text-xs font-mono font-semibold mr-1.5">
            {TOOL_ICONS[event.tool] ?? event.tool}
          </span>
          <span className="text-xs text-text-tertiary">{formatMs(event.elapsed_ms)}</span>
        </span>
      );
    case "tool_error":
      return (
        <span className="text-error">
          {event.tool} failed: {event.error.slice(0, 100)}
          {event.will_retry && <span className="text-xs text-warning ml-2">retrying</span>}
        </span>
      );
    case "waiting_for_user":
      return <span className="text-warning font-medium">Needs your input: {event.prompt}</span>;
    case "user_answered":
      return <span className="text-text-secondary">Answered: <span className="font-medium text-text-primary">{event.answer}</span></span>;
    case "plan_created":
      return <span className="text-accent font-medium">Plan created ({event.steps} steps): {event.interpretation.slice(0, 100)}</span>;
    case "plan_pending":
      return <span className="text-warning">Awaiting approval...</span>;
    case "plan_approved":
      return <span className="text-success font-medium">Plan approved</span>;
    case "progress":
      return (
        <span className="text-text-secondary">
          Step {event.step}/{event.total}: {event.description}
        </span>
      );
    case "subagent_spawned":
      return <span className="text-accent">Spawned agent: {event.task.slice(0, 80)}</span>;
    case "subagent_complete":
      return <span className="text-success">Agent complete: {event.result.slice(0, 80)}</span>;
    case "error":
      return <span className="text-error font-medium">{event.message}</span>;
    default:
      return null;
  }
}
