"""Deterministic enrichment: temporal grain detection and metric proposals.

The enricher is the "ENRICH" step of the Silver-stage agent loop. It adds
inferred structure on top of raw column profiles without involving the
LLM: detecting the temporal grain of date columns from gap analysis, and
proposing plausible computed metrics from column naming and role hints.

Temporal-grain detection works by computing the modal gap between
consecutive distinct dates in the column. Metric proposal is pattern-
matching on column names plus statistical shape.
"""

from __future__ import annotations

from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from src.ingestion.base import quote_identifier, validate_identifier
from src.profiling.statistical import ColumnProfile, is_numeric_type

TemporalGrain = Literal[
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly",
    "irregular",
]

# Gap thresholds for temporal grain inference. Ranges accommodate calendar
# drift (28-31 days/month, 88-92 days/quarter, 360-370 days/year).
_DAILY_GAP = 1
_WEEKLY_GAP = 7
_MONTHLY_RANGE = (28, 31)
_QUARTERLY_RANGE = (88, 92)
_YEARLY_RANGE = (360, 370)

# Keyword sets used by metric-proposal heuristics.
_REVENUE_KEYWORDS = frozenset(
    {"revenue", "amount", "price", "total", "sales", "cost", "value"}
)
_QUANTITY_KEYWORDS = frozenset({"quantity", "qty", "count", "units"})
_ID_NAME_HINTS = frozenset({"id", "order_id", "transaction_id", "invoice_id"})


class MetricProposal(BaseModel):
    """A plausible computed metric derived from the column profiles."""

    model_config = ConfigDict(frozen=True)

    name: str
    formula: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


def detect_temporal_grain(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    temporal_column: str,
) -> TemporalGrain:
    """Return the modal gap-based grain of ``temporal_column`` in ``table_name``.

    The query extracts distinct dates, computes the day gap between each
    date and its predecessor, and returns the DuckDB ``mode()`` of those
    gaps. The returned gap is mapped onto one of the :data:`TemporalGrain`
    buckets; gaps that don't fit any bucket return ``"irregular"``.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)
    quoted_col = quote_identifier(temporal_column)

    gap_row = connection.execute(
        f"WITH sorted_dates AS ("
        f"  SELECT DISTINCT CAST({quoted_col} AS DATE) AS d "
        f"  FROM {table_name} "
        f"  WHERE {quoted_col} IS NOT NULL "
        f"), "
        f"gaps AS ("
        f"  SELECT DATE_DIFF('day', LAG(d) OVER (ORDER BY d), d) AS gap "
        f"  FROM sorted_dates"
        f") "
        f"SELECT mode(gap) FROM gaps WHERE gap IS NOT NULL"
    ).fetchone()

    modal_gap = gap_row[0] if gap_row is not None else None
    if modal_gap is None:
        return "irregular"

    gap = int(modal_gap)
    if gap == _DAILY_GAP:
        return "daily"
    if gap == _WEEKLY_GAP:
        return "weekly"
    if _MONTHLY_RANGE[0] <= gap <= _MONTHLY_RANGE[1]:
        return "monthly"
    if _QUARTERLY_RANGE[0] <= gap <= _QUARTERLY_RANGE[1]:
        return "quarterly"
    if _YEARLY_RANGE[0] <= gap <= _YEARLY_RANGE[1]:
        return "yearly"
    return "irregular"


def propose_metrics(profiles: list[ColumnProfile]) -> list[MetricProposal]:
    """Propose plausible computed metrics from ``profiles``.

    Emits, when the relevant columns are present:

    - ``average_{revenue}_per_{id}`` — mean revenue per unique identifier
    - ``{id}_count`` — distinct count of the primary id column
    - ``{revenue}_per_{quantity}`` — effective unit price

    The proposals are deterministic and deliberately conservative; the
    user (or the LLM classifier) always has final say via the DCD.
    """
    numeric = [p for p in profiles if is_numeric_type(p.dtype)]
    revenue_cols = [p for p in numeric if _matches_any(p.name, _REVENUE_KEYWORDS)]
    quantity_cols = [p for p in numeric if _matches_any(p.name, _QUANTITY_KEYWORDS)]
    id_cols = [p for p in profiles if _is_id_like(p)]

    proposals: list[MetricProposal] = []

    if revenue_cols and id_cols:
        revenue = revenue_cols[0]
        id_col = id_cols[0]
        proposals.append(
            MetricProposal(
                name=f"average_{revenue.name}_per_{id_col.name}",
                formula=f"SUM({revenue.name}) / COUNT(DISTINCT {id_col.name})",
                description=(f"Average {revenue.name} per unique {id_col.name}."),
                depends_on=[revenue.name, id_col.name],
            )
        )

    if id_cols:
        id_col = id_cols[0]
        proposals.append(
            MetricProposal(
                name=f"{id_col.name}_count",
                formula=f"COUNT(DISTINCT {id_col.name})",
                description=f"Number of unique {id_col.name} values.",
                depends_on=[id_col.name],
            )
        )

    if revenue_cols and quantity_cols:
        revenue = revenue_cols[0]
        quantity = quantity_cols[0]
        proposals.append(
            MetricProposal(
                name=f"{revenue.name}_per_{quantity.name}",
                formula=f"SUM({revenue.name}) / NULLIF(SUM({quantity.name}), 0)",
                description=(f"Effective {revenue.name} per unit of {quantity.name}."),
                depends_on=[revenue.name, quantity.name],
            )
        )

    return proposals


def _matches_any(name: str, keywords: frozenset[str]) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in keywords)


def _is_id_like(profile: ColumnProfile) -> bool:
    lowered = profile.name.lower()
    if lowered in _ID_NAME_HINTS:
        return True
    if lowered.endswith("_id") or lowered.startswith("id_"):
        return True
    # Very high cardinality integer/string columns are likely ids
    return profile.cardinality_ratio >= 0.95 and profile.distinct_count >= 5
