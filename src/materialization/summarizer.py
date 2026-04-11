"""Pre-computed summary tables for common agent query patterns.

For each metric column in the DCD, :func:`create_summary_tables` emits:

- One temporal rollup (daily or monthly depending on the detected
  grain). The rollup aggregates every metric and includes every
  dimension column so that agents can filter without rescanning the
  full Gold table.
- One dimension breakdown per dimension column with every metric
  aggregated and the percentage of total records.

SPEC §3.2 asks for multiple temporal granularities. We keep this pass
tight (one rollup + one per-dimension breakdown) and can layer on
additional grains when the end-to-end flow is stable.
"""

from __future__ import annotations

import duckdb

from src.ingestion.base import quote_identifier, validate_identifier
from src.semantic.schema import DataContextDocument, DcdColumn

_GRAIN_TO_TRUNC: dict[str, str] = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
    "quarterly": "quarter",
    "yearly": "year",
}
# Secondary rollups to materialize alongside the detected primary grain.
# When the detected grain is fine-grained (daily/weekly), we also emit a
# monthly rollup so agents can answer "per-month" queries without a
# secondary groupby on the Gold table.
_ADDITIONAL_ROLLUPS: dict[str, list[tuple[str, str]]] = {
    "daily": [("monthly", "month")],
    "weekly": [("monthly", "month")],
    "monthly": [("quarterly", "quarter")],
    "quarterly": [("yearly", "year")],
}
_VALID_AGGREGATIONS = {"SUM", "AVG", "COUNT", "MIN", "MAX"}


def create_summary_tables(
    connection: duckdb.DuckDBPyConnection,
    gold_table: str,
    dcd: DataContextDocument,
) -> list[str]:
    """Create summary tables derived from ``gold_table``.

    Returns:
        The list of summary table names created, in the order they were
        created. Empty if the DCD has no metrics or no dimensions.
    """
    validate_identifier(gold_table)

    metric_columns = [c for c in dcd.dataset.columns if c.role == "metric"]
    dimension_columns = [c for c in dcd.dataset.columns if c.role == "dimension"]
    if not metric_columns:
        return []

    created: list[str] = []

    temporal_column = dcd.dataset.temporal.column
    grain = dcd.dataset.temporal.grain
    if temporal_column and grain in _GRAIN_TO_TRUNC:
        # Primary rollup at the detected grain.
        _emit_rollup(
            connection=connection,
            gold_table=gold_table,
            rollup_label=grain,
            trunc_unit=_GRAIN_TO_TRUNC[grain],
            temporal_column=temporal_column,
            metric_columns=metric_columns,
            dimension_columns=dimension_columns,
            created=created,
        )
        # Additional rollups (e.g. monthly when the source is daily).
        for label, unit in _ADDITIONAL_ROLLUPS.get(grain, []):
            _emit_rollup(
                connection=connection,
                gold_table=gold_table,
                rollup_label=label,
                trunc_unit=unit,
                temporal_column=temporal_column,
                metric_columns=metric_columns,
                dimension_columns=dimension_columns,
                created=created,
            )

    for dimension in dimension_columns:
        breakdown_name = f"{gold_table}_by_{dimension.name}"
        validate_identifier(breakdown_name)
        connection.execute(
            _build_dimension_breakdown_sql(
                gold_table=gold_table,
                breakdown_name=breakdown_name,
                dimension=dimension,
                metric_columns=metric_columns,
            )
        )
        created.append(breakdown_name)

    return created


def _emit_rollup(
    *,
    connection: duckdb.DuckDBPyConnection,
    gold_table: str,
    rollup_label: str,
    trunc_unit: str,
    temporal_column: str,
    metric_columns: list[DcdColumn],
    dimension_columns: list[DcdColumn],
    created: list[str],
) -> None:
    rollup_name = f"{gold_table}_{rollup_label}"
    validate_identifier(rollup_name)
    connection.execute(
        _build_temporal_rollup_sql(
            gold_table=gold_table,
            rollup_name=rollup_name,
            temporal_column=temporal_column,
            trunc_unit=trunc_unit,
            metric_columns=metric_columns,
            dimension_columns=dimension_columns,
        )
    )
    created.append(rollup_name)


def _build_temporal_rollup_sql(
    *,
    gold_table: str,
    rollup_name: str,
    temporal_column: str,
    trunc_unit: str,
    metric_columns: list[DcdColumn],
    dimension_columns: list[DcdColumn],
) -> str:
    quoted_temporal = quote_identifier(temporal_column)
    metric_exprs = ", ".join(
        f"{_agg_for(metric)}({quote_identifier(metric.name)}) "
        f"AS {quote_identifier(metric.name)}"
        for metric in metric_columns
    )
    dim_select_parts = [
        f"{quote_identifier(d.name)} AS {quote_identifier(d.name)}"
        for d in dimension_columns
    ]
    dim_select_clause = (", " + ", ".join(dim_select_parts)) if dim_select_parts else ""
    group_by_parts = [
        f"DATE_TRUNC('{trunc_unit}', {quoted_temporal})",
        *[quote_identifier(d.name) for d in dimension_columns],
    ]
    group_by_clause = ", ".join(group_by_parts)

    return (
        f"CREATE OR REPLACE TABLE {rollup_name} AS "
        f"SELECT DATE_TRUNC('{trunc_unit}', {quoted_temporal}) AS period"
        f"{dim_select_clause}, {metric_exprs}, "
        f"COUNT(*) AS record_count "
        f"FROM {gold_table} "
        f"GROUP BY {group_by_clause}"
    )


def _build_dimension_breakdown_sql(
    *,
    gold_table: str,
    breakdown_name: str,
    dimension: DcdColumn,
    metric_columns: list[DcdColumn],
) -> str:
    quoted_dim = quote_identifier(dimension.name)
    metric_exprs = ", ".join(
        f"{_agg_for(metric)}({quote_identifier(metric.name)}) "
        f"AS {quote_identifier(metric.name)}"
        for metric in metric_columns
    )
    return (
        f"CREATE OR REPLACE TABLE {breakdown_name} AS "
        f"SELECT {quoted_dim}, {metric_exprs}, "
        f"COUNT(*) AS record_count, "
        f"ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_total "
        f"FROM {gold_table} "
        f"GROUP BY {quoted_dim} "
        f"ORDER BY record_count DESC"
    )


def _agg_for(metric: DcdColumn) -> str:
    """Return the aggregation function to use for ``metric``."""
    if metric.aggregation and metric.aggregation.upper() in _VALID_AGGREGATIONS:
        return metric.aggregation.upper()
    return "SUM"
