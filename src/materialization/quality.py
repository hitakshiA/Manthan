"""Great Expectations quality suite for Gold tables.

Given a :class:`DataContextDocument` and a DuckDB Gold table,
:func:`run_quality_suite` runs a small expectation suite derived from
the DCD (non-null checks on high-completeness columns, value-set checks
on low-cardinality dimensions, numeric range checks on metrics) and
returns a structured pass/fail report.

Great Expectations' newer APIs (v1+) are heavy — we use the simpler
expectations available via the ``gx`` namespace against a pandas
DataFrame exported from DuckDB. This keeps the suite runnable on any
size that fits in memory while avoiding the full EphemeralContext dance.
"""

from __future__ import annotations

from typing import Any

import duckdb
from pydantic import BaseModel, Field

from src.ingestion.base import validate_identifier
from src.semantic.schema import DataContextDocument, DcdColumn

_DEFAULT_MOSTLY = 0.99
_VALUE_SET_SAMPLE_THRESHOLD = 20


class QualityExpectation(BaseModel):
    """One validated expectation."""

    column: str
    expectation: str
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    """Aggregate pass/fail report for a Gold table."""

    table_name: str
    total_expectations: int
    successful: int
    success_percent: float = Field(ge=0.0, le=100.0)
    expectations: list[QualityExpectation] = Field(default_factory=list)


def run_quality_suite(
    connection: duckdb.DuckDBPyConnection,
    gold_table: str,
    dcd: DataContextDocument,
) -> QualityReport:
    """Execute a DCD-derived expectation suite against ``gold_table``."""
    validate_identifier(gold_table)
    df = connection.table(gold_table).df()

    expectations: list[QualityExpectation] = []
    for column in dcd.dataset.columns:
        expectations.extend(_expectations_for_column(df, column))

    successful = sum(1 for e in expectations if e.success)
    total = len(expectations)
    percent = (successful / total * 100.0) if total > 0 else 100.0

    return QualityReport(
        table_name=gold_table,
        total_expectations=total,
        successful=successful,
        success_percent=round(percent, 2),
        expectations=expectations,
    )


def _expectations_for_column(df: Any, column: DcdColumn) -> list[QualityExpectation]:
    results: list[QualityExpectation] = []

    if column.name not in df.columns:
        return [
            QualityExpectation(
                column=column.name,
                expectation="expect_column_to_exist",
                success=False,
                details={"error": f"column {column.name!r} missing from Gold table"},
            )
        ]

    series = df[column.name]
    total = len(series)

    # Completeness check
    non_null = int(series.notna().sum())
    completeness = non_null / total if total else 1.0
    results.append(
        QualityExpectation(
            column=column.name,
            expectation="expect_column_values_to_not_be_null",
            success=completeness >= _DEFAULT_MOSTLY
            or column.completeness < _DEFAULT_MOSTLY,
            details={"observed": round(completeness, 4), "mostly": _DEFAULT_MOSTLY},
        )
    )

    # Value set check for small dimensions
    if (
        column.role == "dimension"
        and column.cardinality is not None
        and column.cardinality <= _VALUE_SET_SAMPLE_THRESHOLD
        and column.sample_values
    ):
        expected_set = {str(v) for v in column.sample_values if v is not None}
        observed = {str(v) for v in series.dropna().unique()}
        unexpected = observed - expected_set
        results.append(
            QualityExpectation(
                column=column.name,
                expectation="expect_column_values_to_be_in_set",
                success=not unexpected,
                details={
                    "expected_set_size": len(expected_set),
                    "unexpected_count": len(unexpected),
                },
            )
        )

    # Numeric range check for metrics with recorded stats
    if (
        column.role == "metric"
        and column.stats is not None
        and column.stats.min is not None
        and column.stats.max is not None
    ):
        try:
            numeric = series.dropna().astype(float)
        except (ValueError, TypeError):
            numeric = None
        if numeric is not None and not numeric.empty:
            observed_min = float(numeric.min())
            observed_max = float(numeric.max())
            slack = (float(column.stats.max) - float(column.stats.min)) * 0.01 + 1e-9
            within = (
                observed_min >= float(column.stats.min) - slack
                and observed_max <= float(column.stats.max) + slack
            )
            results.append(
                QualityExpectation(
                    column=column.name,
                    expectation="expect_column_values_to_be_between",
                    success=within,
                    details={
                        "observed_min": observed_min,
                        "observed_max": observed_max,
                        "expected_min": float(column.stats.min),
                        "expected_max": float(column.stats.max),
                    },
                )
            )

    return results
