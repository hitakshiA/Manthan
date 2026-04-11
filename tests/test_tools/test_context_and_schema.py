"""Tests for src.tools.context_tool and src.tools.schema_tool."""

from __future__ import annotations

from src.semantic.schema import DataContextDocument
from src.tools.context_tool import get_context
from src.tools.schema_tool import get_schema


def test_get_context_returns_yaml(sample_dcd: DataContextDocument) -> None:
    yaml_text = get_context(sample_dcd)
    assert "dataset:" in yaml_text
    assert "revenue" in yaml_text


def test_get_context_prunes_when_query_provided(
    sample_dcd: DataContextDocument,
) -> None:
    # Pruning only kicks in for DCDs with > max_columns columns; sample
    # has 6 columns so it stays full-size. We still verify the code
    # path runs and returns a valid YAML body.
    yaml_text = get_context(sample_dcd, query="revenue by region")
    assert "dataset:" in yaml_text


def test_get_schema_summary_structure(
    sample_dcd: DataContextDocument,
) -> None:
    schema = get_schema(sample_dcd)
    assert schema.dataset_id == "ds_test000001"
    assert schema.row_count == 10
    names = {c.name for c in schema.columns}
    assert {"revenue", "region", "order_date"}.issubset(names)


def test_get_schema_includes_verified_queries(
    sample_dcd: DataContextDocument,
) -> None:
    # sample_dcd has no verified queries by default; the list should
    # still be present and iterable.
    schema = get_schema(sample_dcd)
    assert isinstance(schema.verified_queries, list)
