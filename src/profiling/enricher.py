"""Deterministic enrichment: temporal grain, metric proposals, hierarchies.

The enricher is the "ENRICH" step of the Silver-stage agent loop. It
adds inferred structure on top of raw column profiles without involving
the LLM:

- :func:`detect_temporal_grain` classifies a date column's cadence from
  gap analysis.
- :func:`propose_metrics` emits plausible computed metrics from column
  naming and role hints.
- :func:`detect_hierarchies` discovers functional dependencies between
  dimension columns (e.g. ``city`` → ``state`` → ``country``) so the
  downstream agent can drill up from a low-cardinality lookup to a
  higher-cardinality one.
"""

from __future__ import annotations

from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from src.ingestion.base import quote_identifier, validate_identifier
from src.profiling.statistical import ColumnProfile, is_numeric_type, is_string_type

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

    When the column cannot be cast to DATE (for example the classifier
    marked a non-date string like an ISO week label as temporal), we
    return ``"irregular"`` rather than raise, so the agent still gets
    a usable (if coarse) grain hint.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)
    quoted_col = quote_identifier(temporal_column)

    try:
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
    except duckdb.Error:
        return "irregular"

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


# Functional-dependency detection thresholds. A column pair (A, B) is
# considered a hierarchy (A is finer-grained than B) when:
#  - both are dimension-shaped (string-like, reasonable cardinality)
#  - cardinality(B) < cardinality(A) (B is the parent / coarser)
#  - every distinct A value maps to exactly one distinct B value
#    (functional dependency A → B)
_HIERARCHY_MIN_CARDINALITY = 2
_HIERARCHY_MAX_CARDINALITY = 10_000


def detect_hierarchies(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    profiles: list[ColumnProfile],
) -> dict[str, list[str]]:
    """Return a ``{child_col: [parent_col, grandparent_col, ...]}`` mapping.

    Uses functional-dependency analysis. For every pair (A, B) where B
    has strictly fewer distinct values, if each A value maps to exactly
    one B value, B is marked as the immediate parent of A. Chains are
    resolved greedily so ``city`` → ``state`` → ``country`` becomes
    ``{"city": ["state", "country"]}``.

    Raises:
        SqlValidationError: If ``table_name`` is not a valid identifier.
    """
    validate_identifier(table_name)

    candidates = [
        p
        for p in profiles
        if is_string_type(p.dtype)
        and _HIERARCHY_MIN_CARDINALITY <= p.distinct_count <= _HIERARCHY_MAX_CARDINALITY
    ]
    if len(candidates) < 2:
        return {}

    parents: dict[str, str] = {}
    for child in candidates:
        for parent in candidates:
            if parent.name == child.name:
                continue
            if parent.distinct_count >= child.distinct_count:
                continue
            if _is_functional_dependency(
                connection, table_name, child.name, parent.name
            ):
                current = parents.get(child.name)
                if current is None or _cardinality(
                    profiles, parent.name
                ) < _cardinality(profiles, current):
                    parents[child.name] = parent.name
                break

    # Resolve chains: for each child, walk the parent map.
    hierarchies: dict[str, list[str]] = {}
    for child in candidates:
        chain: list[str] = []
        cursor = parents.get(child.name)
        seen = {child.name}
        while cursor is not None and cursor not in seen:
            chain.append(cursor)
            seen.add(cursor)
            cursor = parents.get(cursor)
        if chain:
            hierarchies[child.name] = chain
    return hierarchies


def _is_functional_dependency(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    child: str,
    parent: str,
) -> bool:
    """Return ``True`` when every ``child`` value maps to exactly one ``parent``."""
    quoted_child = quote_identifier(child)
    quoted_parent = quote_identifier(parent)
    row = connection.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT {quoted_child} FROM {table_name} "
        f"  WHERE {quoted_child} IS NOT NULL AND {quoted_parent} IS NOT NULL "
        f"  GROUP BY {quoted_child} "
        f"  HAVING COUNT(DISTINCT {quoted_parent}) > 1"
        f")"
    ).fetchone()
    if row is None:
        return False
    return int(row[0]) == 0


def _cardinality(profiles: list[ColumnProfile], name: str) -> int:
    for profile in profiles:
        if profile.name == name:
            return profile.distinct_count
    return 0
