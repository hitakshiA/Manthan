"""Tests for the JSON loader."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from src.core.exceptions import IngestionError
from src.ingestion.loaders.json_loader import JsonLoader


@pytest.fixture
def loader() -> JsonLoader:
    return JsonLoader()


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def sample_json(tmp_path: Path) -> Path:
    path = tmp_path / "sample.json"
    records = [
        {"order_id": 1, "region": "North", "revenue": 100.50},
        {"order_id": 2, "region": "South", "revenue": 89.00},
        {"order_id": 3, "region": "East", "revenue": 299.99},
    ]
    path.write_text(json.dumps(records))
    return path


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    path = tmp_path / "sample.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"order_id": 1, "region": "North", "revenue": 100.50},
                {"order_id": 2, "region": "South", "revenue": 89.00},
            ]
        )
    )
    return path


class TestDetect:
    def test_detects_json(self, loader: JsonLoader) -> None:
        assert loader.detect(Path("data.json"))

    def test_detects_jsonl(self, loader: JsonLoader) -> None:
        assert loader.detect(Path("data.jsonl"))

    def test_detects_ndjson(self, loader: JsonLoader) -> None:
        assert loader.detect(Path("data.ndjson"))

    def test_rejects_csv(self, loader: JsonLoader) -> None:
        assert not loader.detect(Path("data.csv"))


class TestLoad:
    def test_loads_json_array(
        self,
        loader: JsonLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_json: Path,
    ) -> None:
        result = loader.load(sample_json, connection, "raw_json")
        assert result.source_type == "json"
        assert result.row_count == 3
        total = connection.execute("SELECT SUM(revenue) FROM raw_json").fetchone()
        assert total is not None
        assert round(total[0], 2) == 489.49

    def test_loads_jsonl(
        self,
        loader: JsonLoader,
        connection: duckdb.DuckDBPyConnection,
        sample_jsonl: Path,
    ) -> None:
        result = loader.load(sample_jsonl, connection, "raw_jsonl")
        assert result.row_count == 2

    def test_wraps_malformed_json(
        self,
        loader: JsonLoader,
        connection: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        bogus = tmp_path / "bad.json"
        bogus.write_text("not json at all {{{")
        with pytest.raises(IngestionError):
            loader.load(bogus, connection, "raw_bad")
