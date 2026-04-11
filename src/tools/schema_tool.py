"""Lightweight schema summary tool.

Where :func:`src.tools.context_tool.get_context` returns the full DCD,
:func:`get_schema` returns a compact JSON-friendly summary that agents
can consult without spending prompt tokens on statistical detail.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.semantic.schema import DataContextDocument


class SchemaSummaryColumn(BaseModel):
    """A single column entry in the schema summary."""

    name: str
    dtype: str
    role: str
    description: str
    sensitivity: str | None = None


class SchemaSummaryVerifiedQuery(BaseModel):
    """A verified query as exposed via the schema tool."""

    question: str
    sql: str
    intent: str


class SchemaSummary(BaseModel):
    """Compact schema summary returned to analysis agents."""

    dataset_id: str
    name: str
    description: str
    row_count: int = Field(ge=0)
    columns: list[SchemaSummaryColumn]
    summary_tables: list[str] = Field(default_factory=list)
    verified_queries: list[SchemaSummaryVerifiedQuery] = Field(default_factory=list)


def get_schema(
    dcd: DataContextDocument,
    *,
    summary_tables: list[str] | None = None,
) -> SchemaSummary:
    """Return a compact :class:`SchemaSummary` for ``dcd``."""
    return SchemaSummary(
        dataset_id=dcd.dataset.id,
        name=dcd.dataset.name,
        description=dcd.dataset.description,
        row_count=dcd.dataset.source.row_count,
        columns=[
            SchemaSummaryColumn(
                name=column.name,
                dtype=column.dtype,
                role=column.role,
                description=column.description,
                sensitivity=(
                    column.sensitivity if column.sensitivity != "public" else None
                ),
            )
            for column in dcd.dataset.columns
        ],
        summary_tables=summary_tables or [],
        verified_queries=[
            SchemaSummaryVerifiedQuery(question=q.question, sql=q.sql, intent=q.intent)
            for q in dcd.dataset.verified_queries
        ],
    )
