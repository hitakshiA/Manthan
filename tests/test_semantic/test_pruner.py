"""Tests for src.semantic.pruner."""

from __future__ import annotations

from datetime import UTC, datetime

from src.semantic.pruner import prune_for_query
from src.semantic.schema import (
    DataContextDocument,
    DcdColumn,
    DcdDataset,
    DcdSource,
)


def _make_dcd(columns: list[DcdColumn]) -> DataContextDocument:
    dataset = DcdDataset(
        id="ds_test",
        name="Test",
        description="test dataset",
        source=DcdSource(
            type="csv",
            original_filename="t.csv",
            ingested_at=datetime.now(UTC),
            row_count=100,
        ),
        columns=columns,
    )
    return DataContextDocument(dataset=dataset)


def _col(name: str, role: str = "dimension", description: str = "") -> DcdColumn:
    return DcdColumn(
        name=name,
        dtype="VARCHAR",
        role=role,
        description=description or f"{name} column",
    )


def test_small_dcd_returned_unchanged() -> None:
    dcd = _make_dcd([_col("a"), _col("b"), _col("c")])
    pruned = prune_for_query(dcd, "total of b", max_columns=30)
    assert [c.name for c in pruned.dataset.columns] == ["a", "b", "c"]


def test_large_dcd_keeps_relevant_columns() -> None:
    columns = [_col(f"col_{i:03d}") for i in range(50)]
    columns[0] = _col("revenue", role="metric")
    columns[25] = _col(
        "region",
        role="dimension",
        description="Sales region identifier",
    )
    dcd = _make_dcd(columns)
    pruned = prune_for_query(dcd, "revenue by region", max_columns=10)

    assert len(pruned.dataset.columns) == 10
    kept = {c.name for c in pruned.dataset.columns}
    assert "revenue" in kept  # metric force-kept
    assert "region" in kept  # token match


def test_metric_columns_are_force_kept() -> None:
    columns = [_col(f"dim_{i}") for i in range(40)]
    columns.append(_col("total_sales", role="metric"))
    dcd = _make_dcd(columns)
    pruned = prune_for_query(dcd, "unrelated question", max_columns=5)
    assert "total_sales" in {c.name for c in pruned.dataset.columns}
