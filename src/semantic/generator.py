"""Assemble a Data Context Document from Silver-stage outputs.

This module is the hinge between the profiling agent and everything
downstream: it takes a :class:`LoadResult` (Bronze metadata) and a
:class:`ProfilingResult` (Silver profile + classification + PII + enrich)
and produces a fully-populated :class:`DataContextDocument` ready for
materialization, pruning, and serving to analysis agents.

The generator is deterministic. It does no LLM calls of its own — all
semantic content already lives in the profiling result.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.ingestion.base import LoadResult
from src.profiling.agent import ProfilingResult
from src.profiling.classifier import ColumnClassification
from src.profiling.pii_detector import PiiFlag
from src.profiling.statistical import (
    ColumnProfile,
    is_numeric_type,
)
from src.semantic.schema import (
    DataContextDocument,
    DcdColumn,
    DcdColumnStats,
    DcdComputedMetric,
    DcdDataset,
    DcdQuality,
    DcdQualityCompleteness,
    DcdQualityCompletenessDetail,
    DcdQualityFreshness,
    DcdSource,
    DcdTemporal,
    DcdTemporalRange,
)

_COMPLETE_THRESHOLD = 0.95
_OVERALL_SCORE_WEIGHT = 0.7  # weight of completeness in the overall score


def build_dcd(
    *,
    dataset_id: str,
    load_result: LoadResult,
    profiling_result: ProfilingResult,
) -> DataContextDocument:
    """Assemble a :class:`DataContextDocument` from Silver-stage outputs.

    Args:
        dataset_id: The opaque ``ds_*`` id assigned by the registry.
        load_result: The Bronze-stage load metadata.
        profiling_result: The Silver-stage profiling output.

    Returns:
        A validated :class:`DataContextDocument`.
    """
    columns = _build_columns(
        profiling_result.column_profiles,
        profiling_result.classifications,
        profiling_result.pii_flags,
    )

    temporal = _build_temporal(profiling_result)
    quality = _build_quality(profiling_result.column_profiles, temporal)
    metrics = [
        DcdComputedMetric(
            name=proposal.name,
            formula=proposal.formula,
            description=proposal.description,
            depends_on=proposal.depends_on,
        )
        for proposal in profiling_result.metric_proposals
    ]

    dataset = DcdDataset(
        id=dataset_id,
        name=_humanize_name(load_result.original_filename),
        description=_describe_dataset(load_result),
        source=DcdSource(
            type=load_result.source_type,
            original_filename=load_result.original_filename,
            ingested_at=load_result.ingested_at,
            row_count=load_result.row_count,
            raw_size_bytes=load_result.raw_size_bytes,
        ),
        temporal=temporal,
        columns=columns,
        computed_metrics=metrics,
        quality=quality,
        agent_instructions=_build_agent_instructions(
            columns, profiling_result.pii_flags
        ),
    )

    return DataContextDocument(dataset=dataset)


def _build_columns(
    profiles: list[ColumnProfile],
    classifications: list[ColumnClassification],
    pii_flags: list[PiiFlag],
) -> list[DcdColumn]:
    classification_by_name = {c.name: c for c in classifications}
    pii_by_name = {f.column_name: f for f in pii_flags}
    columns: list[DcdColumn] = []
    for profile in profiles:
        classification = classification_by_name.get(profile.name)
        pii_flag = pii_by_name.get(profile.name)
        columns.append(_build_column(profile, classification, pii_flag))
    return columns


def _build_column(
    profile: ColumnProfile,
    classification: ColumnClassification | None,
    pii_flag: PiiFlag | None,
) -> DcdColumn:
    stats: DcdColumnStats | None = None
    if is_numeric_type(profile.dtype):
        stats = DcdColumnStats(
            min=profile.min_value,
            max=profile.max_value,
            mean=profile.mean,
            median=profile.median,
            stddev=profile.stddev,
            p25=profile.q25,
            p75=profile.q75,
        )

    role = classification.role if classification else "auxiliary"
    description = (
        classification.description if classification else f"{profile.name} column"
    )
    aggregation = classification.aggregation if classification else None

    sensitivity = pii_flag.sensitivity if pii_flag else "public"
    pii_type = pii_flag.pii_type if pii_flag else None
    handling = pii_flag.handling if pii_flag else None

    return DcdColumn(
        name=profile.name,
        dtype=profile.dtype,
        role=role,
        description=description,
        aggregation=aggregation,
        nullable=profile.null_count > 0,
        completeness=profile.completeness,
        cardinality=profile.distinct_count,
        sensitivity=sensitivity,
        pii_type=pii_type,
        handling=handling,
        stats=stats,
        sample_values=list(profile.sample_values),
    )


def _build_temporal(profiling_result: ProfilingResult) -> DcdTemporal:
    if profiling_result.temporal_column is None:
        return DcdTemporal()

    temporal_profile = next(
        (
            p
            for p in profiling_result.column_profiles
            if p.name == profiling_result.temporal_column
        ),
        None,
    )
    range_start = _coerce_to_date(
        temporal_profile.min_value if temporal_profile else None
    )
    range_end = _coerce_to_date(
        temporal_profile.max_value if temporal_profile else None
    )

    return DcdTemporal(
        grain=profiling_result.temporal_grain,
        column=profiling_result.temporal_column,
        range=DcdTemporalRange(start=range_start, end=range_end),
    )


def _build_quality(
    profiles: list[ColumnProfile],
    temporal: DcdTemporal,
) -> DcdQuality:
    fully_complete = sum(1 for p in profiles if p.completeness >= _COMPLETE_THRESHOLD)
    partial = len(profiles) - fully_complete
    details = [
        DcdQualityCompletenessDetail(
            column=profile.name,
            completeness=profile.completeness,
            note=f"{(1 - profile.completeness) * 100:.0f}% missing",
        )
        for profile in profiles
        if profile.completeness < _COMPLETE_THRESHOLD
    ]

    if profiles:
        avg_completeness = sum(p.completeness for p in profiles) / len(profiles)
    else:
        avg_completeness = 1.0

    overall_score = _OVERALL_SCORE_WEIGHT * avg_completeness + (
        1 - _OVERALL_SCORE_WEIGHT
    ) * (fully_complete / max(len(profiles), 1))

    freshness = DcdQualityFreshness(
        last_record_date=temporal.range.end,
        expected_frequency=temporal.grain,
        status="fresh" if temporal.range.end is not None else "unknown",
    )

    return DcdQuality(
        overall_score=round(overall_score, 3),
        freshness=freshness,
        completeness=DcdQualityCompleteness(
            fully_complete_columns=fully_complete,
            partial_columns=partial,
            details=details,
        ),
    )


def _build_agent_instructions(
    columns: list[DcdColumn],
    pii_flags: list[PiiFlag],
) -> list[str]:
    instructions: list[str] = []
    pii_columns = sorted(
        flag.column_name for flag in pii_flags if flag.sensitivity == "pii"
    )
    if pii_columns:
        instructions.append(
            "Never include the following PII columns in query outputs: "
            + ", ".join(pii_columns)
        )

    metric_cols = [c for c in columns if c.role == "metric" and c.aggregation]
    for metric in metric_cols:
        instructions.append(
            f"Always aggregate {metric.name!r} using {metric.aggregation}."
        )

    low_completeness = [c for c in columns if c.completeness < _COMPLETE_THRESHOLD]
    if low_completeness:
        names = ", ".join(sorted(c.name for c in low_completeness))
        instructions.append(
            f"Surface data-quality warnings when querying columns with "
            f"completeness below {int(_COMPLETE_THRESHOLD * 100)}%: {names}."
        )

    return instructions


def _humanize_name(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").title()


def _describe_dataset(load_result: LoadResult) -> str:
    return (
        f"{load_result.source_type.upper()} dataset loaded from "
        f"{load_result.original_filename} ({load_result.row_count} rows, "
        f"{load_result.column_count} columns)."
    )


def _coerce_to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None
