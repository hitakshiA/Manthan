"""Pydantic schema for the Data Context Document (DCD).

The DCD is Manthan's semantic contract with downstream analysis agents —
a YAML artifact encoding everything about a dataset: columns, metrics,
temporal grain, PII flags, quality caveats, verified queries, and agent
instructions. This module defines the strict shape of that document so
that any change to the DCD surface is visible in one place.

The schema closely follows ``docs/LAYER1_SPEC.md`` but uses pydantic models
instead of free-form YAML so we can validate generated and edited
documents against a single source of truth.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DCD_VERSION = "1.1"


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
    label: str | None = Field(
        default=None,
        description=(
            "Exec-facing display name (e.g. 'Order total' for "
            "``total_price``). When set, the agent prompt renders this "
            "instead of the raw column name and narrative/artifacts "
            "use it in place of the physical identifier."
        ),
    )
    pii: bool = Field(
        default=False,
        description=(
            "If true, this column contains personally-identifiable "
            "information. Agents must aggregate or count — never "
            "enumerate — values from this column."
        ),
    )
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
    """A derived metric with an explicit formula.

    Kept for backward compatibility with v1.0 DCDs. New work should
    prefer :class:`DcdMetric`, which carries the filter, aggregation
    semantics, and grain contract that make metrics reusable and
    auditable across the agent's `compute_metric` path.
    """

    name: str
    formula: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class DcdMetric(BaseModel):
    """A governed, named business metric — the atomic unit of trust.

    Unlike :class:`DcdComputedMetric` (whose ``formula`` is plain text
    and never executed), a ``DcdMetric`` is a prescriptive contract:
    exactly how the metric is computed, what filters are baked in,
    what grains it aggregates safely over, and which dimensions are
    valid slices. The agent's ``compute_metric`` tool composes SQL
    directly from this definition, so every invocation of
    "revenue" or "churn rate" resolves to the same SQL whether
    surfaced in a chart, a brief, or a board-ready number.

    Filter semantics: when ``filter`` is set (e.g. ``status =
    'delivered'``), it is ALWAYS applied. An agent cannot produce
    "revenue" without the filter — the validator rejects such queries.

    Aggregation semantics classify whether the metric can be SUMmed
    across slices without producing nonsense:

        * ``additive`` — SUM across any combination of dimensions is
          valid. Typical of counts, totals, row-level monetary fields.
        * ``ratio_unsafe`` — the metric is a ratio or average. SUMming
          across slices is WRONG; the ratio must be re-computed from
          its numerator and denominator.
        * ``non_additive`` — the metric is distinct-count-like or uses
          HyperLogLog; SUM is wrong for a different reason (the
          distinct space collapses).

    Grain contracts: ``default_grain`` specifies the grain at which
    the metric is intended to be reported; ``valid_dimensions`` whitelists
    the dimensions the metric is safe to slice by. Queries outside these
    bounds are flagged by the validator.
    """

    slug: str = Field(
        ...,
        description=(
            "Stable identifier used by the agent (``revenue``, ``aov``). "
            "Must be unique within the entity."
        ),
    )
    label: str = Field(
        ...,
        description="Exec-facing display name (e.g. 'Revenue', 'AOV').",
    )
    description: str = Field(
        default="",
        description=(
            "One-sentence business definition injected into the "
            "agent prompt so it can pick the right metric by intent."
        ),
    )
    expression: str = Field(
        ...,
        description=(
            "SQL aggregation expression, e.g. ``SUM(subtotal)`` or "
            "``SUM(subtotal) / COUNT(DISTINCT order_id)``. Must be a "
            "valid expression against the entity's physical table."
        ),
    )
    filter: str | None = Field(
        default=None,
        description=(
            "Optional SQL predicate ALWAYS applied when the metric is "
            "computed (e.g. ``status = 'delivered'``). The validator "
            "rejects queries that compute the metric's expression "
            "without this filter."
        ),
    )
    unit: str | None = Field(
        default=None,
        description="Display unit (USD, percent, count, days, ...)",
    )
    aggregation_semantics: str = Field(
        default="additive",
        description=(
            "How the metric composes across slices: ``additive`` | "
            "``ratio_unsafe`` | ``non_additive``."
        ),
    )
    default_grain: str | None = Field(
        default=None,
        description=(
            "Preferred time grain for reporting (``daily``, ``weekly``, "
            "``monthly``, ``quarterly``, ``yearly``). ``None`` means "
            "grain-agnostic."
        ),
    )
    valid_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Whitelist of dimensions this metric is safe to slice by. "
            "Empty means all declared dimensions of the entity are valid."
        ),
    )
    synonyms: list[str] = Field(
        default_factory=list,
        description=(
            "Alternative natural-language names the agent can recognize "
            "as referring to this metric (e.g. ``sales`` -> ``revenue``)."
        ),
    )


class DcdRollup(BaseModel):
    """Pre-materialized aggregation pointer for an entity.

    Layer 1 materializes common rollups (daily, monthly, by-status,
    by-region, etc.) as physical tables during ingestion. Each
    ``DcdRollup`` tells the agent what physical table serves a
    particular slice so queries can hit the rollup instead of
    scanning the full table.
    """

    slug: str = Field(
        ...,
        description=(
            "Rollup identifier within the entity (``by_status``, "
            "``daily``, ``monthly``)."
        ),
    )
    physical_table: str = Field(
        ...,
        description=(
            "The actual table name in DuckDB. Opaque to the agent; "
            "referenced only through the entity slug."
        ),
    )
    grain: str | None = Field(
        default=None,
        description="Time grain, if temporal: ``daily`` / ``monthly`` / etc.",
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions pre-aggregated in this rollup.",
    )


class DcdEntity(BaseModel):
    """Stable, business-facing entity wrapper over physical tables.

    The entity is the agent's — and exec's — handle on a dataset.
    The ``slug`` is stable across re-ingests; the ``physical_table``
    pointer rotates atomically when new data arrives. User-authored
    customizations (``name``, ``metrics``, column ``label`` /
    ``synonyms`` / ``pii``) survive re-ingestion because they live
    on the entity, not the physical table.

    Rollups are indexed by slug for O(1) lookup during query
    composition. Metrics are the governed happy-path the agent
    reaches for before writing raw SQL.
    """

    slug: str = Field(
        ...,
        description=(
            "Stable identifier (``orders``, ``funding``). Exec-editable "
            "once at ingest; immutable thereafter. Used in prompt "
            "output, tool calls, and lineage events."
        ),
    )
    name: str = Field(
        ...,
        description="Exec-facing display name (``Orders``, ``Startup Funding``).",
    )
    description: str = Field(
        default="",
        description="One-paragraph business context for the agent prompt.",
    )
    physical_table: str = Field(
        ...,
        description=(
            "Current Gold table backing this entity. Rotates on "
            "re-ingest; agent never sees this name directly."
        ),
    )
    rollups: list[DcdRollup] = Field(
        default_factory=list,
        description="Pre-materialized aggregate tables.",
    )
    metrics: list[DcdMetric] = Field(
        default_factory=list,
        description="Governed business metrics, reachable via `compute_metric`.",
    )


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

    The ``entity`` field (added in DCD v1.1) wraps the physical
    storage behind a stable business-facing slug + display name +
    governed metrics. When present, it becomes the agent's primary
    handle on the dataset; the ``id`` / legacy table names remain
    for backward compatibility but never surface to the exec.
    """

    id: str
    name: str
    description: str
    source: DcdSource
    entity: DcdEntity | None = Field(
        default=None,
        description=(
            "Business-facing entity wrapper. Populated in DCD v1.1+; "
            "older documents leave this null and fall back to raw "
            "table names. A migration pass upgrades legacy DCDs on "
            "first boot."
        ),
    )
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
