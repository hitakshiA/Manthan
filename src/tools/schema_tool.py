"""Schema summary tool — now with full Layer 1 intelligence.

Exposes column statistics, cardinality, completeness, sample values,
and aggregation rules alongside the basic schema. The frontend uses
this to render rich dataset profile pages.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.semantic.schema import DataContextDocument


class SchemaSummaryColumn(BaseModel):
    """A single column with full Layer 1 intelligence."""

    name: str
    dtype: str
    role: str
    description: str
    aggregation: str | None = None
    cardinality: int | None = None
    completeness: float | None = None
    sample_values: list[str] = Field(default_factory=list)
    stats: dict[str, Any] | None = None


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
    columns: list[SchemaSummaryColumn]
    summary_tables: list[str] = Field(default_factory=list)
    verified_queries: list[SchemaSummaryVerifiedQuery] = Field(
        default_factory=list,
    )


def get_schema(
    dcd: DataContextDocument,
    *,
    summary_tables: list[str] | None = None,
) -> SchemaSummary:
    """Return a :class:`SchemaSummary` with full column intelligence."""
    return SchemaSummary(
        dataset_id=dcd.dataset.id,
        name=dcd.dataset.name,
        description=dcd.dataset.description,
        row_count=dcd.dataset.source.row_count,
        columns=[
            SchemaSummaryColumn(
                name=col.name,
                dtype=col.dtype,
                role=col.role,
                description=col.description,
                aggregation=col.aggregation,
                cardinality=col.cardinality,
                completeness=col.completeness,
                sample_values=[
                    str(v) for v in (col.sample_values or [])[:5]
                ],
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
                question=q.question, sql=q.sql, intent=q.intent,
            )
            for q in dcd.dataset.verified_queries
        ],
    )
