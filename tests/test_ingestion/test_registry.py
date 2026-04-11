"""Tests for ingestion.registry."""

from datetime import UTC, datetime

import pytest
from src.core.exceptions import IngestionError
from src.ingestion.base import LoadResult
from src.ingestion.registry import DatasetRegistry


def _make_load_result(filename: str = "sample.csv") -> LoadResult:
    return LoadResult(
        table_name="raw_sample",
        source_type="csv",
        original_filename=filename,
        ingested_at=datetime.now(UTC),
        row_count=10,
        column_count=3,
        raw_size_bytes=256,
    )


def test_register_assigns_unique_dataset_id() -> None:
    registry = DatasetRegistry()
    first = registry.register(_make_load_result("a.csv"))
    second = registry.register(_make_load_result("b.csv"))
    assert first.dataset_id != second.dataset_id
    assert first.dataset_id.startswith("ds_")
    assert first.status == "bronze"


def test_register_stores_load_result() -> None:
    registry = DatasetRegistry()
    entry = registry.register(_make_load_result("orders.csv"))
    assert entry.load_result.original_filename == "orders.csv"
    assert entry.load_result.row_count == 10


def test_get_returns_registered_entry() -> None:
    registry = DatasetRegistry()
    entry = registry.register(_make_load_result())
    retrieved = registry.get(entry.dataset_id)
    assert retrieved.dataset_id == entry.dataset_id


def test_get_raises_for_unknown_id() -> None:
    registry = DatasetRegistry()
    with pytest.raises(IngestionError, match="Unknown dataset_id"):
        registry.get("ds_nonexistent")


def test_list_entries_preserves_insertion_order() -> None:
    registry = DatasetRegistry()
    first = registry.register(_make_load_result("a.csv"))
    second = registry.register(_make_load_result("b.csv"))
    entries = registry.list_entries()
    assert [e.dataset_id for e in entries] == [first.dataset_id, second.dataset_id]


def test_delete_removes_entry() -> None:
    registry = DatasetRegistry()
    entry = registry.register(_make_load_result())
    registry.delete(entry.dataset_id)
    assert registry.list_entries() == []


def test_delete_raises_for_unknown_id() -> None:
    registry = DatasetRegistry()
    with pytest.raises(IngestionError):
        registry.delete("ds_nonexistent")


def test_update_status_advances_stage() -> None:
    registry = DatasetRegistry()
    entry = registry.register(_make_load_result())
    before = entry.updated_at
    updated = registry.update_status(entry.dataset_id, "silver")
    assert updated.status == "silver"
    assert updated.updated_at >= before
    # Subsequent get sees the new status
    assert registry.get(entry.dataset_id).status == "silver"
