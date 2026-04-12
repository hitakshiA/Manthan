"""Interactive clarification for low-confidence column classifications.

When the LLM classifier isn't confident about a column's role, we ask
the user a plain-English question with clear multiple-choice options —
no jargon, no code syntax, no "metric vs dimension" vocabulary.

Each question is self-contained: a human-readable prompt, a list of
option objects (each with a ``label`` the user sees and a ``value``
the system uses), and a recommended default. Layer 3 renders these as
clickable buttons. The user taps one; Layer 1 gets back a structured
answer it can merge into the profiling result before Gold.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.profiling.agent import ProfilingResult
from src.profiling.classifier import ColumnClassification
from src.profiling.statistical import ColumnProfile, is_numeric_type, is_temporal_type

_LOW_CARDINALITY_QUESTION_THRESHOLD = 3
_SHORT_NAME_LENGTH = 3
_LOW_CONFIDENCE_THRESHOLD = 0.8


class ClarificationOption(BaseModel):
    """One clickable choice the user sees."""

    model_config = ConfigDict(frozen=True)

    label: str = Field(..., description="Human-friendly text shown to the user")
    value: str = Field(
        ...,
        description="Internal role value: metric/dimension/"
        "temporal/identifier/auxiliary",
    )
    aggregation: str | None = Field(
        default=None, description="If metric, default aggregation"
    )


class ClarificationQuestion(BaseModel):
    """A single question surfaced to the user."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    column_name: str
    prompt: str = Field(..., description="Plain-English question")
    options: list[ClarificationOption] = Field(default_factory=list)
    current_role: str
    recommended: str | None = Field(
        default=None,
        description="The option value we'd pick if the user skips",
    )


class ClarificationAnswer(BaseModel):
    """A user's response — just the chosen option's value."""

    question_id: str
    column_name: str
    chosen_role: str
    aggregation: str | None = None


def generate_questions(
    profiling_result: ProfilingResult,
) -> list[ClarificationQuestion]:
    """Emit human-friendly questions for columns the classifier was unsure about."""
    questions: list[ClarificationQuestion] = []
    by_name: dict[str, ColumnProfile] = {
        p.name: p for p in profiling_result.column_profiles
    }

    for cls in profiling_result.classifications:
        profile = by_name.get(cls.name)
        if profile is None:
            continue
        if _needs_clarification(profile, cls):
            questions.append(_build_question(profile, cls))
    return questions


def merge_answers(
    profiling_result: ProfilingResult,
    answers: list[ClarificationAnswer],
) -> ProfilingResult:
    """Apply user answers on top of the profiling result's classifications."""
    if not answers:
        return profiling_result

    by_column = {a.column_name: a for a in answers}
    updated: list[ColumnClassification] = []
    for cls in profiling_result.classifications:
        answer = by_column.get(cls.name)
        if answer is None:
            updated.append(cls)
            continue
        updated.append(
            cls.model_copy(
                update={
                    "role": answer.chosen_role,
                    "aggregation": answer.aggregation
                    if answer.chosen_role == "metric"
                    else None,
                }
            )
        )

    return profiling_result.model_copy(update={"classifications": updated})


def _needs_clarification(
    profile: ColumnProfile,
    classification: ColumnClassification,
) -> bool:
    if (
        classification.confidence is not None
        and classification.confidence < _LOW_CONFIDENCE_THRESHOLD
    ):
        return True
    if len(profile.name) <= _SHORT_NAME_LENGTH:
        return True
    if classification.role == "auxiliary" and profile.dtype.upper() in {
        "DOUBLE",
        "FLOAT",
        "DECIMAL",
        "BIGINT",
        "INTEGER",
    }:
        return True
    return (
        classification.role == "metric"
        and profile.distinct_count <= _LOW_CARDINALITY_QUESTION_THRESHOLD
    )


def _build_question(
    profile: ColumnProfile,
    classification: ColumnClassification,
) -> ClarificationQuestion:
    """Build a plain-English question with clickable options."""
    name = profile.name
    samples = profile.sample_values[:5]
    sample_str = ", ".join(str(v) for v in samples)
    distinct = profile.distinct_count
    total = profile.row_count
    is_numeric = is_numeric_type(profile.dtype)
    is_time = is_temporal_type(profile.dtype)

    # Pick the right question style based on what's ambiguous
    if is_time:
        prompt = (
            f"'{name}' looks like it contains dates or timestamps "
            f"(e.g. {sample_str}). Is this a time column your data "
            f"is organized by?"
        )
        options = [
            ClarificationOption(
                label="Yes, this is my main date/time column",
                value="temporal",
            ),
            ClarificationOption(
                label="No, it's just a reference date — not for trending",
                value="dimension",
            ),
        ]
        recommended = "temporal"

    elif is_numeric and distinct <= 20:
        # Numeric with few distinct values — could be a code/enum or a real metric
        prompt = (
            f"'{name}' has numbers but only {distinct} different values "
            f"(like {sample_str}). Is this a code or category you'd "
            f"group by, or a number you'd calculate with?"
        )
        options = [
            ClarificationOption(
                label=f"It's a category — I'd group or filter by '{name}'",
                value="dimension",
            ),
            ClarificationOption(
                label=f"It's a number — I'd sum or average '{name}'",
                value="metric",
                aggregation="SUM",
            ),
            ClarificationOption(
                label="It's an ID or code — not really useful for analysis",
                value="identifier",
            ),
        ]
        recommended = classification.role

    elif is_numeric and classification.role == "auxiliary":
        # Numeric column tagged as auxiliary — probably a mistake
        prompt = (
            f"'{name}' contains numbers (like {sample_str}) but I'm "
            f"not sure if it's useful for analysis. What is it?"
        )
        options = [
            ClarificationOption(
                label=f"It's a measure — I'd want to sum or average '{name}'",
                value="metric",
                aggregation="SUM",
            ),
            ClarificationOption(
                label=f"It's a category code — I'd group by '{name}'",
                value="dimension",
            ),
            ClarificationOption(
                label="It's internal/technical — I can ignore it",
                value="auxiliary",
            ),
        ]
        recommended = "metric"

    elif is_numeric:
        # Generic numeric ambiguity
        prompt = (
            f"'{name}' has {distinct:,} different numeric values "
            f"(like {sample_str}). How do you use it?"
        )
        options = [
            ClarificationOption(
                label="I'd calculate with it (sum, average, etc.)",
                value="metric",
                aggregation="SUM",
            ),
            ClarificationOption(
                label="I'd group or filter by it",
                value="dimension",
            ),
            ClarificationOption(
                label="It's an ID — just for looking up records",
                value="identifier",
            ),
        ]
        recommended = classification.role

    elif distinct > total * 0.9:
        # High-cardinality string — probably an identifier
        prompt = (
            f"'{name}' has {distinct:,} unique values out of {total:,} "
            f"rows (like {sample_str}). Is this an ID or key, or "
            f"something you'd actually analyze?"
        )
        options = [
            ClarificationOption(
                label="It's an ID or key — just for looking up records",
                value="identifier",
            ),
            ClarificationOption(
                label="It's a category I'd want to group by",
                value="dimension",
            ),
            ClarificationOption(
                label="It's free text — not useful for grouping",
                value="auxiliary",
            ),
        ]
        recommended = "identifier"

    else:
        # Generic string column
        prompt = (
            f"'{name}' has {distinct} different values "
            f"(like {sample_str}). How would you use this in analysis?"
        )
        options = [
            ClarificationOption(
                label=f"I'd group or filter by '{name}'",
                value="dimension",
            ),
            ClarificationOption(
                label="It's an ID or reference code",
                value="identifier",
            ),
            ClarificationOption(
                label="It's not useful — skip it",
                value="auxiliary",
            ),
        ]
        recommended = classification.role

    return ClarificationQuestion(
        question_id=f"q_{uuid4().hex[:8]}",
        column_name=name,
        prompt=prompt,
        options=options,
        current_role=classification.role,
        recommended=recommended,
    )
