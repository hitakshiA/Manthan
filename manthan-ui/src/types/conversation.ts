/** Conversation stream block types — the building blocks of the chat UI */

// ── Individual block types ──

export interface UserMessageBlock {
  type: "user_message";
  text: string;
  timestamp: number;
}

export interface ThinkingStep {
  kind: "reasoning" | "tool_call" | "tool_result";
  tool?: string;
  text: string;
  badge?: "Script" | "SQL" | "Read" | "Search" | "Memory" | "Plan" | "Ask";
  elapsed_ms?: number;
  success?: boolean;
  code?: string;     // SQL query or Python code (shown as code block)
  output?: string;   // tool output preview (collapsible)
  /** Exec-speak label derived from the reasoning narration that
   * preceded this tool call — e.g. "Pulled Q3 orders by region"
   * instead of "Running SQL query". Takes precedence over TOOL_LABELS. */
  display_label?: string;
  /** Tabular SQL result — rendered inside the expanded thinking group
   * only (never as a top-level block). Execs don't need schema dumps,
   * table-name lists, or single-value pulls surfaced in the main flow;
   * the narrative + emit_visual are the exec-facing surfaces. */
  table?: {
    columns: string[];
    rows: unknown[][];
    row_count: number;
    truncated: boolean;
    query: string;
    elapsed_ms: number;
  };
}

export interface ThinkingGroupBlock {
  type: "thinking_group";
  summary: string;
  steps: ThinkingStep[];
  duration_ms: number;
}

export interface NarrativeBlock {
  type: "narrative";
  text: string; // markdown
}

export interface SqlResultBlock {
  type: "sql_result";
  tool_call_id: string;
  query: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

export interface AskUserBlock {
  type: "ask_user";
  question_id: string;
  prompt: string;
  options: string[];
  /** Analyst's working interpretation — rendered prominently */
  interpretation?: string;
  /** Why this clarification matters — what flips downstream */
  why?: string;
  /** MAC-taxonomy classification of the ambiguity */
  ambiguity_type?: "intent" | "vague_goal" | "parameter" | "value" | "contextual";
  answered?: boolean;
  answer?: string;
}

export interface ArtifactCardBlock {
  type: "artifact_card";
  artifact_id: string;
  title: string;
  filename: string;
}

export interface DoneBlock {
  type: "done";
  summary: string;
  turns: number;
  tool_calls: number;
  elapsed_seconds: number;
}

export interface InlineVisualBlock {
  type: "inline_visual";
  visual_id: string;
  visual_type: string;
  html: string;
  height: number;
}

export interface ErrorBlock {
  type: "error";
  message: string;
  recoverable: boolean;
}

export interface FollowUpChipsBlock {
  type: "followup_chips";
  /** 3 exec-voice next-question suggestions; tapping fires the next query */
  chips: string[];
}

/**
 * A numeric claim the agent has attached lineage to. The UI inlines
 * the ``formatted`` value into the last narrative block and wraps it
 * with a click-to-open drawer showing the metric YAML + SQL + filters.
 */
export interface NumericClaim {
  value: number;
  formatted: string;
  /** Alternate renderings of the same value for fuzzy matching. */
  formatted_variants: string[];
  label: string;
  /** Plain-English one-liner of what the number represents. */
  description: string | null;
  entity: string | null;
  metric_ref: string | null;
  filters_applied: string[];
  dimensions: string[];
  grain: string | null;
  sql: string | null;
  row_count_scanned: number | null;
  run_id: string | null;
}

// ── Union type ──

export type ConversationBlock =
  | UserMessageBlock
  | ThinkingGroupBlock
  | NarrativeBlock
  | SqlResultBlock
  | AskUserBlock
  | ArtifactCardBlock
  | InlineVisualBlock
  | DoneBlock
  | ErrorBlock
  | FollowUpChipsBlock;

// ── Artifact state ──

export interface ArtifactState {
  id: string;
  title: string;
  code: string; // full HTML
  filename: string;
  versions: { code: string; timestamp: number }[];
}

// ── Tool name → badge mapping ──

export const TOOL_BADGES: Record<string, ThinkingStep["badge"]> = {
  run_sql: "SQL",
  run_python: "Script",
  get_schema: "Read",
  get_context: "Read",
  ask_user: "Ask",
  create_plan: "Plan",
  save_memory: "Memory",
  recall_memory: "Memory",
  create_artifact: "Script",
  emit_visual: "Script",
};

export const TOOL_LABELS: Record<string, string> = {
  run_sql: "Pulling the data",
  run_python: "Running the analysis",
  get_schema: "Checking what's in the dataset",
  get_context: "Reading the context",
  ask_user: "Checking with you",
  create_plan: "Laying out the plan",
  save_memory: "Noting this for later",
  recall_memory: "Remembering prior findings",
  create_artifact: "Writing it up",
  emit_visual: "Showing a quick view",
};
