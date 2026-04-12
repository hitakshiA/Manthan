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

    model_config = ConfigDict(frozen=True)

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

    id: str
    type: VisualType
    title: str
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

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

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


def parse_render_spec(data: dict[str, Any]) -> RenderSpec:
    """Parse a raw dict into the appropriate render spec model.

    Dispatches on the ``mode`` field.

    Raises:
        ValueError: If ``mode`` is missing or unrecognized.
        ValidationError: If the data doesn't conform to the schema.
    """
    mode = data.get("mode")
    if mode == "simple":
        return SimpleRenderSpec.model_validate(data)
    if mode == "moderate":
        return ModerateRenderSpec.model_validate(data)
    if mode == "complex":
        return ComplexRenderSpec.model_validate(data)
    msg = f"Unknown or missing render mode: {mode!r}"
    raise ValueError(msg)
