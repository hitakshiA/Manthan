"""Schema summary tool — now with full Layer 1 intelligence.

Exposes column statistics, cardinality, completeness, sample values,
and aggregation rules alongside the basic schema. The frontend uses
this to render rich dataset profile pages. The agent prompt uses it
to ground queries in declared columns, rollups, and (starting
DCD v1.1) the stable entity slug that wraps the physical storage.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.semantic.schema import DataContextDocument


class SchemaSummaryColumn(BaseModel):
    """A single column with full Layer 1 intelligence.

    ``label`` and ``synonyms`` are the exec-facing surface — the agent
    prompt renders ``label`` as the primary name and treats ``synonyms``
    as additional user-language the exec might use to refer to this
    field. ``pii`` flips on aggregate-only handling in the agent.
    """

    name: str
    dtype: str
    role: str
    description: str
    label: str | None = None
    pii: bool = False
    synonyms: list[str] = Field(default_factory=list)
    aggregation: str | None = None
    cardinality: int | None = None
    completeness: float | None = None
    sample_values: list[str] = Field(default_factory=list)
    stats: dict[str, Any] | None = None


class SchemaSummaryRollup(BaseModel):
    """A pre-materialized rollup exposed to the agent by slug."""

    slug: str
    physical_table: str
    grain: str | None = None
    dimensions: list[str] = Field(default_factory=list)


class SchemaSummaryMetric(BaseModel):
    """A governed metric declaration.

    Populated from DCD v1.1 entities. Phase 2 wires the agent's
    ``compute_metric`` tool to these; Phase 1 surfaces them to the
    prompt so the agent can name the right one when narrating.
    """

    slug: str
    label: str
    description: str = ""
    expression: str
    filter: str | None = None
    unit: str | None = None
    aggregation_semantics: str = "additive"
    default_grain: str | None = None
    valid_dimensions: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class SchemaSummaryEntity(BaseModel):
    """Stable, business-facing wrapper over the physical storage."""

    slug: str
    name: str
    description: str = ""
    physical_table: str
    rollups: list[SchemaSummaryRollup] = Field(default_factory=list)
    metrics: list[SchemaSummaryMetric] = Field(default_factory=list)


class SchemaSummaryVerifiedQuery(BaseModel):
    """A verified query as exposed via the schema tool."""

    question: str
    sql: str
    intent: str


class SchemaSummary(BaseModel):
    """Full schema summary with Layer 1 intelligence."""

    dataset_id: str
    name: str
    description: str
    row_count: int = Field(ge=0)
    entity: SchemaSummaryEntity | None = None
    columns: list[SchemaSummaryColumn]
    summary_tables: list[str] = Field(
        default_factory=list,
        description=(
            "Legacy flat list of physical rollup table names — kept "
            "for backward compatibility. Use ``entity.rollups`` for "
            "new code; each rollup there carries its grain/dimensions."
        ),
    )
    verified_queries: list[SchemaSummaryVerifiedQuery] = Field(
        default_factory=list,
    )


def get_schema(
    dcd: DataContextDocument,
    *,
    summary_tables: list[str] | None = None,
) -> SchemaSummary:
    """Return a :class:`SchemaSummary` with full column intelligence."""
    entity_payload: SchemaSummaryEntity | None = None
    if dcd.dataset.entity is not None:
        e = dcd.dataset.entity
        entity_payload = SchemaSummaryEntity(
            slug=e.slug,
            name=e.name,
            description=e.description,
            physical_table=e.physical_table,
            rollups=[
                SchemaSummaryRollup(
                    slug=r.slug,
                    physical_table=r.physical_table,
                    grain=r.grain,
                    dimensions=list(r.dimensions),
                )
                for r in e.rollups
            ],
            metrics=[
                SchemaSummaryMetric(
                    slug=m.slug,
                    label=m.label,
                    description=m.description,
                    expression=m.expression,
                    filter=m.filter,
                    unit=m.unit,
                    aggregation_semantics=m.aggregation_semantics,
                    default_grain=m.default_grain,
                    valid_dimensions=list(m.valid_dimensions),
                    synonyms=list(m.synonyms),
                )
                for m in e.metrics
            ],
        )
    # Prefer rollup physical names from the entity (if present) over the
    # ad-hoc list passed in — the entity is authoritative.
    if entity_payload is not None and not summary_tables:
        summary_tables = [r.physical_table for r in entity_payload.rollups]
    return SchemaSummary(
        dataset_id=dcd.dataset.id,
        name=dcd.dataset.name,
        description=dcd.dataset.description,
        row_count=dcd.dataset.source.row_count,
        entity=entity_payload,
        columns=[
            SchemaSummaryColumn(
                name=col.name,
                dtype=col.dtype,
                role=col.role,
                description=col.description,
                label=col.label,
                pii=col.pii,
                synonyms=list(col.synonyms),
                aggregation=col.aggregation,
                cardinality=col.cardinality,
                completeness=col.completeness,
                sample_values=[str(v) for v in (col.sample_values or [])[:5]],
                stats=(
                    {
                        "min": col.stats.min,
                        "max": col.stats.max,
                        "mean": round(col.stats.mean, 2)
                        if col.stats.mean is not None
                        else None,
                        "median": col.stats.median,
                    }
                    if col.stats
                    else None
                ),
            )
            for col in dcd.dataset.columns
        ],
        summary_tables=summary_tables or [],
        verified_queries=[
            SchemaSummaryVerifiedQuery(
                question=q.question,
                sql=q.sql,
                intent=q.intent,
            )
            for q in dcd.dataset.verified_queries
        ],
    )
