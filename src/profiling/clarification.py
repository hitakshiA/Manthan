"""Interactive clarification flow for low-confidence classifications.

The profiling agent always picks a deterministic fallback for
low-confidence columns, but SPEC §2 ADR-005 also asks for a
``DISAMBIGUATE`` step where the agent batches targeted questions to the
user. This module implements the question-generation + answer-merge
pieces so the API layer can surface a clarification UI without the
agent needing to block mid-run.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.profiling.agent import ProfilingResult
from src.profiling.classifier import ColumnClassification
from src.profiling.statistical import ColumnProfile

_LOW_CARDINALITY_QUESTION_THRESHOLD = 3
_SHORT_NAME_LENGTH = 3


class ClarificationQuestion(BaseModel):
    """A single question surfaced to the user."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    column_name: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    current_role: str


class ClarificationAnswer(BaseModel):
    """A user's response to a :class:`ClarificationQuestion`."""

    question_id: str
    column_name: str
    chosen_role: str
    aggregation: str | None = None


def generate_questions(
    profiling_result: ProfilingResult,
) -> list[ClarificationQuestion]:
    """Emit targeted questions for columns the agent was unsure about.

    Targets:

    - Short / abbreviated column names whose inferred role may be wrong
    - Numeric columns classified as ``auxiliary`` (often a mistake)
    - Low-distinct dimension-shaped columns that could be metrics
    """
    questions: list[ClarificationQuestion] = []
    by_name: dict[str, ColumnProfile] = {
        profile.name: profile for profile in profiling_result.column_profiles
    }

    for classification in profiling_result.classifications:
        profile = by_name.get(classification.name)
        if profile is None:
            continue
        if _needs_clarification(profile, classification):
            questions.append(
                ClarificationQuestion(
                    question_id=f"q_{uuid4().hex[:8]}",
                    column_name=classification.name,
                    prompt=_build_prompt(profile, classification),
                    options=[
                        "metric",
                        "dimension",
                        "temporal",
                        "identifier",
                        "auxiliary",
                    ],
                    current_role=classification.role,
                )
            )
    return questions


def merge_answers(
    profiling_result: ProfilingResult,
    answers: list[ClarificationAnswer],
) -> ProfilingResult:
    """Apply user ``answers`` on top of ``profiling_result``'s classifications."""
    if not answers:
        return profiling_result

    by_column = {answer.column_name: answer for answer in answers}
    updated_classifications: list[ColumnClassification] = []
    for classification in profiling_result.classifications:
        answer = by_column.get(classification.name)
        if answer is None:
            updated_classifications.append(classification)
            continue
        updated_classifications.append(
            classification.model_copy(
                update={
                    "role": answer.chosen_role,
                    "aggregation": answer.aggregation
                    if answer.chosen_role == "metric"
                    else None,
                }
            )
        )

    return profiling_result.model_copy(
        update={"classifications": updated_classifications}
    )


def _needs_clarification(
    profile: ColumnProfile,
    classification: ColumnClassification,
) -> bool:
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


def _build_prompt(
    profile: ColumnProfile,
    classification: ColumnClassification,
) -> str:
    sample_preview = ", ".join(str(v) for v in profile.sample_values[:5])
    return (
        f"Column {profile.name!r} (dtype={profile.dtype}, "
        f"distinct={profile.distinct_count}/{profile.row_count}, "
        f"samples=[{sample_preview}]) was classified as "
        f"{classification.role!r}. Is that correct?"
    )
