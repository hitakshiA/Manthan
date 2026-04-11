"""Tests for src.profiling.classifier.

Uses :class:`httpx.MockTransport` to stub the LLM response so no network
traffic is involved.
"""

from __future__ import annotations

import json

import httpx
import pytest
from src.core.exceptions import ProfilingError
from src.core.llm import LlmClient
from src.profiling.classifier import (
    ColumnClassification,
    _align_to_profiles,
    _parse_classifications,
    classify_columns,
)
from src.profiling.statistical import ColumnProfile


def _make_profile(name: str, dtype: str = "VARCHAR") -> ColumnProfile:
    return ColumnProfile(
        name=name,
        dtype=dtype,
        row_count=10,
        null_count=0,
        completeness=1.0,
        distinct_count=5,
        cardinality_ratio=0.5,
        sample_values=["a", "b", "c"],
    )


def _build_mock_llm(payload: object) -> LlmClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(payload)
                            if not isinstance(payload, str)
                            else payload,
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        transport=transport,
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test"},
    )
    return LlmClient(client=client)


class TestParseClassifications:
    def test_parses_top_level_dict(self) -> None:
        raw = json.dumps(
            {
                "classifications": [
                    {
                        "name": "revenue",
                        "role": "metric",
                        "description": "Sales revenue",
                        "aggregation": "SUM",
                    }
                ]
            }
        )
        result = _parse_classifications(raw)
        assert len(result) == 1
        assert result[0].role == "metric"
        assert result[0].aggregation == "SUM"

    def test_parses_bare_list(self) -> None:
        raw = json.dumps(
            [
                {
                    "name": "region",
                    "role": "dimension",
                    "description": "Region",
                    "aggregation": None,
                }
            ]
        )
        result = _parse_classifications(raw)
        assert result[0].role == "dimension"

    def test_strips_markdown_fences(self) -> None:
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "classifications": [
                        {
                            "name": "x",
                            "role": "auxiliary",
                            "description": "x",
                            "aggregation": None,
                        }
                    ]
                }
            )
            + "\n```"
        )
        result = _parse_classifications(raw)
        assert result[0].name == "x"

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ProfilingError):
            _parse_classifications("not json at all")

    def test_rejects_missing_classifications_key(self) -> None:
        with pytest.raises(ProfilingError):
            _parse_classifications(json.dumps({"foo": "bar"}))

    def test_rejects_invalid_role_enum(self) -> None:
        raw = json.dumps(
            {
                "classifications": [
                    {
                        "name": "x",
                        "role": "not_a_role",
                        "description": "x",
                        "aggregation": None,
                    }
                ]
            }
        )
        with pytest.raises(ProfilingError):
            _parse_classifications(raw)


class TestAlignToProfiles:
    def test_fills_missing_columns_with_auxiliary(self) -> None:
        profiles = [_make_profile("a"), _make_profile("b"), _make_profile("c")]
        classifications = [
            ColumnClassification(
                name="a", role="metric", description="a", aggregation="SUM"
            ),
            ColumnClassification(
                name="c", role="dimension", description="c", aggregation=None
            ),
        ]
        aligned = _align_to_profiles(profiles, classifications)
        assert [c.name for c in aligned] == ["a", "b", "c"]
        assert aligned[0].role == "metric"
        assert aligned[1].role == "auxiliary"
        assert aligned[2].role == "dimension"


@pytest.mark.asyncio
class TestClassifyColumns:
    async def test_happy_path(self) -> None:
        profiles = [
            _make_profile("revenue", "DOUBLE"),
            _make_profile("region", "VARCHAR"),
        ]
        payload = {
            "classifications": [
                {
                    "name": "revenue",
                    "role": "metric",
                    "description": "Total order amount",
                    "aggregation": "SUM",
                },
                {
                    "name": "region",
                    "role": "dimension",
                    "description": "Sales region",
                    "aggregation": None,
                },
            ]
        }
        async with _build_mock_llm(payload) as llm:
            result = await classify_columns(profiles, llm)
        assert len(result) == 2
        assert result[0].role == "metric"
        assert result[1].role == "dimension"

    async def test_empty_profiles_short_circuits(self) -> None:
        async with _build_mock_llm({"classifications": []}) as llm:
            result = await classify_columns([], llm)
        assert result == []

    async def test_llm_returns_bad_json_raises_profiling_error(self) -> None:
        async with _build_mock_llm("this is not json") as llm:
            with pytest.raises(ProfilingError):
                await classify_columns([_make_profile("x")], llm)
