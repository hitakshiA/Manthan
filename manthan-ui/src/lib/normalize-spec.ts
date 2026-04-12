import type {
  RenderSpec, SimpleRenderSpec, ModerateRenderSpec, ComplexRenderSpec,
  KPICard, Visual, DashboardSection, DrillDown, Citation,
} from "@/types/render-spec";

/* eslint-disable @typescript-eslint/no-explicit-any */

function normKpi(k: any): KPICard {
  if (!k || typeof k !== "object") return { value: "—", label: "", sentiment: "neutral" };
  return {
    value: String(k.value ?? ""),
    label: String(k.label ?? ""),
    delta: k.delta ?? k.trend ?? undefined,
    sentiment: k.trend_direction === "up" ? "positive"
      : k.trend_direction === "down" ? "negative"
      : (k.sentiment ?? "neutral"),
  };
}

function normVisual(v: any): Visual {
  if (!v || typeof v !== "object") return { id: "", type: "bar", title: "", encoding: {} };

  // Agent uses chart_type instead of type
  const chartType = v.type ?? v.chart_type ?? "bar";

  // Agent may put x/y as raw data arrays OR as field names pointing into a data array
  // Normalize everything into encoding for the mapper
  const enc: Record<string, any> = { ...(v.encoding ?? {}) };

  // If x and y are arrays (raw data format from agent), convert to {data, x, y} format
  if (Array.isArray(v.x) && Array.isArray(v.y)) {
    // Agent format: x=["A","B"], y=[10,20] → convert to data=[{x:"A",y:10},{x:"B",y:20}]
    const xLabel = v.x_label ?? "x";
    const yLabel = v.y_label ?? "y";
    enc.data = v.x.map((xVal: any, i: number) => ({ [xLabel]: xVal, [yLabel]: v.y[i] }));
    enc.x = xLabel;
    enc.y = yLabel;
  } else {
    // Standard format: x="fieldName", y="fieldName", data=[{...}]
    for (const key of ["x", "y", "data", "color", "sort_by", "color_scheme", "color_by", "orientation"]) {
      if (v[key] !== undefined && enc[key] === undefined) enc[key] = v[key];
    }
  }

  return {
    id: String(v.id ?? ""),
    type: chartType,
    title: String(v.title ?? ""),
    data_ref: v.data_ref,
    encoding: enc,
    caption: v.caption ? String(v.caption) : undefined,
    annotations: Array.isArray(v.annotations) ? v.annotations : [],
  };
}

function normDrillDown(d: any): DrillDown {
  if (typeof d === "string") return { label: d, query_hint: d };
  if (d && typeof d === "object") return { label: String(d.label ?? ""), query_hint: String(d.query_hint ?? d.label ?? "") };
  return { label: "", query_hint: "" };
}

function normCitation(c: any): Citation {
  if (!c || typeof c !== "object") return { kind: "column", identifier: "dataset", reason: "source" };
  return {
    kind: String(c.kind ?? "column"),
    identifier: String(c.identifier ?? c.table ?? "dataset"),
    reason: String(c.reason ?? c.aggregation ?? "source"),
  };
}

function normSection(s: any): DashboardSection {
  if (!s || typeof s !== "object") return { title: "", narrative: "", layout: "single", visuals: [], drill_downs: [] };
  return {
    id: s.id ? String(s.id) : undefined,
    title: String(s.title ?? ""),
    narrative: String(s.narrative ?? ""),
    layout: s.layout ?? "single",
    visuals: Array.isArray(s.visuals) ? s.visuals.map(normVisual) : [],
    drill_downs: Array.isArray(s.drill_downs) ? s.drill_downs.map(normDrillDown) : [],
  };
}

export function normalizeSpec(raw: any): RenderSpec {
  if (!raw || typeof raw !== "object") {
    return { mode: "simple", headline: { value: "—", label: "", sentiment: "neutral" }, narrative: "", visuals: [], citations: [] } as SimpleRenderSpec;
  }

  const mode = String(raw.mode ?? "simple").toLowerCase();

  if (mode === "simple") {
    return {
      mode: "simple",
      headline: normKpi(raw.headline),
      narrative: String(raw.narrative ?? ""),
      visuals: Array.isArray(raw.visuals) ? raw.visuals.map(normVisual) : [],
      citations: Array.isArray(raw.citations) ? raw.citations.map(normCitation) : [],
      caveats: Array.isArray(raw.caveats) ? raw.caveats.map(String) : [],
    } as SimpleRenderSpec;
  }

  if (mode === "moderate") {
    return {
      mode: "moderate",
      title: String(raw.title ?? "Dashboard"),
      subtitle: raw.subtitle ? String(raw.subtitle) : undefined,
      kpi_row: Array.isArray(raw.kpi_row) ? raw.kpi_row.map(normKpi) : [],
      sections: Array.isArray(raw.sections) ? raw.sections.map(normSection) : [],
      citations: Array.isArray(raw.citations) ? raw.citations.map(normCitation) : [],
      caveats: Array.isArray(raw.caveats) ? raw.caveats.map(String) : [],
      plan_id: raw.plan_id ? String(raw.plan_id) : undefined,
    } as ModerateRenderSpec;
  }

  if (mode === "complex") {
    const es = raw.executive_summary ?? {};
    return {
      mode: "complex",
      report_title: String(raw.report_title ?? raw.title ?? "Report"),
      executive_summary: {
        headline: String(es.headline ?? ""),
        key_findings: Array.isArray(es.key_findings) ? es.key_findings.map(String) : [],
        recommendations: Array.isArray(es.recommendations) ? es.recommendations.map((r: any) => ({
          id: String(r.id ?? `rec_${Math.random().toString(36).slice(2, 6)}`),
          action: String(r.action ?? r.rec ?? ""),
          rationale: String(r.rationale ?? r.evidence ?? ""),
          expected_impact: String(r.expected_impact ?? r.evidence ?? ""),
          confidence: String(r.confidence ?? "medium").toLowerCase() as "low" | "medium" | "high",
        })) : [],
      },
      pages: Array.isArray(raw.pages) ? raw.pages.map((p: any) => ({
        id: String(p.id ?? `p_${Math.random().toString(36).slice(2, 6)}`),
        title: String(p.title ?? ""),
        purpose: String(p.purpose ?? p.narrative ?? ""),
        layout: p.layout ?? "single",
        blocks: Array.isArray(p.blocks) ? p.blocks : [],
        cross_references: Array.isArray(p.cross_references) ? p.cross_references : [],
      })) : [],
      appendix: raw.appendix ?? { methodology: "SQL-based analysis", data_quality_notes: [], open_questions: [] },
      plan_ids: Array.isArray(raw.plan_ids) ? raw.plan_ids.map(String) : (raw.plan_id ? [String(raw.plan_id)] : []),
    } as ComplexRenderSpec;
  }

  // Unknown mode — show raw text as narrative
  return {
    mode: "simple",
    headline: { value: "—", label: "", sentiment: "neutral" },
    narrative: typeof raw === "string" ? raw : JSON.stringify(raw, null, 2),
    visuals: [],
    citations: [],
  } as SimpleRenderSpec;
}
