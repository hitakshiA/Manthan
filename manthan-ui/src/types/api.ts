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

export interface SchemaSummary {
  dataset_id: string;
  name: string;
  row_count: number;
  columns: ColumnSchema[];
  summary_tables: string[];
  verified_queries: string[];
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
