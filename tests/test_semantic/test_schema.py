"""Tests for src.semantic.schema (DCD serialization round-trip)."""

from __future__ import annotations

from src.semantic.schema import DataContextDocument


def test_yaml_round_trip(sample_dcd: DataContextDocument) -> None:
    yaml_text = sample_dcd.to_yaml()
    assert "dataset:" in yaml_text
    assert "order_date" in yaml_text

    restored = DataContextDocument.from_yaml(yaml_text)
    assert restored.dataset.id == sample_dcd.dataset.id
    assert len(restored.dataset.columns) == len(sample_dcd.dataset.columns)
    assert restored.dataset.temporal.column == sample_dcd.dataset.temporal.column


def test_dcd_preserves_column_roles(sample_dcd: DataContextDocument) -> None:
    roles = {c.name: c.role for c in sample_dcd.dataset.columns}
    assert roles["revenue"] == "metric"
    assert roles["region"] == "dimension"
    assert roles["order_date"] == "temporal"
    assert roles["order_id"] == "identifier"


def test_version_is_fixed(sample_dcd: DataContextDocument) -> None:
    assert sample_dcd.version == "1.0"
