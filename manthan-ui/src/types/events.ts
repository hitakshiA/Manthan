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
  | "error"
  | "sql_result"
  | "narrative"
  | "building_artifact"
  | "artifact_created"
  | "artifact_updated"
  | "repairing_artifact"
  | "inline_visual"
  | "numeric_claim";

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
  /** Analyst's working interpretation — shown prominently in the UI */
  interpretation?: string;
  /** One-sentence "why this matters" — shown below interpretation */
  why?: string;
  /** MAC-taxonomy classification of the ambiguity */
  ambiguity_type?: "intent" | "vague_goal" | "parameter" | "value" | "contextual";
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
}

export interface ErrorEvent {
  type: "error";
  message: string;
  recoverable: boolean;
}

// ── Conversation stream events (new) ──

export interface SqlResultEvent {
  type: "sql_result";
  tool_call_id: string;
  query: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

export interface NarrativeEvent {
  type: "narrative";
  text: string;
}

/** Emitted IMMEDIATELY when the agent calls ``create_artifact`` —
 *  before any validation/repair runs. The UI uses this to open the
 *  artifact panel with a skeleton state so the exec sees progress
 *  during the 30s–3m repair window instead of a silent gap. Followed
 *  by ``artifact_created`` (and optionally ``repairing_artifact`` in
 *  between) once the final HTML is ready. */
export interface BuildingArtifactEvent {
  type: "building_artifact";
  artifact_id: string;
  title: string;
  filename: string;
}

export interface ArtifactCreatedEvent {
  type: "artifact_created";
  artifact_id: string;
  title: string;
  code: string;
  filename: string;
}

export interface ArtifactUpdatedEvent {
  type: "artifact_updated";
  artifact_id: string;
  title: string;
  code: string;
  filename: string;
}

/** Emitted by the backend when a fresh artifact failed JS syntax
 *  validation and a single-shot LLM repair pass is in flight. Followed
 *  by either an ``artifact_created`` with the fixed code, or — if the
 *  repair also fails — the original broken artifact. UI shows a
 *  subtle "Polishing dashboard…" banner until it clears. */
export interface RepairingArtifactEvent {
  type: "repairing_artifact";
  artifact_id: string;
  reason: string;
}

export interface InlineVisualEvent {
  type: "inline_visual";
  visual_id: string;
  visual_type: string;
  html: string;
  height: number;
}

/**
 * A lineage-carrying numeric claim. Paired with every metric value
 * the agent commits to in the narrative, enabling a "How was this
 * calculated?" affordance in the UI.
 */
export interface NumericClaimEvent {
  type: "numeric_claim";
  value: number;
  formatted: string;
  /** All plausible rendered forms of this value (``$706K``, ``$0.7M``,
   *  ``706,532``). The narrative preprocessor matches against any of
   *  these so the click-to-audit underline survives format drift
   *  between the tool output and the agent's prose. */
  formatted_variants?: string[];
  label: string;
  /** Plain-English one-liner of what the number represents. Sourced
   *  from the governed metric's description (compute_metric) or
   *  composed from the SQL (run_sql). Renders in the drawer's
   *  "What this measures" section. */
  description?: string | null;
  entity: string | null;
  metric_ref: string | null;
  filters_applied: string[];
  dimensions: string[];
  grain: string | null;
  sql: string | null;
  row_count_scanned: number | null;
  run_id: string | null;
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
  | ErrorEvent
  | SqlResultEvent
  | NarrativeEvent
  | BuildingArtifactEvent
  | ArtifactCreatedEvent
  | ArtifactUpdatedEvent
  | RepairingArtifactEvent
  | InlineVisualEvent
  | NumericClaimEvent;
