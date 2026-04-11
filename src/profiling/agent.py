"""Profiling agent: orchestrates the Silver-stage pipeline.

Runs a deterministic version of the ReAct loop described in SPEC.md
§ADR-005:

1. **PERCEIVE**   — :func:`profile_columns` against the raw table.
2. **CLASSIFY**   — :func:`classify_columns` via the LLM.
3. **ENRICH**     — temporal grain detection and metric proposals.
4. **VALIDATE**   — cross-checks between classifier output and stats.
5. **EMIT**       — a :class:`ProfilingResult` aggregated for the
   semantic layer to turn into a Data Context Document.

Interactive user clarification (``ask_user``) is intentionally not wired
in at this phase; the agent always picks its best deterministic fallback
and surfaces any low-confidence classifications in the ``warnings`` list
so the semantic layer can expose them to the user after the fact.

Column sensitivity is expressed through the LLM's role assignment
(``identifier`` for unique-ish keys like customer_name or order_id), not
through a separate PII pipeline. The analysis agent's job is to never
enumerate individual values of identifier columns when answering
questions — aggregate or count them instead.
"""

from __future__ import annotations

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from src.core.llm import LlmClient
from src.core.logger import get_logger
from src.profiling.classifier import ColumnClassification, classify_columns
from src.profiling.enricher import (
    MetricProposal,
    TemporalGrain,
    detect_hierarchies,
    detect_temporal_grain,
    propose_metrics,
)
from src.profiling.statistical import (
    ColumnProfile,
    is_temporal_type,
    profile_columns,
)

_logger = get_logger()


class ProfilingResult(BaseModel):
    """Everything the Silver stage learned about a dataset."""

    model_config = ConfigDict(frozen=True)

    table_name: str
    column_profiles: list[ColumnProfile]
    classifications: list[ColumnClassification]
    temporal_column: str | None = None
    temporal_grain: TemporalGrain | None = None
    metric_proposals: list[MetricProposal] = Field(default_factory=list)
    hierarchies: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


async def profile_dataset(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    llm_client: LlmClient,
) -> ProfilingResult:
    """Run the full Silver-stage pipeline against ``table_name``."""
    _logger.info("profiling.start", table=table_name)

    profiles = profile_columns(connection, table_name)
    _logger.info("profiling.perceive", table=table_name, columns=len(profiles))

    classifications = await classify_columns(profiles, llm_client)

    temporal_column = _pick_temporal_column(profiles, classifications)
    temporal_grain: TemporalGrain | None = None
    if temporal_column is not None:
        temporal_grain = detect_temporal_grain(connection, table_name, temporal_column)
        _logger.info(
            "profiling.temporal",
            column=temporal_column,
            grain=temporal_grain,
        )

    metric_proposals = propose_metrics(profiles)
    hierarchies = detect_hierarchies(connection, table_name, profiles)
    if hierarchies:
        _logger.info(
            "profiling.hierarchies",
            table=table_name,
            count=len(hierarchies),
        )

    warnings = _validate(profiles, classifications)

    _logger.info(
        "profiling.complete",
        table=table_name,
        metric_proposals=len(metric_proposals),
        hierarchies=len(hierarchies),
        warnings=len(warnings),
    )

    return ProfilingResult(
        table_name=table_name,
        column_profiles=profiles,
        classifications=classifications,
        temporal_column=temporal_column,
        temporal_grain=temporal_grain,
        metric_proposals=metric_proposals,
        hierarchies=hierarchies,
        warnings=warnings,
    )


def _pick_temporal_column(
    profiles: list[ColumnProfile],
    classifications: list[ColumnClassification],
) -> str | None:
    """Return the best candidate temporal column, or ``None``."""
    for classification in classifications:
        if classification.role == "temporal":
            return classification.name
    for profile in profiles:
        if is_temporal_type(profile.dtype):
            return profile.name
    return None


def _validate(
    profiles: list[ColumnProfile],
    classifications: list[ColumnClassification],
) -> list[str]:
    """Return human-readable warnings for any inconsistencies."""
    warnings: list[str] = []
    profile_by_name = {p.name: p for p in profiles}

    for classification in classifications:
        profile = profile_by_name.get(classification.name)
        if profile is None:
            warnings.append(
                f"Classifier returned an unknown column: {classification.name}"
            )
            continue
        if classification.role == "metric" and classification.aggregation is None:
            warnings.append(
                f"Column {classification.name!r} classified as metric "
                "but has no aggregation rule"
            )
        if classification.role == "metric" and not _looks_numeric(profile.dtype):
            warnings.append(
                f"Column {classification.name!r} classified as metric "
                f"but dtype is {profile.dtype}"
            )

    return warnings


def _looks_numeric(dtype: str) -> bool:
    upper = dtype.upper()
    return any(
        token in upper
        for token in ("INT", "BIGINT", "DECIMAL", "DOUBLE", "FLOAT", "REAL", "NUMERIC")
    )
