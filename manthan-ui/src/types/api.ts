/** API response types — mirrors backend Pydantic models */

export interface DatasetSummary {
  dataset_id: string;
  name: string;
  source_type: string;
  row_count: number;
  column_count: number;
  status: "bronze" | "silver" | "gold";
  created_at: string;
}

export interface ColumnSchema {
  name: string;
  dtype: string;
  role: "metric" | "dimension" | "temporal" | "identifier" | "auxiliary";
  description: string;
  /** DCD v1.1 — exec-facing label; falls back to name when null. */
  label?: string | null;
  /** DCD v1.1 — aggregate-only handling downstream. */
  pii?: boolean;
  /** DCD v1.1 — alternate phrasings the exec might use for this column. */
  synonyms?: string[];
  aggregation: string | null;
  cardinality: number | null;
  completeness: number | null;
  sample_values: string[];
  stats: {
    min: number | null;
    max: number | null;
    mean: number | null;
    median: number | null;
  } | null;
}

/** DCD v1.1 — governed metric declaration. */
export interface SchemaSummaryMetric {
  slug: string;
  label: string;
  description: string;
  expression: string;
  filter: string | null;
  unit: string | null;
  aggregation_semantics: "additive" | "ratio_unsafe" | "non_additive";
  default_grain: string | null;
  valid_dimensions: string[];
  synonyms: string[];
}

/** DCD v1.1 — pre-materialized rollup exposed by slug. */
export interface SchemaSummaryRollup {
  slug: string;
  physical_table: string;
  grain: string | null;
  dimensions: string[];
}

/** DCD v1.1 — stable wrapper over physical storage. */
export interface SchemaSummaryEntity {
  slug: string;
  name: string;
  description: string;
  physical_table: string;
  rollups: SchemaSummaryRollup[];
  metrics: SchemaSummaryMetric[];
}

export interface SchemaSummaryVerifiedQuery {
  question: string;
  sql: string;
  intent: string;
}

export interface SchemaSummary {
  dataset_id: string;
  name: string;
  description: string;
  row_count: number;
  entity?: SchemaSummaryEntity | null;
  columns: ColumnSchema[];
  summary_tables: string[];
  verified_queries: SchemaSummaryVerifiedQuery[];
}

export interface ClarificationOption {
  label: string;
  value: string;
  aggregation: string | null;
}

export interface ClarificationQuestion {
  question_id: string;
  column_name: string;
  prompt: string;
  options: ClarificationOption[];
  current_role: string;
  recommended: string | null;
}

export interface QuestionResponse {
  id: string;
  session_id: string;
  prompt: string;
  options: string[];
  allow_free_text: boolean;
  context: string | null;
  status: string;
  answer: string | null;
  answered_at: string | null;
  created_at: string;
  timed_out: boolean;
}

export interface MemoryEntry {
  scope_type: string;
  scope_id: string;
  key: string;
  value: unknown;
  category: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanStep {
  id: string;
  tool: string;
  description: string;
  arguments: Record<string, unknown>;
  depends_on: string[];
  status: string;
  result_summary: string | null;
}

export interface Plan {
  id: string;
  session_id: string;
  dataset_id: string | null;
  user_question: string;
  interpretation: string;
  steps: PlanStep[];
  status: string;
  expected_cost: Record<string, number>;
  risks: string[];
  approval_feedback: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentSyncResponse {
  text: string;
  turns: number;
  tool_calls: number;
  elapsed_seconds: number;
  render_spec?: Record<string, unknown>;
}
