"""User edits to the Data Context Document.

Accepts a partial DCD override (column role/description changes,
handling tweaks, agent-instruction additions, new verified queries) and
applies it on top of the generated document, then revalidates against
the DuckDB catalog so users cannot introduce references to columns that
do not exist.
"""

from __future__ import annotations

from typing import Any

import duckdb
from pydantic import BaseModel, Field, ValidationError

from src.core.exceptions import DcdValidationError
from src.ingestion.base import validate_identifier
from src.semantic.schema import DataContextDocument, DcdColumn


class DcdColumnEdit(BaseModel):
    """User-supplied override for a single column."""

    name: str
    role: str | None = None
    description: str | None = None
    aggregation: str | None = None
    sensitivity: str | None = None
    handling: str | None = None


class DcdEditRequest(BaseModel):
    """Partial DCD update submitted via ``PUT /datasets/{id}/context``."""

    dataset_name: str | None = None
    dataset_description: str | None = None
    columns: list[DcdColumnEdit] = Field(default_factory=list)
    agent_instructions: list[str] | None = None
    known_limitations: list[str] | None = None


def apply_edits(
    dcd: DataContextDocument,
    edits: DcdEditRequest,
    *,
    connection: duckdb.DuckDBPyConnection | None = None,
    gold_table: str | None = None,
) -> DataContextDocument:
    """Apply ``edits`` on top of ``dcd`` and return a new validated document.

    Args:
        dcd: The original DCD.
        edits: User-supplied partial updates.
        connection: Optional DuckDB connection used to validate that
            edited column names still exist in ``gold_table``.
        gold_table: The Gold table name to validate against. Required
            when ``connection`` is provided.

    Raises:
        DcdValidationError: If an edited column name does not exist in
            the current schema, or if the resulting DCD fails pydantic
            validation.
    """
    existing_columns_by_name: dict[str, DcdColumn] = {
        column.name: column for column in dcd.dataset.columns
    }
    for edit in edits.columns:
        if edit.name not in existing_columns_by_name:
            raise DcdValidationError(f"Unknown column in edit: {edit.name!r}")

    if connection is not None and gold_table is not None:
        _verify_columns_against_catalog(
            connection=connection,
            gold_table=gold_table,
            column_names=[edit.name for edit in edits.columns],
        )

    updated_columns: list[DcdColumn] = []
    edits_by_name = {edit.name: edit for edit in edits.columns}
    for column in dcd.dataset.columns:
        edit = edits_by_name.get(column.name)
        if edit is None:
            updated_columns.append(column)
            continue
        updated_columns.append(
            column.model_copy(
                update={
                    k: v
                    for k, v in {
                        "role": edit.role,
                        "description": edit.description,
                        "aggregation": edit.aggregation,
                        "sensitivity": edit.sensitivity,
                        "handling": edit.handling,
                    }.items()
                    if v is not None
                }
            )
        )

    dataset_updates: dict[str, Any] = {"columns": updated_columns}
    if edits.dataset_name is not None:
        dataset_updates["name"] = edits.dataset_name
    if edits.dataset_description is not None:
        dataset_updates["description"] = edits.dataset_description
    if edits.agent_instructions is not None:
        dataset_updates["agent_instructions"] = edits.agent_instructions
    if edits.known_limitations is not None:
        quality = dcd.dataset.quality.model_copy(
            update={"known_limitations": edits.known_limitations}
        )
        dataset_updates["quality"] = quality

    try:
        new_dataset = dcd.dataset.model_copy(update=dataset_updates)
        return DataContextDocument(version=dcd.version, dataset=new_dataset)
    except ValidationError as exc:
        raise DcdValidationError(f"Edited DCD failed validation: {exc}") from exc


def _verify_columns_against_catalog(
    *,
    connection: duckdb.DuckDBPyConnection,
    gold_table: str,
    column_names: list[str],
) -> None:
    validate_identifier(gold_table)
    rows = connection.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        [gold_table],
    ).fetchall()
    catalog = {row[0] for row in rows}
    missing = [name for name in column_names if name not in catalog]
    if missing:
        raise DcdValidationError(
            f"Columns not present in {gold_table}: {', '.join(missing)}"
        )
