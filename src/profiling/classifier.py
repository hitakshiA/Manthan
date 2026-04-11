"""LLM-powered column role classification.

Given a list of :class:`ColumnProfile` objects, this module asks the LLM
(via :class:`src.core.llm.LlmClient`) to assign each column a semantic
role: ``metric``, ``dimension``, ``temporal``, ``identifier``, or
``auxiliary``. Metrics additionally get a default aggregation.

The prompt is deliberately small: columns are summarised in a few lines
each (name, type, cardinality, a handful of sample values), and the
model is asked to return strict JSON. Any parsing failure raises
:class:`ProfilingError` so callers can retry with a different prompt or
fall back to a deterministic default.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src.core.exceptions import ProfilingError
from src.core.llm import LlmClient
from src.profiling.statistical import ColumnProfile

Role = Literal["metric", "dimension", "temporal", "identifier", "auxiliary"]
Aggregation = Literal["SUM", "AVG", "COUNT", "MIN", "MAX"]

_MAX_SAMPLE_VALUES_IN_PROMPT = 5

_SYSTEM_PROMPT = (
    "You are a data analyst classifying columns in a dataset.\n\n"
    "For each column, return:\n"
    '- role: exactly one of "metric", "dimension", "temporal", '
    '"identifier", "auxiliary"\n'
    "- description: one short user-facing sentence\n"
    "- aggregation: for metrics only, one of "
    '"SUM", "AVG", "COUNT", "MIN", "MAX"; null otherwise\n\n'
    "Definitions:\n"
    "- metric = numeric values the user aggregates (revenue, quantity, price)\n"
    "- dimension = categorical attribute to group or filter by "
    "(region, category)\n"
    "- temporal = dates and times\n"
    "- identifier = unique or near-unique keys (order_id, customer_id)\n"
    "- auxiliary = anything else (free text, raw json, internal flags)\n\n"
    "Return ONLY valid JSON in this exact shape, with no prose and no "
    "markdown fences:\n"
    '{"classifications": [{"name": "col", "role": "metric", '
    '"description": "...", "aggregation": "SUM"}]}\n'
)


class ColumnClassification(BaseModel):
    """Per-column semantic classification returned by the LLM."""

    model_config = ConfigDict(frozen=True)

    name: str
    role: Role
    description: str
    aggregation: Aggregation | None = None


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

    Raises:
        ProfilingError: If the LLM response is not parseable as the
            expected JSON schema.
    """
    if not profiles:
        return []

    user_message = _build_columns_prompt(profiles)
    raw = await llm_client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
    )

    parsed = _parse_classifications(raw)
    return _align_to_profiles(profiles, parsed)


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
                )
            )
    return aligned
