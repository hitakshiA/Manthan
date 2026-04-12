"""LLM-powered column role classification.

Given a list of :class:`ColumnProfile` objects, this module asks the LLM
(via :class:`src.core.llm.LlmClient`) to assign each column a semantic
role, description, optional aggregation, a confidence score, and a
one-sentence explanation of why it picked that role. Metrics
additionally get a default aggregation.

The prompt is deliberately small: columns are summarised in a few lines
each (name, type, cardinality, a handful of sample values), and the
model is asked to return strict JSON. Any parsing failure raises
:class:`ProfilingError`.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.exceptions import LlmError, ProfilingError
from src.core.llm import LlmClient
from src.core.logger import get_logger
from src.profiling.statistical import (
    ColumnProfile,
    is_numeric_type,
    is_temporal_type,
)

_logger = get_logger()

Role = Literal["metric", "dimension", "temporal", "identifier", "auxiliary"]
Aggregation = Literal["SUM", "AVG", "COUNT", "MIN", "MAX"]

_MAX_SAMPLE_VALUES_IN_PROMPT = 3

# Heuristic identifier/metric hints used by the fallback classifier when
# the LLM is unavailable (rate limited, quota exhausted, network down).
# Patterns match the end of the snake-cased column name so they're
# resilient to prefixes like customer_id or tpep_pickup_datetime.
_IDENTIFIER_NAME_RE = re.compile(
    r"(^|_)(id|uuid|key|code|sku|hash|pid|vin|isbn|upc)s?$",
    re.IGNORECASE,
)
_METRIC_NAME_HINTS = (
    "amount",
    "price",
    "revenue",
    "cost",
    "total",
    "quantity",
    "qty",
    "count",
    "num",
    "rate",
    "balance",
    "value",
    "weight",
    "length",
    "distance",
    "area",
    "size",
    "volume",
    "duration",
    "fare",
    "tip",
    "tax",
    "fee",
    "surcharge",
    "wage",
    "salary",
    "income",
    "profit",
    "margin",
    "discount",
    "score",
    "rating",
    "gain",
    "loss",
    "hours",
    "_sf",
)
_DIMENSION_NAME_HINTS = (
    "type",
    "category",
    "group",
    "class",
    "status",
    "kind",
    "region",
    "country",
    "state",
    "city",
    "zone",
    "channel",
    "segment",
    "tier",
    "level",
    "grade",
    "brand",
    "gender",
    "sex",
    "race",
    "education",
    "occupation",
    "relationship",
    "workclass",
    "marital",
    "neighborhood",
    "zoning",
    "foundation",
    "roof",
    "exterior",
    "heating",
    "style",
    "condition",
    "shape",
    "fence",
    "pool",
    "alley",
    "garage",
    "utility",
    "league",
    "team",
    "position",
    "department",
    "product",
)
_AUXILIARY_NAME_HINTS = (
    "description",
    "notes",
    "comment",
    "text",
    "url",
    "json",
    "xml",
)
_HIGH_CARDINALITY_RATIO = 0.95
_LOW_DISTINCT_CEILING = 50

_SYSTEM_PROMPT = (
    "You are a data analyst. Classify each column.\n\n"
    "Roles: metric (numeric to aggregate), dimension (categorical "
    "to group by), temporal (dates/times), identifier (unique keys), "
    "auxiliary (everything else).\n\n"
    "Return ONLY valid JSON, no markdown, no prose:\n"
    '{"classifications": [{"name": "col", "role": "metric", '
    '"description": "short sentence", "aggregation": "SUM", '
    '"confidence": 0.95}]}\n\n'
    "aggregation: SUM/AVG/COUNT/MIN/MAX for metrics, null otherwise.\n"
    "confidence: 0.0-1.0, how sure you are about the role.\n"
)


class ColumnClassification(BaseModel):
    """Per-column semantic classification returned by the LLM."""

    model_config = ConfigDict(frozen=True)

    name: str
    role: Role
    description: str
    aggregation: Aggregation | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str | None = None
    synonyms: list[str] = Field(default_factory=list)


async def classify_columns(
    profiles: list[ColumnProfile],
    llm_client: LlmClient,
) -> list[ColumnClassification]:
    """Classify every column in ``profiles`` via the LLM.

    Args:
        profiles: Column profiles produced by the statistical profiler.
        llm_client: A live :class:`LlmClient` (already entered as an
            async context manager).

    Returns:
        One :class:`ColumnClassification` per input profile, in the same
        order. Missing or extra LLM items are reconciled by
        :func:`_align_to_profiles` so callers always get exactly
        ``len(profiles)`` classifications back.

    If the LLM is unavailable (rate limited, quota exhausted, transport
    failure), the classifier falls back to a deterministic heuristic
    derived from column names, dtypes, cardinality ratios, and sample
    values. Classifications produced via the fallback are labelled with
    ``reasoning="heuristic-fallback: ..."`` so the DCD makes the
    provenance auditable.

    Raises:
        ProfilingError: If the LLM response is not parseable as the
            expected JSON schema (only when the LLM did respond). An
            ``LlmError`` is caught and converted into heuristic output.
    """
    if not profiles:
        return []

    user_message = _build_columns_prompt(profiles)
    try:
        raw = await llm_client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
        )
    except LlmError as exc:
        _logger.warning(
            "classifier.llm_unavailable_using_heuristic",
            error=str(exc)[:200],
            column_count=len(profiles),
        )
        return [heuristic_classify(p) for p in profiles]

    try:
        parsed = _parse_classifications(raw)
    except ProfilingError as exc:
        _logger.warning(
            "classifier.llm_output_unparseable_using_heuristic",
            error=str(exc)[:200],
            column_count=len(profiles),
        )
        return [heuristic_classify(p) for p in profiles]

    return _align_to_profiles(profiles, parsed)


def heuristic_classify(profile: ColumnProfile) -> ColumnClassification:
    """Deterministic heuristic classifier used as an offline fallback.

    Applies a cascade of rules:

    1. Temporal dtype → role=temporal.
    2. Column name matches identifier regex AND cardinality ratio is
       high (≥ 95% distinct) → role=identifier.
    3. Numeric dtype AND name matches a metric hint → role=metric (SUM).
    4. Numeric dtype AND low distinct count → role=dimension (e.g. a
       small-integer enum).
    5. Numeric dtype with no strong hint → role=metric (SUM) by default.
    6. String dtype AND name matches a dimension hint, OR low distinct
       count → role=dimension.
    7. String dtype AND name matches an auxiliary hint OR high distinct
       count → role=auxiliary.
    8. Default → auxiliary.

    The reasoning string always begins with ``heuristic-fallback:`` so
    the DCD makes the provenance auditable even if downstream code
    strips the ``reasoning`` field.
    """
    name = profile.name
    name_lc = name.lower()
    dtype = profile.dtype
    distinct = profile.distinct_count
    row_count = profile.row_count
    cardinality_ratio = distinct / row_count if row_count > 0 else 0.0

    def _make(
        role: Role,
        description: str,
        reason: str,
        aggregation: Aggregation | None = None,
    ) -> ColumnClassification:
        return ColumnClassification(
            name=name,
            role=role,
            description=description,
            aggregation=aggregation,
            confidence=0.5,
            reasoning=f"heuristic-fallback: {reason}",
            synonyms=[],
        )

    if is_temporal_type(dtype):
        return _make(
            "temporal",
            f"{name} timestamp/date column",
            f"dtype {dtype} is temporal",
        )

    if (
        _IDENTIFIER_NAME_RE.search(name_lc)
        and cardinality_ratio >= _HIGH_CARDINALITY_RATIO
    ):
        return _make(
            "identifier",
            f"Unique identifier for {name}",
            f"name matches id pattern, cardinality ratio {cardinality_ratio:.2f}",
        )

    if is_numeric_type(dtype):
        if any(hint in name_lc for hint in _METRIC_NAME_HINTS):
            return _make(
                "metric",
                f"Numeric measure {name}",
                f"dtype {dtype} + name matches metric hint",
                aggregation="SUM",
            )
        if distinct <= _LOW_DISTINCT_CEILING:
            return _make(
                "dimension",
                f"Low-cardinality integer enum {name}",
                f"numeric with only {distinct} distinct values",
            )
        # Default numeric → metric
        return _make(
            "metric",
            f"Numeric column {name}",
            f"dtype {dtype} defaulted to metric",
            aggregation="SUM",
        )

    # String / other dtypes
    if any(hint in name_lc for hint in _AUXILIARY_NAME_HINTS):
        return _make(
            "auxiliary",
            f"Free-text {name}",
            "name matches auxiliary hint",
        )
    if any(hint in name_lc for hint in _DIMENSION_NAME_HINTS):
        return _make(
            "dimension",
            f"Categorical dimension {name}",
            "name matches dimension hint",
        )
    if distinct <= _LOW_DISTINCT_CEILING:
        return _make(
            "dimension",
            f"Low-cardinality categorical {name}",
            f"only {distinct} distinct values",
        )
    if (
        _IDENTIFIER_NAME_RE.search(name_lc)
        or cardinality_ratio >= _HIGH_CARDINALITY_RATIO
    ):
        return _make(
            "identifier",
            f"High-cardinality identifier {name}",
            f"cardinality ratio {cardinality_ratio:.2f} or name matches id pattern",
        )
    return _make(
        "auxiliary",
        f"Unclassified column {name}",
        "no rule matched",
    )


def _build_columns_prompt(profiles: list[ColumnProfile]) -> str:
    lines: list[str] = ["Columns to classify:"]
    for profile in profiles:
        sample_preview = ", ".join(
            repr(v) for v in profile.sample_values[:_MAX_SAMPLE_VALUES_IN_PROMPT]
        )
        lines.append(
            f"- {profile.name} "
            f"(dtype={profile.dtype}, "
            f"distinct={profile.distinct_count}/{profile.row_count}, "
            f"samples=[{sample_preview}])"
        )
    return "\n".join(lines)


def _parse_classifications(raw: str) -> list[ColumnClassification]:
    """Parse LLM output into :class:`ColumnClassification` objects.

    Tolerates common deviations: leading/trailing whitespace, markdown
    fences, or a ``classifications`` list returned at the top level.
    """
    text = raw.strip()

    # Strip optional Markdown fences like ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            text = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfilingError(f"Classifier returned invalid JSON: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "classifications" in data:
        items = data["classifications"]
    else:
        raise ProfilingError("Classifier response is missing a 'classifications' list")

    if not isinstance(items, list):
        raise ProfilingError("'classifications' is not a list")

    result: list[ColumnClassification] = []
    for item in items:
        if not isinstance(item, dict):
            raise ProfilingError(f"Expected classification object, got {type(item)}")
        try:
            result.append(ColumnClassification(**item))
        except ValidationError as exc:
            raise ProfilingError(f"Invalid classification item: {exc}") from exc
    return result


def _align_to_profiles(
    profiles: list[ColumnProfile],
    classifications: list[ColumnClassification],
) -> list[ColumnClassification]:
    """Return a classification for every profile, filling gaps with auxiliary."""
    by_name = {c.name: c for c in classifications}
    aligned: list[ColumnClassification] = []
    for profile in profiles:
        existing = by_name.get(profile.name)
        if existing is not None:
            aligned.append(existing)
        else:
            aligned.append(
                ColumnClassification(
                    name=profile.name,
                    role="auxiliary",
                    description=f"{profile.name} column (not classified by LLM)",
                    aggregation=None,
                    confidence=0.2,
                    reasoning="Not classified by LLM; defaulted to auxiliary.",
                    synonyms=[],
                )
            )
    return aligned
