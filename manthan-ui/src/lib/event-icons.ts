import type { AgentEventType } from "@/types/events";

interface EventMeta {
  icon: string;
  color: string;
  label: string;
}

export const EVENT_META: Record<AgentEventType, EventMeta> = {
  session_start:      { icon: "Play",           color: "text-accent",           label: "Session started" },
  discovering_tables: { icon: "Search",         color: "text-text-secondary",   label: "Scanning tables" },
  tables_found:       { icon: "TableProperties", color: "text-accent",          label: "Tables found" },
  loading_schema:     { icon: "FileJson",       color: "text-text-secondary",   label: "Loading schema" },
  checking_memory:    { icon: "Brain",          color: "text-text-secondary",   label: "Checking memory" },
  memory_found:       { icon: "Brain",          color: "text-accent",           label: "Memory found" },
  thinking:           { icon: "Sparkles",       color: "text-accent",           label: "Thinking" },
  deciding:           { icon: "GitBranch",      color: "text-text-secondary",   label: "Decision" },
  tool_start:         { icon: "Wrench",         color: "text-warning",          label: "Running tool" },
  tool_complete:      { icon: "CheckCircle",    color: "text-success",          label: "Tool complete" },
  tool_error:         { icon: "XCircle",        color: "text-error",            label: "Tool error" },
  waiting_for_user:   { icon: "MessageCircle",  color: "text-warning",          label: "Needs input" },
  user_answered:      { icon: "CheckCircle",    color: "text-success",          label: "Answered" },
  plan_created:       { icon: "ListChecks",     color: "text-accent",           label: "Plan created" },
  plan_pending:       { icon: "Clock",          color: "text-warning",          label: "Awaiting approval" },
  plan_approved:      { icon: "CheckCircle",    color: "text-success",          label: "Plan approved" },
  progress:           { icon: "Loader",         color: "text-text-secondary",   label: "Progress" },
  turn_complete:      { icon: "ArrowRight",     color: "text-text-tertiary",    label: "Turn complete" },
  subagent_spawned:   { icon: "GitFork",        color: "text-accent",           label: "Agent spawned" },
  subagent_complete:  { icon: "GitMerge",       color: "text-success",          label: "Agent complete" },
  done:               { icon: "CheckCircle2",   color: "text-success",          label: "Done" },
  error:              { icon: "AlertTriangle",  color: "text-error",            label: "Error" },
};
