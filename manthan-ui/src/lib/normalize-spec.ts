import type { RenderSpec } from "@/types/render-spec";

/** Normalize raw agent render_spec into a shape the frontend can render.
 *  Handles: case normalization, missing fields, agent-format visuals. */
export function normalizeSpec(raw: Record<string, unknown>): RenderSpec {
  const mode = ((raw.mode as string) ?? "simple").toLowerCase();

  // Normalize KPI cards: agent uses trend/trend_direction, we use delta/sentiment
  function normKpi(k: Record<string, unknown>) {
    return {
      value: String(k.value ?? ""),
      label: String(k.label ?? ""),
      delta: (k.delta ?? k.trend ?? undefined) as string | undefined,
      sentiment: k.trend_direction === "up" ? "positive" as const
        : k.trend_direction === "down" ? "negative" as const
        : "neutral" as const,
    };
  }

  // Normalize visuals: ensure encoding exists, move top-level x/y/data into it
  function normVisual(v: Record<string, unknown>) {
    const enc = (v.encoding ?? {}) as Record<string, unknown>;
    // Move top-level chart props into encoding if not already there
    for (const key of ["x", "y", "data", "color", "sort_by", "color_scheme", "color_by"]) {
      if (v[key] !== undefined && enc[key] === undefined) {
        enc[key] = v[key];
      }
    }
    return {
      ...v,
      id: v.id ?? "",
      type: v.type ?? "bar",
      title: v.title ?? "",
      encoding: enc,
    };
  }

  if (mode === "simple") {
    return {
      mode: "simple",
      headline: normKpi((raw.headline ?? {}) as Record<string, unknown>),
      narrative: String(raw.narrative ?? ""),
      visuals: ((raw.visuals ?? []) as Array<Record<string, unknown>>).map(normVisual),
      citations: (raw.citations ?? []) as RenderSpec & { mode: "simple" } extends { citations: infer C } ? C : never,
      caveats: (raw.caveats ?? []) as string[],
    } as RenderSpec;
  }

  if (mode === "moderate") {
    return {
      mode: "moderate",
      title: String(raw.title ?? "Dashboard"),
      subtitle: raw.subtitle as string | undefined,
      kpi_row: ((raw.kpi_row ?? []) as Array<Record<string, unknown>>).map(normKpi),
      sections: ((raw.sections ?? []) as Array<Record<string, unknown>>).map((s) => ({
        id: s.id,
        title: String(s.title ?? ""),
        narrative: String(s.narrative ?? ""),
        layout: s.layout ?? "single",
        visuals: ((s.visuals ?? []) as Array<Record<string, unknown>>).map(normVisual),
        drill_downs: ((s.drill_downs ?? []) as Array<unknown>).map((d) =>
          typeof d === "string" ? { label: d, query_hint: d } : d
        ),
      })),
      citations: (raw.citations ?? [{ kind: "column", identifier: "dataset", reason: "source" }]) as never,
      caveats: (raw.caveats ?? []) as string[],
      plan_id: raw.plan_id as string | undefined,
    } as RenderSpec;
  }

  if (mode === "complex") {
    const es = (raw.executive_summary ?? {}) as Record<string, unknown>;
    return {
      mode: "complex",
      report_title: String(raw.report_title ?? raw.title ?? "Report"),
      executive_summary: {
        headline: String(es.headline ?? ""),
        key_findings: (es.key_findings ?? []) as string[],
        recommendations: ((es.recommendations ?? []) as Array<Record<string, unknown>>).map((r) => ({
          id: r.id ?? `rec_${Math.random().toString(36).slice(2, 6)}`,
          action: String(r.action ?? r.rec ?? ""),
          rationale: String(r.rationale ?? r.evidence ?? ""),
          expected_impact: String(r.expected_impact ?? r.evidence ?? ""),
          confidence: ((r.confidence as string) ?? "medium").toLowerCase() as "low" | "medium" | "high",
        })),
      },
      pages: ((raw.pages ?? []) as Array<Record<string, unknown>>).map((p) => ({
        id: p.id ?? `page_${Math.random().toString(36).slice(2, 6)}`,
        title: String(p.title ?? ""),
        purpose: String(p.purpose ?? p.narrative ?? ""),
        layout: p.layout ?? "single",
        blocks: (p.blocks ?? []) as never,
        cross_references: (p.cross_references ?? []) as never,
      })),
      appendix: (raw.appendix ?? { methodology: "SQL-based analysis", data_quality_notes: [], open_questions: [] }) as never,
      plan_ids: raw.plan_ids ?? (raw.plan_id ? [raw.plan_id] : []),
    } as RenderSpec;
  }

  // Unknown mode — return as-is, let RenderRouter show error
  return raw as unknown as RenderSpec;
}
