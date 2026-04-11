"""In-memory dataset registry.

Tracks every dataset the data layer has ingested and the stage each one
has reached (``bronze`` after ingestion, ``silver`` after profiling,
``gold`` after materialization). For the hackathon scale this is a simple
dict-backed store; a persistent store (likely SQLite) will replace it once
we support multi-session workflows.

The registry is the single place that assigns ``dataset_id`` values so
that every other module can trust the identifiers they receive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.exceptions import IngestionError
from src.ingestion.base import LoadResult

DatasetStatus = Literal["bronze", "silver", "gold"]

_DATASET_ID_LENGTH = 10


class DatasetEntry(BaseModel):
    """Registry row describing a single dataset."""

    dataset_id: str = Field(..., description="Opaque dataset identifier.")
    load_result: LoadResult = Field(..., description="Bronze-stage load metadata.")
    status: DatasetStatus = Field(default="bronze", description="Pipeline stage.")
    created_at: datetime
    updated_at: datetime


class DatasetRegistry:
    """Process-local registry of loaded datasets."""

    def __init__(self) -> None:
        self._entries: dict[str, DatasetEntry] = {}

    def register(self, load_result: LoadResult) -> DatasetEntry:
        """Assign a ``dataset_id`` and store ``load_result``.

        Returns:
            The newly created :class:`DatasetEntry`.
        """
        dataset_id = f"ds_{uuid4().hex[:_DATASET_ID_LENGTH]}"
        now = datetime.now(UTC)
        entry = DatasetEntry(
            dataset_id=dataset_id,
            load_result=load_result,
            status="bronze",
            created_at=now,
            updated_at=now,
        )
        self._entries[dataset_id] = entry
        return entry

    def get(self, dataset_id: str) -> DatasetEntry:
        """Return the entry for ``dataset_id``.

        Raises:
            IngestionError: If no dataset with that id has been registered.
        """
        entry = self._entries.get(dataset_id)
        if entry is None:
            raise IngestionError(f"Unknown dataset_id: {dataset_id}")
        return entry

    def list_entries(self) -> list[DatasetEntry]:
        """Return every registered entry in insertion order."""
        return list(self._entries.values())

    def delete(self, dataset_id: str) -> None:
        """Remove a dataset from the registry.

        Raises:
            IngestionError: If no dataset with that id has been registered.
        """
        if dataset_id not in self._entries:
            raise IngestionError(f"Unknown dataset_id: {dataset_id}")
        del self._entries[dataset_id]

    def update_status(
        self,
        dataset_id: str,
        status: DatasetStatus,
    ) -> DatasetEntry:
        """Advance a dataset to a new pipeline stage."""
        current = self.get(dataset_id)
        updated = current.model_copy(
            update={"status": status, "updated_at": datetime.now(UTC)},
        )
        self._entries[dataset_id] = updated
        return updated
