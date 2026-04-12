/** Render spec types — mirrors src/semantic/render_spec.py */

export type VisualType =
  | "histogram" | "bar" | "line" | "area" | "scatter" | "bubble"
  | "heatmap" | "funnel" | "sankey" | "treemap" | "pie" | "box"
  | "violin" | "kpi";

export type LayoutType =
  | "single" | "two_col" | "three_col" | "hero_chart"
  | "hero_plus_grid" | "kpi_grid" | "narrative_only";

export type Sentiment = "positive" | "negative" | "neutral";
export type Confidence = "low" | "medium" | "high";
export type RenderMode = "simple" | "moderate" | "complex";

export type BlockType =
  | "kpi_row" | "hero_chart" | "chart_grid" | "table"
  | "narrative" | "callout" | "comparison";

export interface Visual {
  id: string;
  type: VisualType;
  title: string;
  data_ref?: string;
  encoding: Record<string, unknown>;
  caption?: string;
  annotations?: Array<Record<string, unknown>>;
}

export interface KPICard {
  value: string;
  label: string;
  delta?: string;
  sentiment: Sentiment;
}

export interface Citation {
  kind: string;
  identifier: string;
  reason: string;
}

export interface DrillDown {
  label: string;
  query_hint: string;
}

// ── Simple mode ──

export interface SimpleRenderSpec {
  mode: "simple";
  headline: KPICard;
  narrative: string;
  visuals: Visual[];
  citations: Citation[];
  caveats?: string[];
}

// ── Moderate mode ──

export interface DashboardSection {
  id?: string;
  title: string;
  narrative: string;
  layout: LayoutType;
  visuals: Visual[];
  drill_downs: DrillDown[];
}

export interface ModerateRenderSpec {
  mode: "moderate";
  title: string;
  subtitle?: string;
  kpi_row: KPICard[];
  sections: DashboardSection[];
  citations: Citation[];
  caveats?: string[];
  plan_id?: string;
  subagent_ids?: string[];
}

// ── Complex mode ──

export interface Recommendation {
  id: string;
  action: string;
  rationale: string;
  expected_impact: string;
  evidence_page?: string;
  confidence: Confidence;
}

export interface ExecSummary {
  headline: string;
  key_findings: string[];
  recommendations: Recommendation[];
}

export interface ReportBlock {
  type: BlockType;
  items?: KPICard[];
  visual?: Visual;
  visuals?: Visual[];
  cols?: number;
  title?: string;
  data_ref?: string;
  columns?: string[];
  text?: string;
  style?: string;
  left?: Record<string, unknown>;
  right?: Record<string, unknown>;
}

export interface CrossReference {
  to_page: string;
  reason: string;
}

export interface ReportPage {
  id: string;
  title: string;
  purpose: string;
  layout: LayoutType;
  blocks: ReportBlock[];
  cross_references: CrossReference[];
}

export interface Appendix {
  methodology: string;
  data_quality_notes: string[];
  open_questions: string[];
}

export interface ComplexRenderSpec {
  mode: "complex";
  report_title: string;
  report_subtitle?: string;
  executive_summary: ExecSummary;
  pages: ReportPage[];
  appendix: Appendix;
  plan_ids?: string[];
  subagent_ids?: string[];
  memory_refs?: Array<{ scope: string; key: string }>;
}

export type RenderSpec = SimpleRenderSpec | ModerateRenderSpec | ComplexRenderSpec;
