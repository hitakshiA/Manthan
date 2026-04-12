"""Unit tests for :mod:`src.core.memory`."""

from __future__ import annotations

from pathlib import Path

import pytest
from src.core.memory import MemoryError, MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "agent_memory.db")


def test_put_and_get_roundtrip(store: MemoryStore) -> None:
    entry = store.put(
        scope_type="dataset",
        scope_id="ds_123",
        key="active_user_definition",
        value={"window_days": 30, "verb": "signed_in"},
        category="definition",
        description="Business definition of active user",
    )

    fetched = store.get(
        scope_type="dataset", scope_id="ds_123", key="active_user_definition"
    )

    assert fetched is not None
    assert fetched.value == entry.value
    assert fetched.category == "definition"
    assert fetched.description == "Business definition of active user"


def test_put_updates_existing_entry(store: MemoryStore) -> None:
    store.put(scope_type="user", scope_id="u1", key="currency", value="USD")
    store.put(scope_type="user", scope_id="u1", key="currency", value="GBP")

    entries = store.list_scope(scope_type="user", scope_id="u1")
    assert len(entries) == 1
    assert entries[0].value == "GBP"


def test_list_scope_filters_by_category(store: MemoryStore) -> None:
    store.put(scope_type="dataset", scope_id="d", key="k1", value=1, category="caveat")
    store.put(scope_type="dataset", scope_id="d", key="k2", value=2, category="fact")
    caveats = store.list_scope(scope_type="dataset", scope_id="d", category="caveat")
    assert [e.key for e in caveats] == ["k1"]


def test_delete(store: MemoryStore) -> None:
    store.put(scope_type="global", scope_id="*", key="fiscal_year_start", value="04-01")
    assert store.delete(scope_type="global", scope_id="*", key="fiscal_year_start")
    assert not store.delete(scope_type="global", scope_id="*", key="fiscal_year_start")


def test_search_by_key_substring(store: MemoryStore) -> None:
    store.put(scope_type="user", scope_id="u1", key="timezone_pref", value="UTC")
    store.put(scope_type="user", scope_id="u1", key="colour", value="blue")
    hits = store.search(query="timezone")
    assert len(hits) == 1
    assert hits[0].key == "timezone_pref"


def test_drop_scope(store: MemoryStore) -> None:
    for i in range(3):
        store.put(scope_type="session", scope_id="s1", key=f"k{i}", value=i)
    assert store.drop_scope(scope_type="session", scope_id="s1") == 3
    assert store.list_scope(scope_type="session", scope_id="s1") == []


def test_invalid_scope_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryError):
        store.put(scope_type="bogus", scope_id="x", key="k", value=1)


def test_invalid_category_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryError):
        store.put(
            scope_type="dataset", scope_id="d", key="k", value=1, category="weird"
        )


def test_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "agent_memory.db"
    store1 = MemoryStore(path)
    store1.put(scope_type="global", scope_id="*", key="env", value="prod")

    store2 = MemoryStore(path)
    entry = store2.get(scope_type="global", scope_id="*", key="env")
    assert entry is not None
    assert entry.value == "prod"
