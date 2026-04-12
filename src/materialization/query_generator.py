"""Verified query generation.

Deterministically produces 8-12 known-correct natural-language ↔ SQL
pairs covering the four core use-case types from the problem
statement (SPEC §3.4): change, comparison, breakdown, summary. The
pairs are SQL-generated from the DCD schema, not the LLM, so they are
always correct against the Gold table.

These verified queries serve two purposes: they are embedded in the
DCD so downstream analysis agents can use them as few-shot examples,
and they form the seed test set for the E2E verification of the data
layer.
"""

from __future__ import annotations

import duckdb

from src.ingestion.base import quote_identifier, sanitize_for_identifier
from src.materialization.summarizer import filter_numeric_metrics
from src.semantic.schema import DataContextDocument, DcdColumn, DcdVerifiedQuery

_MIN_PAIRS = 6


def generate_verified_queries(
    dcd: DataContextDocument,
    *,
    gold_table: str,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> list[DcdVerifiedQuery]:
    """Return a set of verified question-SQL pairs for ``gold_table``.

    Each returned query uses quoted identifiers so arbitrary column
    names work. The SQL targets ``gold_table`` directly — it is the
    caller's responsibility to ensure the table exists.

    When ``connection`` is provided, metric columns whose actual Gold
    dtype is non-numeric (e.g. VARCHAR because the source CSV used
    ``NA`` sentinels) are filtered out so the generated queries never
    emit ``SUM`` on a string column.
    """
    metric_columns = [c for c in dcd.dataset.columns if c.role == "metric"]
    dimension_columns = [c for c in dcd.dataset.columns if c.role == "dimension"]
    temporal_column = dcd.dataset.temporal.column

    if connection is not None and metric_columns:
        metric_columns = filter_numeric_metrics(connection, gold_table, metric_columns)

    if not metric_columns:
        return []

    primary_metric = metric_columns[0]
    pairs: list[DcdVerifiedQuery] = []

    # Breakdown: metric by each dimension.
    for dimension in dimension_columns:
        pairs.append(_breakdown(gold_table, primary_metric, dimension))

    # Summary: total of every metric (no grouping).
    pairs.append(_total_summary(gold_table, metric_columns))

    # Trend: monthly rollup of the primary metric if temporal column exists.
    if temporal_column:
        pairs.append(_trend(gold_table, primary_metric, temporal_column))
        pairs.append(_change_last_vs_prior(gold_table, primary_metric, temporal_column))

    # Comparison: top dimension value vs all others, if we have a dimension.
    if dimension_columns:
        pairs.append(
            _comparison_top_vs_rest(gold_table, primary_metric, dimension_columns[0])
        )

    # Ensure we return at least _MIN_PAIRS by padding with per-dimension
    # record counts when needed.
    if len(pairs) < _MIN_PAIRS:
        for dimension in dimension_columns:
            if len(pairs) >= _MIN_PAIRS:
                break
            pairs.append(_record_count_by_dimension(gold_table, dimension))

    return pairs


def _breakdown(
    gold_table: str, metric: DcdColumn, dimension: DcdColumn
) -> DcdVerifiedQuery:
    agg = _agg(metric)
    dim_alias = sanitize_for_identifier(dimension.name)
    metric_alias = f"total_{sanitize_for_identifier(metric.name)}"
    sql = (
        f"SELECT {quote_identifier(dimension.name)} AS {dim_alias}, "
        f"{agg}({quote_identifier(metric.name)}) AS {metric_alias} "
        f"FROM {gold_table} "
        f"GROUP BY {quote_identifier(dimension.name)} "
        f"ORDER BY {metric_alias} DESC"
    )
    return DcdVerifiedQuery(
        question=f"What is the total {metric.name} by {dimension.name}?",
        sql=sql,
        intent="breakdown",
    )


def _total_summary(gold_table: str, metrics: list[DcdColumn]) -> DcdVerifiedQuery:
    def _metric_select(metric: DcdColumn) -> str:
        alias = f"total_{sanitize_for_identifier(metric.name)}"
        return f"{_agg(metric)}({quote_identifier(metric.name)}) AS {alias}"

    selects = ", ".join(_metric_select(m) for m in metrics)
    sql = f"SELECT {selects} FROM {gold_table}"
    return DcdVerifiedQuery(
        question=f"Show a summary of {', '.join(m.name for m in metrics)}.",
        sql=sql,
        intent="summary",
    )


def _trend(
    gold_table: str, metric: DcdColumn, temporal_column: str
) -> DcdVerifiedQuery:
    agg = _agg(metric)
    metric_alias = f"monthly_{sanitize_for_identifier(metric.name)}"
    sql = (
        f"SELECT DATE_TRUNC('month', {quote_identifier(temporal_column)}) AS month, "
        f"{agg}({quote_identifier(metric.name)}) AS {metric_alias} "
        f"FROM {gold_table} "
        f"GROUP BY 1 "
        f"ORDER BY 1"
    )
    return DcdVerifiedQuery(
        question=f"How has {metric.name} changed over time?",
        sql=sql,
        intent="trend",
    )


def _change_last_vs_prior(
    gold_table: str, metric: DcdColumn, temporal_column: str
) -> DcdVerifiedQuery:
    agg = _agg(metric)
    sql = (
        f"WITH months AS ("
        f"  SELECT DATE_TRUNC('month', {quote_identifier(temporal_column)}) AS month, "
        f"  {agg}({quote_identifier(metric.name)}) AS amount "
        f"  FROM {gold_table} GROUP BY 1"
        f") "
        f"SELECT month, amount, "
        f"LAG(amount) OVER (ORDER BY month) AS previous_amount, "
        f"amount - LAG(amount) OVER (ORDER BY month) AS change "
        f"FROM months ORDER BY month"
    )
    return DcdVerifiedQuery(
        question=f"What is the month-over-month change in {metric.name}?",
        sql=sql,
        intent="change",
    )


def _comparison_top_vs_rest(
    gold_table: str, metric: DcdColumn, dimension: DcdColumn
) -> DcdVerifiedQuery:
    agg = _agg(metric)
    dim_alias = sanitize_for_identifier(dimension.name)
    sql = (
        f"SELECT {quote_identifier(dimension.name)} AS {dim_alias}, "
        f"{agg}({quote_identifier(metric.name)}) AS total "
        f"FROM {gold_table} "
        f"GROUP BY {quote_identifier(dimension.name)} "
        f"ORDER BY total DESC "
        f"LIMIT 5"
    )
    return DcdVerifiedQuery(
        question=f"Which {dimension.name} values have the highest {metric.name}?",
        sql=sql,
        intent="comparison",
    )


def _record_count_by_dimension(
    gold_table: str, dimension: DcdColumn
) -> DcdVerifiedQuery:
    dim_alias = sanitize_for_identifier(dimension.name)
    sql = (
        f"SELECT {quote_identifier(dimension.name)} AS {dim_alias}, "
        f"COUNT(*) AS record_count "
        f"FROM {gold_table} "
        f"GROUP BY {quote_identifier(dimension.name)} "
        f"ORDER BY record_count DESC"
    )
    return DcdVerifiedQuery(
        question=f"How many records per {dimension.name}?",
        sql=sql,
        intent="breakdown",
    )


def _agg(metric: DcdColumn) -> str:
    if metric.aggregation and metric.aggregation.upper() in {
        "SUM",
        "AVG",
        "COUNT",
        "MIN",
        "MAX",
    }:
        return metric.aggregation.upper()
    return "SUM"
