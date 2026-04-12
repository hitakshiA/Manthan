/** SSE event types emitted by POST /agent/query — mirrors src/agent/events.py */

export type AgentEventType =
  | "session_start"
  | "discovering_tables"
  | "tables_found"
  | "loading_schema"
  | "checking_memory"
  | "memory_found"
  | "thinking"
  | "deciding"
  | "tool_start"
  | "tool_complete"
  | "tool_error"
  | "waiting_for_user"
  | "user_answered"
  | "plan_created"
  | "plan_pending"
  | "plan_approved"
  | "progress"
  | "turn_complete"
  | "subagent_spawned"
  | "subagent_complete"
  | "done"
  | "error";

export interface SessionStartEvent {
  type: "session_start";
  session_id: string;
  dataset_id: string;
  model: string;
}

export interface DiscoveringTablesEvent {
  type: "discovering_tables";
  dataset_id: string;
  status: string;
}

export interface TablesFoundEvent {
  type: "tables_found";
  tables: string[];
  total: number;
}

export interface LoadingSchemaEvent {
  type: "loading_schema";
  dataset_id: string;
}

export interface CheckingMemoryEvent {
  type: "checking_memory";
  dataset_id: string;
}

export interface MemoryFoundEvent {
  type: "memory_found";
  prior_analyses: number;
}

export interface ThinkingEvent {
  type: "thinking";
  text: string;
}

export interface DecidingEvent {
  type: "deciding";
  gate: string;
  decision: string;
  reason: string;
}

export interface ToolStartEvent {
  type: "tool_start";
  tool: string;
  turn: number;
  args_preview: string;
}

export interface ToolCompleteEvent {
  type: "tool_complete";
  tool: string;
  preview: string;
  elapsed_ms: number;
}

export interface ToolErrorEvent {
  type: "tool_error";
  tool: string;
  error: string;
  will_retry: boolean;
}

export interface WaitingForUserEvent {
  type: "waiting_for_user";
  question_id: string;
  prompt: string;
  options: string[];
}

export interface UserAnsweredEvent {
  type: "user_answered";
  answer: string;
}

export interface PlanCreatedEvent {
  type: "plan_created";
  plan_id: string;
  interpretation: string;
  steps: number;
}

export interface PlanPendingEvent {
  type: "plan_pending";
  plan_id: string;
  interpretation: string;
}

export interface PlanApprovedEvent {
  type: "plan_approved";
  plan_id: string;
}

export interface ProgressEvent {
  type: "progress";
  step: number;
  total: number;
  description: string;
}

export interface TurnCompleteEvent {
  type: "turn_complete";
  turn: number;
  tools_used: string[];
}

export interface SubagentSpawnedEvent {
  type: "subagent_spawned";
  subagent_id: string;
  task: string;
}

export interface SubagentCompleteEvent {
  type: "subagent_complete";
  subagent_id: string;
  result: string;
}

export interface DoneEvent {
  type: "done";
  summary: string;
  turns: number;
  tool_calls: number;
  elapsed_seconds: number;
  mode: string | null;
  render_spec: Record<string, unknown> | null;
}

export interface ErrorEvent {
  type: "error";
  message: string;
  recoverable: boolean;
}

export type AgentEvent =
  | SessionStartEvent
  | DiscoveringTablesEvent
  | TablesFoundEvent
  | LoadingSchemaEvent
  | CheckingMemoryEvent
  | MemoryFoundEvent
  | ThinkingEvent
  | DecidingEvent
  | ToolStartEvent
  | ToolCompleteEvent
  | ToolErrorEvent
  | WaitingForUserEvent
  | UserAnsweredEvent
  | PlanCreatedEvent
  | PlanPendingEvent
  | PlanApprovedEvent
  | ProgressEvent
  | TurnCompleteEvent
  | SubagentSpawnedEvent
  | SubagentCompleteEvent
  | DoneEvent
  | ErrorEvent;
