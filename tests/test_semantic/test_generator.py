"""Tests for src.semantic.generator."""

from __future__ import annotations

from src.semantic.schema import DataContextDocument


def test_dataset_metadata_populated(sample_dcd: DataContextDocument) -> None:
    assert sample_dcd.dataset.id == "ds_test000001"
    assert sample_dcd.dataset.source.type == "csv"
    assert sample_dcd.dataset.source.row_count == 10


def test_columns_align_with_classification(
    sample_dcd: DataContextDocument,
) -> None:
    revenue = next(c for c in sample_dcd.dataset.columns if c.name == "revenue")
    assert revenue.role == "metric"
    assert revenue.aggregation == "SUM"
    assert revenue.stats is not None
    assert revenue.stats.mean is not None


def test_temporal_range_inferred(sample_dcd: DataContextDocument) -> None:
    assert sample_dcd.dataset.temporal.column == "order_date"
    assert sample_dcd.dataset.temporal.grain == "daily"
    assert sample_dcd.dataset.temporal.range.start is not None
    assert sample_dcd.dataset.temporal.range.end is not None


def test_quality_reports_freshness(sample_dcd: DataContextDocument) -> None:
    freshness = sample_dcd.dataset.quality.freshness
    assert freshness.last_record_date is not None
    assert freshness.expected_frequency == "daily"
    assert freshness.status == "fresh"


def test_agent_instructions_mention_metrics(
    sample_dcd: DataContextDocument,
) -> None:
    instructions_text = " ".join(sample_dcd.dataset.agent_instructions)
    assert "revenue" in instructions_text
    assert "SUM" in instructions_text


def test_computed_metric_included(sample_dcd: DataContextDocument) -> None:
    names = {m.name for m in sample_dcd.dataset.computed_metrics}
    assert "average_revenue_per_order_id" in names
