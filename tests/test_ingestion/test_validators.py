"""Tests for ingestion.validators."""

from pathlib import Path

import pytest
from src.core.exceptions import IngestionError
from src.ingestion.validators import validate_file


def test_validates_existing_non_empty_file(sample_csv_path: Path) -> None:
    validate_file(sample_csv_path, max_size_mb=500)  # should not raise


def test_raises_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.csv"
    with pytest.raises(IngestionError, match="does not exist"):
        validate_file(missing, max_size_mb=500)


def test_raises_for_directory(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="not a regular file"):
        validate_file(tmp_path, max_size_mb=500)


def test_raises_for_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.touch()
    with pytest.raises(IngestionError, match="empty"):
        validate_file(empty, max_size_mb=500)


def test_raises_when_over_max_size(tmp_path: Path) -> None:
    big = tmp_path / "big.csv"
    big.write_bytes(b"a" * (2 * 1024 * 1024))  # 2 MB
    with pytest.raises(IngestionError, match="exceeds"):
        validate_file(big, max_size_mb=1)
