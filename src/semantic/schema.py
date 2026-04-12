"""Pydantic schema for the Data Context Document (DCD).

The DCD is Manthan's semantic contract with downstream analysis agents —
a YAML artifact encoding everything about a dataset: columns, metrics,
temporal grain, PII flags, quality caveats, verified queries, and agent
instructions. This module defines the strict shape of that document so
that any change to the DCD surface is visible in one place.

The schema closely follows SPEC.md §2 (ADR-004) but uses pydantic models
instead of free-form YAML so we can validate generated and edited
documents against a single source of truth.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DCD_VERSION = "1.0"


class DcdSource(BaseModel):
    """Where the raw data came from."""

    type: str = Field(..., description="Source type: csv, parquet, postgres, ...")
    original_filename: str
    ingested_at: datetime
    row_count: int = Field(ge=0)
    raw_size_bytes: int | None = Field(default=None, ge=0)


class DcdTemporalRange(BaseModel):
    """Inclusive date range covered by the temporal column, if any."""

    start: date | None = None
    end: date | None = None


class DcdTemporal(BaseModel):
    """Temporal dimension metadata."""

    grain: str | None = None
    column: str | None = None
    range: DcdTemporalRange = Field(default_factory=DcdTemporalRange)
    timezone: str = "UTC"


class DcdColumnStats(BaseModel):
    """Numeric statistics for a single column."""

    min: Any = None
    max: Any = None
    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    p25: float | None = None
    p75: float | None = None


class DcdColumn(BaseModel):
    """Complete semantic and statistical description of a column.

    Column sensitivity is expressed through ``role`` rather than a
    separate PII classification: columns tagged ``identifier`` (like
    customer_name or order_id) should never be enumerated individually
    in analysis-agent outputs. Analysis agents aggregate or count them
    instead.

    The ``hierarchy``, ``synonyms``, ``classification_reasoning``, and
    ``classification_confidence`` fields give the downstream agent
    richer context for deciding how to interpret a user's phrasing and
    how confident to sound when citing a column in an answer.
    """

    name: str
    dtype: str
    role: str = Field(
        ...,
        description="metric | dimension | temporal | identifier | auxiliary",
    )
    description: str
    aggregation: str | None = None
    nullable: bool = True
    completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    cardinality: int | None = Field(default=None, ge=0)
    stats: DcdColumnStats | None = None
    sample_values: list[Any] = Field(default_factory=list)
    hierarchy: list[str] | None = Field(
        default=None,
        description=(
            "Drill-up path for dimension columns, e.g. "
            "city -> ['state', 'country']. Detected from functional "
            "dependencies during the Silver stage."
        ),
    )
    synonyms: list[str] = Field(
        default_factory=list,
        description="User-facing aliases (e.g. 'sales' for 'revenue').",
    )
    classification_reasoning: str | None = Field(
        default=None,
        description="One-sentence explanation of why this role was chosen.",
    )
    classification_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Classifier self-reported confidence in this role.",
    )


class DcdComputedMetric(BaseModel):
    """A derived metric with an explicit formula."""

    name: str
    formula: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class DcdTable(BaseModel):
    """One table inside a multi-table dataset.

    Used when a dataset is loaded from multiple related files (orders,
    customers, products). Each table carries its own columns, row
    count, and optional temporal metadata. Relationships between
    tables live in :attr:`DcdDataset.relationships`.
    """

    name: str
    description: str
    row_count: int = Field(ge=0)
    columns: list[DcdColumn]
    temporal: DcdTemporal | None = None


class DcdRelationship(BaseModel):
    """A detected or declared join between two tables."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    kind: str = Field(
        default="foreign_key",
        description="foreign_key | lookup | many_to_one | one_to_one",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DcdQualityFreshness(BaseModel):
    """Freshness indicators for the dataset."""

    last_record_date: date | None = None
    expected_frequency: str | None = None
    status: str = "unknown"


class DcdQualityCompletenessDetail(BaseModel):
    """One partially-complete column with an optional note."""

    column: str
    completeness: float = Field(ge=0.0, le=1.0)
    note: str | None = None


class DcdQualityCompleteness(BaseModel):
    """Aggregate completeness view."""

    fully_complete_columns: int = 0
    partial_columns: int = 0
    details: list[DcdQualityCompletenessDetail] = Field(default_factory=list)


class DcdQuality(BaseModel):
    """Data-quality indicators surfaced to downstream agents."""

    overall_score: float = Field(default=1.0, ge=0.0, le=1.0)
    freshness: DcdQualityFreshness = Field(default_factory=DcdQualityFreshness)
    completeness: DcdQualityCompleteness = Field(default_factory=DcdQualityCompleteness)
    known_limitations: list[str] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)


class DcdVerifiedQuery(BaseModel):
    """Known-correct natural-language ↔ SQL pair for few-shot prompting."""

    question: str
    sql: str
    intent: str = Field(
        ..., description="breakdown | trend | comparison | change | summary"
    )


class DcdDataset(BaseModel):
    """The dataset body of a Data Context Document.

    Single-file datasets populate ``columns`` directly and leave
    ``tables`` empty. Multi-file datasets populate ``tables`` with an
    entry per uploaded file; ``columns`` then holds the primary
    table's columns as a backward-compatibility shortcut, and
    ``relationships`` carries the detected joins.
    """

    id: str
    name: str
    description: str
    source: DcdSource
    temporal: DcdTemporal = Field(default_factory=DcdTemporal)
    columns: list[DcdColumn]
    computed_metrics: list[DcdComputedMetric] = Field(default_factory=list)
    tables: list[DcdTable] = Field(default_factory=list)
    relationships: list[DcdRelationship] = Field(default_factory=list)
    quality: DcdQuality = Field(default_factory=DcdQuality)
    verified_queries: list[DcdVerifiedQuery] = Field(default_factory=list)
    agent_instructions: list[str] = Field(default_factory=list)
    profiler_mode: str = Field(
        default="llm",
        description=(
            "How the column classifications were produced: "
            "'llm' (OpenRouter model), 'heuristic' (deterministic "
            "fallback when LLM unavailable), or 'mixed' (some "
            "columns LLM, some heuristic)."
        ),
    )


class DataContextDocument(BaseModel):
    """Top-level DCD envelope."""

    model_config = ConfigDict(validate_assignment=True)

    version: str = _DCD_VERSION
    dataset: DcdDataset

    def to_yaml(self) -> str:
        """Serialize the DCD to a YAML string."""
        payload = self.model_dump(mode="json", exclude_none=False)
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, text: str) -> DataContextDocument:
        """Parse and validate a YAML DCD document."""
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            msg = "DCD YAML must decode to a mapping at the top level"
            raise ValueError(msg)
        return cls.model_validate(data)
