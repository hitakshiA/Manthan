"""Assemble a Data Context Document from Silver-stage outputs.

Takes a :class:`LoadResult` (Bronze metadata) and a
:class:`ProfilingResult` (Silver profile + classification + enrich) and
produces a fully-populated :class:`DataContextDocument` ready for
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
    DcdTable,
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
    """Assemble a :class:`DataContextDocument` from Silver-stage outputs."""
    columns = _build_columns(
        profiling_result.column_profiles,
        profiling_result.classifications,
        profiling_result.hierarchies,
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
        agent_instructions=_build_agent_instructions(columns),
        profiler_mode=profiling_result.profiler_mode,
    )

    return DataContextDocument(dataset=dataset)


def _build_columns(
    profiles: list[ColumnProfile],
    classifications: list[ColumnClassification],
    hierarchies: dict[str, list[str]] | None = None,
) -> list[DcdColumn]:
    classification_by_name = {c.name: c for c in classifications}
    hierarchies = hierarchies or {}
    columns: list[DcdColumn] = []
    for profile in profiles:
        classification = classification_by_name.get(profile.name)
        columns.append(
            _build_column(profile, classification, hierarchies.get(profile.name))
        )
    return columns


def _build_column(
    profile: ColumnProfile,
    classification: ColumnClassification | None,
    hierarchy: list[str] | None = None,
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
    synonyms = list(classification.synonyms) if classification else []
    reasoning = classification.reasoning if classification else None
    confidence = classification.confidence if classification else None

    return DcdColumn(
        name=profile.name,
        dtype=profile.dtype,
        role=role,
        description=description,
        aggregation=aggregation,
        nullable=profile.null_count > 0,
        completeness=profile.completeness,
        cardinality=profile.distinct_count,
        stats=stats,
        sample_values=list(profile.sample_values),
        hierarchy=hierarchy,
        synonyms=synonyms,
        classification_reasoning=reasoning,
        classification_confidence=confidence,
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


def _build_agent_instructions(columns: list[DcdColumn]) -> list[str]:
    """Emit natural-language directives the analysis agent should follow.

    The key rule: never enumerate individual values of ``identifier``
    columns when answering questions. Aggregate or count them instead.
    This replaces the old PII-based output filtering — the role
    classification is the enforcement mechanism.
    """
    instructions: list[str] = []

    identifier_cols = sorted(c.name for c in columns if c.role == "identifier")
    if identifier_cols:
        instructions.append(
            "Never enumerate individual values of identifier columns ("
            + ", ".join(identifier_cols)
            + "). Aggregate (COUNT DISTINCT, GROUP BY dimension) or "
            "reference them only when the user explicitly asks for a lookup."
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


async def generate_dataset_description(
    dcd: DataContextDocument,
) -> str:
    """Use the LLM to write a 1-2 sentence dataset description.

    Falls back to a template description if the LLM is unavailable.
    """
    from src.core.llm import LlmClient

    cols = dcd.dataset.columns
    metrics = [c for c in cols if c.role == "metric"]
    dims = [c for c in cols if c.role == "dimension"]
    temporal = [c for c in cols if c.role == "temporal"]

    col_summary = "\n".join(
        f"- {c.name} ({c.role}): {c.description}" for c in cols[:15]
    )

    prompt = (
        f"Dataset: {dcd.dataset.name}\n"
        f"Rows: {dcd.dataset.source.row_count:,}\n"
        f"Columns:\n{col_summary}\n\n"
        "Write a 1-2 sentence description of what this dataset "
        "contains and what it could be used to analyze. "
        "Be specific about the domain (e.g., 'census income data', "
        "'e-commerce transactions', 'corporate client records'). "
        "Do NOT mention file formats, column counts, or technical "
        "details. Write for a business user."
    )

    try:
        async with LlmClient() as llm:
            reply = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        desc = reply.strip().strip('"').strip("'")
        if len(desc) > 10:
            return desc
    except Exception:
        pass

    # Fallback: template from column roles
    parts: list[str] = []
    if metrics:
        names = ", ".join(c.name.replace("_", " ") for c in metrics[:2])
        parts.append(f"tracks {names}")
    if dims:
        names = ", ".join(c.name.replace("_", " ") for c in dims[:3])
        parts.append(f"segmented by {names}")
    if temporal:
        parts.append("with time-series data")
    if parts:
        return (
            f"{', '.join(parts)}. {dcd.dataset.source.row_count:,} records."
        ).capitalize()
    return _describe_dataset(dcd.dataset.source)


def _coerce_to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def build_dcd_table_from_profile(
    *,
    table_name: str,
    original_filename: str,
    load_result: LoadResult,
    profiling_result: ProfilingResult,
) -> DcdTable:
    """Build a :class:`DcdTable` for one file in a multi-file dataset.

    Used by :func:`src.api.pipeline.ingest_multi_file_and_profile` to
    attach additional (non-primary) tables to the DCD. Only the
    per-column shape + description is surfaced — Gold summary tables
    and verified queries still target the primary table only.
    """
    columns = _build_columns(
        profiling_result.column_profiles,
        profiling_result.classifications,
        profiling_result.hierarchies,
    )
    temporal = _build_temporal(profiling_result)
    return DcdTable(
        name=table_name,
        description=(
            f"{load_result.source_type.upper()} table loaded from "
            f"{original_filename} ({load_result.row_count} rows, "
            f"{load_result.column_count} columns)."
        ),
        row_count=load_result.row_count,
        columns=columns,
        temporal=temporal if temporal.column else None,
    )


def dcd_table_from_primary_dcd(
    dcd: DataContextDocument,
    table_name: str,
) -> DcdTable:
    """Wrap the primary DCD's columns as a :class:`DcdTable` entry.

    Used so the primary table appears alongside additional tables in
    ``DcdDataset.tables`` for uniform agent enumeration.
    """
    return DcdTable(
        name=table_name,
        description=dcd.dataset.description,
        row_count=dcd.dataset.source.row_count,
        columns=list(dcd.dataset.columns),
        temporal=dcd.dataset.temporal if dcd.dataset.temporal.column else None,
    )
