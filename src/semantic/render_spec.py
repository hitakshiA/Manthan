"""Render spec schema — the contract between Layer 2 and Layer 3.

Defines the Pydantic models for the three rendering modes:

- **Simple**: a headline KPI, a short narrative, and 1-3 visuals.
- **Moderate**: a single-page dashboard with KPI row, 3+ story-arced
  sections, drill-down hooks, and plan linkage.
- **Complex**: a multi-page report with executive summary,
  recommendations, appendix, subagent traceability, and cross-session
  memory references.

The agent (Layer 2) produces one of these specs per user turn. The
frontend (Layer 3) consumes it and renders it without deciding what to
show — the agent already decided.

These models were derived from 24 render specs that survived the
Layer 1 live stress test (see ``docs/layer3_spec_schema.md``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- shared building blocks -----------------------------------------------

VisualType = Literal[
    "histogram",
    "bar",
    "line",
    "area",
    "scatter",
    "bubble",
    "heatmap",
    "funnel",
    "sankey",
    "treemap",
    "pie",
    "box",
    "violin",
    "kpi",
]

LayoutType = Literal[
    "single",
    "two_col",
    "three_col",
    "hero_chart",
    "hero_plus_grid",
    "kpi_grid",
    "narrative_only",
]

Sentiment = Literal["positive", "negative", "neutral"]
Confidence = Literal["low", "medium", "high"]
RenderMode = Literal["simple", "moderate", "complex"]

BlockType = Literal[
    "kpi_row",
    "hero_chart",
    "chart_grid",
    "table",
    "narrative",
    "callout",
    "comparison",
]


class Citation(BaseModel):
    """A DCD reference backing the agent's output."""

    model_config = ConfigDict(extra="allow")

    kind: str = Field(
        ...,
        description=(
            "column | metric | agent_instruction | verified_query | hierarchy"
        ),
    )
    identifier: str
    reason: str


class Visual(BaseModel):
    """One chart or KPI card in the render spec."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    type: VisualType = "bar"
    title: str = ""
    data_ref: str | None = Field(
        default=None,
        description="Path to a parquet file under OUTPUT_DIR",
    )
    encoding: dict[str, Any] = Field(default_factory=dict)
    caption: str | None = None
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class KPICard(BaseModel):
    """One card in a KPI row."""

    value: str
    label: str
    delta: str | None = None
    sentiment: Sentiment = "neutral"


class DrillDown(BaseModel):
    """A drill-down hint the frontend renders as a clickable button."""

    label: str
    query_hint: str


class MemoryRef(BaseModel):
    """Pointer to a memory entry this spec depends on or produced."""

    scope: str
    key: str


# --- simple mode ----------------------------------------------------------


class SimpleRenderSpec(BaseModel):
    """Mode: simple — a headline KPI, short narrative, 1-3 visuals."""

    model_config = ConfigDict(extra="allow")

    mode: Literal["simple"] = "simple"
    headline: KPICard
    narrative: str = Field(..., max_length=500, description="2-4 sentences")
    visuals: list[Visual] = Field(..., min_length=1, max_length=3)
    citations: list[Citation] = Field(..., min_length=1)
    caveats: list[str] = Field(default_factory=list)


# --- moderate mode --------------------------------------------------------


class DashboardSection(BaseModel):
    """One story-arced section in a moderate dashboard."""

    id: str | None = None
    title: str = Field(
        ...,
        description=(
            "An insight title, not a label. "
            "E.g. 'Weekend riders tip more' not 'Section 1'"
        ),
    )
    narrative: str
    layout: LayoutType = "single"
    visuals: list[Visual] = Field(default_factory=list)
    drill_downs: list[DrillDown] = Field(default_factory=list)


class ModerateRenderSpec(BaseModel):
    """Mode: moderate — a single-page dashboard."""

    model_config = ConfigDict(extra="allow")

    mode: Literal["moderate"] = "moderate"
    title: str
    subtitle: str | None = None
    kpi_row: list[KPICard] = Field(..., min_length=2, description="2-6 headline cards")
    sections: list[DashboardSection] = Field(
        ..., min_length=3, description="3+ story-arced sections"
    )
    caveats: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(..., min_length=1)
    plan_id: str | None = None
    subagent_ids: list[str] = Field(default_factory=list)


# --- complex mode ---------------------------------------------------------


class Recommendation(BaseModel):
    """One actionable recommendation in the executive summary."""

    id: str
    action: str
    rationale: str
    expected_impact: str
    evidence_page: str | None = None
    confidence: Confidence = "medium"


class ExecSummary(BaseModel):
    """Executive summary for a complex report."""

    headline: str
    key_findings: list[str] = Field(
        ..., min_length=2, description="2+ quantified one-liners"
    )
    recommendations: list[Recommendation] = Field(..., min_length=1)


class ReportBlock(BaseModel):
    """One block inside a report page."""

    type: BlockType
    items: list[KPICard] | None = None
    visual: Visual | None = None
    visuals: list[Visual] | None = None
    cols: int | None = None
    title: str | None = None
    data_ref: str | None = None
    columns: list[str] | None = None
    text: str | None = None
    style: str | None = None
    left: dict[str, Any] | None = None
    right: dict[str, Any] | None = None


class CrossReference(BaseModel):
    """Link from one page to another."""

    to_page: str
    reason: str


class ReportPage(BaseModel):
    """One page in a complex multi-page report."""

    id: str
    title: str
    purpose: str
    layout: LayoutType = "single"
    blocks: list[ReportBlock] = Field(default_factory=list)
    cross_references: list[CrossReference] = Field(default_factory=list)


class Appendix(BaseModel):
    """Report appendix: methodology, caveats, open questions."""

    methodology: str
    data_quality_notes: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ComplexRenderSpec(BaseModel):
    """Mode: complex — a multi-page report with exec summary."""

    model_config = ConfigDict(extra="allow")

    mode: Literal["complex"] = "complex"
    report_title: str
    report_subtitle: str | None = None
    executive_summary: ExecSummary
    pages: list[ReportPage] = Field(..., min_length=1, description="1-8 analysis pages")
    appendix: Appendix
    plan_ids: list[str] = Field(default_factory=list)
    subagent_ids: list[str] = Field(default_factory=list)
    memory_refs: list[MemoryRef] = Field(default_factory=list)
    phase: int | None = None
    generated_in_session: str | None = None


# --- discriminated union --------------------------------------------------

RenderSpec = SimpleRenderSpec | ModerateRenderSpec | ComplexRenderSpec


# --- normalization layer ---------------------------------------------------
# The agent (GLM 5.1, gpt-oss-120b, etc.) produces render specs in a natural
# JSON format that doesn't exactly match the strict Pydantic models above.
# This normalizer bridges the gap so Layer 3 always gets typed, validated data.


_LAYOUT_MAP: dict[str, str] = {
    "row": "two_col",
    "vertical": "single",
    "horizontal": "two_col",
    "grid": "kpi_grid",
}

_COUNTER = 0


def _next_id(prefix: str = "v") -> str:
    global _COUNTER
    _COUNTER += 1
    return f"{prefix}_{_COUNTER}"


def _norm_visual(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize an agent-produced visual into the Visual schema."""
    vtype = raw.get("type", "bar")
    return {
        "id": raw.get("id", _next_id("vis")),
        "type": vtype
        if vtype
        in (
            "histogram",
            "bar",
            "line",
            "area",
            "scatter",
            "bubble",
            "heatmap",
            "funnel",
            "sankey",
            "treemap",
            "pie",
            "box",
            "violin",
            "kpi",
        )
        else "bar",
        "title": raw.get("title", ""),
        "data_ref": raw.get("data_ref"),
        "encoding": {
            k: v
            for k, v in raw.items()
            if k
            not in {
                "id",
                "type",
                "title",
                "data_ref",
                "encoding",
                "caption",
                "annotations",
            }
        },
        "caption": raw.get("caption"),
        "annotations": raw.get("annotations", []),
    }


def _norm_citation(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize agent citation format to Citation schema."""
    if "kind" in raw and "identifier" in raw:
        return raw
    # Agent format: {table, columns, filter, aggregation}
    table = raw.get("table", "")
    cols = raw.get("columns", [])
    ident = f"{table}.{','.join(cols)}" if cols else table
    parts = []
    if raw.get("filter"):
        parts.append(f"filter={raw['filter']}")
    if raw.get("aggregation"):
        parts.append(f"agg={raw['aggregation']}")
    return {
        "kind": "column",
        "identifier": ident or "dataset",
        "reason": "; ".join(parts) if parts else "source data",
    }


def _norm_drill_down(raw: Any) -> dict[str, str]:
    """Normalize string or dict drill-down to DrillDown schema."""
    if isinstance(raw, str):
        return {"label": raw[:80], "query_hint": raw}
    return {
        "label": raw.get("label", raw.get("query_hint", "")),
        "query_hint": raw.get("query_hint", raw.get("label", "")),
    }


def _norm_layout(raw: str | None) -> str:
    """Map agent layout strings to valid LayoutType."""
    if raw is None:
        return "single"
    return _LAYOUT_MAP.get(
        raw,
        raw
        if raw
        in (
            "single",
            "two_col",
            "three_col",
            "hero_chart",
            "hero_plus_grid",
            "kpi_grid",
            "narrative_only",
        )
        else "single",
    )


def _norm_kpi(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a KPI card, keeping extra fields as-is."""
    return {
        "value": str(raw.get("value", "")),
        "label": raw.get("label", ""),
        "delta": raw.get("delta") or raw.get("trend"),
        "sentiment": (
            "positive"
            if raw.get("trend_direction") == "up"
            else "negative"
            if raw.get("trend_direction") == "down"
            else "neutral"
        ),
    }


def _norm_confidence(raw: str) -> str:
    """Normalize confidence to lowercase."""
    low = raw.lower()
    return low if low in ("low", "medium", "high") else "medium"


def normalize_render_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Transform raw agent output into a dict that validates.

    Handles case normalization, field name mapping, missing defaults,
    and structural differences between agent output and Pydantic models.
    """
    global _COUNTER
    _COUNTER = 0

    mode = (data.get("mode") or "simple").lower()
    out: dict[str, Any] = {"mode": mode}

    if mode == "simple":
        headline = data.get("headline", {})
        out["headline"] = _norm_kpi(headline)
        out["narrative"] = (data.get("narrative") or "")[:500]
        out["visuals"] = [_norm_visual(v) for v in (data.get("visuals") or [])] or [
            _norm_visual({"type": "kpi", "title": "Result"})
        ]
        out["citations"] = [
            _norm_citation(c) for c in (data.get("citations") or [])
        ] or [{"kind": "column", "identifier": "dataset", "reason": "source"}]
        out["caveats"] = data.get("caveats", [])

    elif mode == "moderate":
        out["title"] = data.get("title", "Dashboard")
        out["subtitle"] = data.get("subtitle")
        out["kpi_row"] = [_norm_kpi(k) for k in (data.get("kpi_row") or [])]
        if len(out["kpi_row"]) < 2:
            out["kpi_row"] = [
                {"value": "—", "label": "N/A"},
                {"value": "—", "label": "N/A"},
            ]
        sections = []
        for s in data.get("sections") or []:
            sections.append(
                {
                    "id": s.get("id", _next_id("sec")),
                    "title": s.get("title", "Section"),
                    "narrative": s.get("narrative", ""),
                    "layout": _norm_layout(s.get("layout")),
                    "visuals": [_norm_visual(v) for v in (s.get("visuals") or [])],
                    "drill_downs": [
                        _norm_drill_down(d) for d in (s.get("drill_downs") or [])
                    ],
                }
            )
        out["sections"] = sections
        out["citations"] = [
            _norm_citation(c) for c in (data.get("citations") or [])
        ] or [{"kind": "column", "identifier": "dataset", "reason": "source"}]
        out["caveats"] = data.get("caveats", [])
        out["plan_id"] = data.get("plan_id")
        out["subagent_ids"] = data.get("subagent_ids", [])

    elif mode == "complex":
        out["report_title"] = data.get("report_title", data.get("title", "Report"))
        out["report_subtitle"] = data.get("report_subtitle")

        # Executive summary
        es = data.get("executive_summary", {})
        recs = []
        for r in es.get("recommendations") or []:
            recs.append(
                {
                    "id": r.get("id", _next_id("rec")),
                    "action": r.get("action", r.get("rec", "")),
                    "rationale": r.get("rationale", r.get("evidence", "")),
                    "expected_impact": r.get(
                        "expected_impact",
                        r.get("evidence", "See analysis"),
                    ),
                    "evidence_page": r.get("evidence_page"),
                    "confidence": _norm_confidence(r.get("confidence", "medium")),
                }
            )
        out["executive_summary"] = {
            "headline": es.get("headline", ""),
            "key_findings": es.get("key_findings", []),
            "recommendations": recs
            or [
                {
                    "id": "rec_1",
                    "action": "See report",
                    "rationale": "Based on analysis",
                    "expected_impact": "Variable",
                }
            ],
        }

        # Pages
        pages = []
        for i, p in enumerate(data.get("pages") or []):
            page_id = p.get("id", _next_id("page"))
            # Convert flat visuals to blocks
            blocks = []
            for b in p.get("blocks") or []:
                blocks.append(b)
            if not blocks and p.get("visuals"):
                for v in p["visuals"]:
                    if v.get("type") == "kpi_row":
                        blocks.append(
                            {
                                "type": "kpi_row",
                                "items": [
                                    _norm_kpi(item) for item in v.get("data", [])
                                ],
                            }
                        )
                    else:
                        blocks.append(
                            {
                                "type": "hero_chart",
                                "visual": _norm_visual(v),
                            }
                        )
            if p.get("narrative") and not any(
                b.get("type") == "narrative" for b in blocks
            ):
                blocks.insert(
                    0,
                    {
                        "type": "narrative",
                        "text": p["narrative"],
                    },
                )
            if p.get("insight_box"):
                ib = p["insight_box"]
                blocks.append(
                    {
                        "type": "callout",
                        "text": (
                            f"{ib.get('finding', '')} {ib.get('implication', '')}"
                        ).strip(),
                        "style": "insight",
                    }
                )
            pages.append(
                {
                    "id": page_id,
                    "title": p.get("title", f"Page {i + 1}"),
                    "purpose": p.get(
                        "purpose",
                        p.get("narrative", "")[:200] or "Analysis",
                    ),
                    "layout": _norm_layout(p.get("layout")),
                    "blocks": blocks,
                    "cross_references": [
                        {"to_page": ref, "reason": "related"}
                        for ref in (p.get("drill_downs") or [])
                        if isinstance(ref, str)
                    ],
                }
            )
        out["pages"] = pages or [
            {
                "id": "page_1",
                "title": "Analysis",
                "purpose": "Primary analysis",
            }
        ]

        # Appendix (required — add default if missing)
        appendix = data.get("appendix") or {}
        out["appendix"] = {
            "methodology": appendix.get(
                "methodology",
                "SQL-based analysis on the full dataset",
            ),
            "data_quality_notes": appendix.get("data_quality_notes", []),
            "open_questions": appendix.get("open_questions", []),
        }

        # plan_ids (normalize from singular plan_id)
        plan_ids = data.get("plan_ids", [])
        if not plan_ids and data.get("plan_id"):
            plan_ids = [data["plan_id"]]
        out["plan_ids"] = plan_ids
        out["subagent_ids"] = data.get("subagent_ids", [])
        out["memory_refs"] = data.get("memory_refs", [])

    return out


def parse_render_spec(data: dict[str, Any]) -> RenderSpec:
    """Parse a raw dict into the appropriate render spec model.

    First normalizes the agent output, then validates against
    the Pydantic model. Dispatches on the ``mode`` field.

    Raises:
        ValueError: If ``mode`` is missing or unrecognized.
        ValidationError: If the data doesn't conform after normalization.
    """
    normalized = normalize_render_spec(data)
    mode = normalized.get("mode")
    if mode == "simple":
        return SimpleRenderSpec.model_validate(normalized)
    if mode == "moderate":
        return ModerateRenderSpec.model_validate(normalized)
    if mode == "complex":
        return ComplexRenderSpec.model_validate(normalized)
    msg = f"Unknown or missing render mode: {mode!r}"
    raise ValueError(msg)
