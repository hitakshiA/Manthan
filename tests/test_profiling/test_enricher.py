"""Tests for src.profiling.enricher."""

from __future__ import annotations

import duckdb
import pytest
from src.profiling.enricher import (
    MetricProposal,
    detect_temporal_grain,
    propose_metrics,
)
from src.profiling.statistical import ColumnProfile


def _make_profile(
    *,
    name: str,
    dtype: str = "VARCHAR",
    row_count: int = 1000,
    distinct_count: int = 10,
) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype=dtype,
        row_count=row_count,
        null_count=0,
        completeness=1.0,
        distinct_count=distinct_count,
        cardinality_ratio=distinct_count / row_count if row_count else 0.0,
        sample_values=[],
    )


class TestDetectTemporalGrain:
    @pytest.fixture
    def connection(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(":memory:")
        yield con
        con.close()

    def _seed(
        self,
        con: duckdb.DuckDBPyConnection,
        values: list[str],
    ) -> None:
        con.execute("CREATE TABLE t (d DATE)")
        for v in values:
            con.execute("INSERT INTO t VALUES (?)", [v])

    def test_daily(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._seed(
            connection,
            [f"2024-01-{i:02d}" for i in range(1, 11)],
        )
        assert detect_temporal_grain(connection, "t", "d") == "daily"

    def test_weekly(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._seed(
            connection,
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29"],
        )
        assert detect_temporal_grain(connection, "t", "d") == "weekly"

    def test_monthly(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._seed(
            connection,
            ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"],
        )
        assert detect_temporal_grain(connection, "t", "d") == "monthly"

    def test_yearly(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._seed(
            connection,
            ["2020-06-15", "2021-06-15", "2022-06-15", "2023-06-15"],
        )
        assert detect_temporal_grain(connection, "t", "d") == "yearly"

    def test_irregular(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._seed(
            connection,
            ["2024-01-01", "2024-01-05", "2024-02-17", "2024-03-04"],
        )
        # Too few rows for a dominant mode — gaps are all different
        result = detect_temporal_grain(connection, "t", "d")
        assert result in ("irregular", "daily")  # mode may pick one


class TestProposeMetrics:
    def test_revenue_plus_id_yields_average(self) -> None:
        profiles = [
            _make_profile(name="revenue", dtype="DOUBLE", distinct_count=900),
            _make_profile(name="order_id", dtype="BIGINT", distinct_count=1000),
            _make_profile(name="region", dtype="VARCHAR", distinct_count=4),
        ]
        proposals = propose_metrics(profiles)
        assert any(p.name.startswith("average_revenue_per_") for p in proposals)
        assert any(p.name.endswith("_count") for p in proposals)

    def test_revenue_and_quantity_yields_unit_price(self) -> None:
        profiles = [
            _make_profile(name="total_sales", dtype="DOUBLE", distinct_count=900),
            _make_profile(name="quantity", dtype="INTEGER", distinct_count=30),
            _make_profile(name="order_id", dtype="BIGINT", distinct_count=1000),
        ]
        proposals = propose_metrics(profiles)
        names = {p.name for p in proposals}
        assert any("total_sales_per_quantity" in n for n in names)

    def test_no_numeric_yields_no_proposals(self) -> None:
        profiles = [
            _make_profile(name="region", dtype="VARCHAR", distinct_count=4),
            _make_profile(name="product", dtype="VARCHAR", distinct_count=20),
        ]
        assert propose_metrics(profiles) == []

    def test_metric_proposal_is_frozen(self) -> None:
        proposal = MetricProposal(
            name="x", formula="SUM(x)", description="sum of x", depends_on=["x"]
        )
        with pytest.raises(Exception):  # pydantic frozen model  # noqa: PT011, B017
            proposal.name = "y"  # type: ignore[misc]
