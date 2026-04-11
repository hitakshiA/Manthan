"""Tests for src.semantic.editor."""

from __future__ import annotations

import duckdb
import pytest
from src.core.exceptions import DcdValidationError
from src.semantic.editor import DcdColumnEdit, DcdEditRequest, apply_edits
from src.semantic.schema import DataContextDocument


def test_apply_edits_updates_role_and_description(
    sample_dcd: DataContextDocument,
) -> None:
    request = DcdEditRequest(
        columns=[
            DcdColumnEdit(
                name="quantity",
                role="auxiliary",
                description="Units ordered (user correction)",
            )
        ],
        agent_instructions=["Do not share customer emails."],
    )
    updated = apply_edits(sample_dcd, request)
    quantity = next(c for c in updated.dataset.columns if c.name == "quantity")
    assert quantity.role == "auxiliary"
    assert "user correction" in quantity.description
    assert "customer emails" in updated.dataset.agent_instructions[0]


def test_apply_edits_rejects_unknown_column(
    sample_dcd: DataContextDocument,
) -> None:
    request = DcdEditRequest(
        columns=[DcdColumnEdit(name="does_not_exist", role="metric")]
    )
    with pytest.raises(DcdValidationError, match="Unknown column"):
        apply_edits(sample_dcd, request)


def test_apply_edits_validates_against_catalog(
    sample_dcd: DataContextDocument,
    gold_connection: duckdb.DuckDBPyConnection,
) -> None:
    gold_connection.execute("CREATE TABLE gold_sales AS SELECT * FROM raw_sales")
    request = DcdEditRequest(
        columns=[DcdColumnEdit(name="revenue", description="Updated")]
    )
    updated = apply_edits(
        sample_dcd, request, connection=gold_connection, gold_table="gold_sales"
    )
    revenue = next(c for c in updated.dataset.columns if c.name == "revenue")
    assert "Updated" in revenue.description
