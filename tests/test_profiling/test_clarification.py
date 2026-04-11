"""Tests for src.profiling.clarification."""

from __future__ import annotations

from src.profiling.agent import ProfilingResult
from src.profiling.clarification import (
    ClarificationAnswer,
    generate_questions,
    merge_answers,
)
from src.profiling.classifier import ColumnClassification
from src.profiling.pii_detector import PiiFlag
from src.profiling.statistical import ColumnProfile


def _profile(name: str, dtype: str, distinct: int = 10) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype=dtype,
        row_count=100,
        null_count=0,
        completeness=1.0,
        distinct_count=distinct,
        cardinality_ratio=distinct / 100,
        sample_values=[],
    )


def _build_result() -> ProfilingResult:
    profiles = [
        _profile("amt", "DOUBLE", 85),
        _profile("score", "DOUBLE", 2),
        _profile("region", "VARCHAR", 4),
        _profile("raw_payload", "DOUBLE", 50),
    ]
    classifications = [
        ColumnClassification(
            name="amt", role="metric", description="amt", aggregation="SUM"
        ),
        ColumnClassification(
            name="score", role="metric", description="score", aggregation="SUM"
        ),
        ColumnClassification(
            name="region", role="dimension", description="region", aggregation=None
        ),
        ColumnClassification(
            name="raw_payload",
            role="auxiliary",
            description="raw_payload",
            aggregation=None,
        ),
    ]
    pii_flags = [
        PiiFlag(
            column_name=p.name,
            sensitivity="public",
            handling="expose",
            reason="none",
            confidence=0.5,
        )
        for p in profiles
    ]
    return ProfilingResult(
        table_name="raw_test",
        column_profiles=profiles,
        classifications=classifications,
        pii_flags=pii_flags,
    )


def test_generates_questions_for_short_names_and_ambiguous_roles() -> None:
    result = _build_result()
    questions = generate_questions(result)
    names = {q.column_name for q in questions}
    assert "amt" in names  # short name (3 chars)
    assert "score" in names  # low-distinct metric
    assert "raw_payload" in names  # numeric classified as auxiliary
    assert "region" not in names  # confident classification


def test_merge_answers_updates_classifications() -> None:
    result = _build_result()
    questions = generate_questions(result)
    answers = [
        ClarificationAnswer(
            question_id=questions[0].question_id,
            column_name="amt",
            chosen_role="metric",
            aggregation="AVG",
        ),
        ClarificationAnswer(
            question_id=questions[1].question_id,
            column_name="score",
            chosen_role="dimension",
        ),
    ]
    merged = merge_answers(result, answers)
    classifications_by_name = {c.name: c for c in merged.classifications}
    assert classifications_by_name["amt"].aggregation == "AVG"
    assert classifications_by_name["score"].role == "dimension"
    assert classifications_by_name["score"].aggregation is None
