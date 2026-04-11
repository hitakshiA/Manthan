"""Tests for LLM retry/backoff."""

from __future__ import annotations

import httpx
import pytest
from src.core.exceptions import LlmError
from src.core.llm import LlmClient


@pytest.mark.asyncio
async def test_retries_on_500_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500, json={"error": "upstream down"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        transport=transport,
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test"},
    )
    async with LlmClient(client=client, max_retries=3) as llm:
        # Patch asyncio.sleep to avoid waiting in tests.
        import src.core.llm as llm_module

        original_sleep = llm_module.asyncio.sleep

        async def fake_sleep(_seconds: float) -> None:
            return None

        llm_module.asyncio.sleep = fake_sleep
        try:
            result = await llm.chat([{"role": "user", "content": "hi"}])
        finally:
            llm_module.asyncio.sleep = original_sleep

    assert result == "ok"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_does_not_retry_on_400() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        transport=transport,
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test"},
    )
    async with LlmClient(client=client, max_retries=3) as llm:
        with pytest.raises(LlmError):
            await llm.chat([{"role": "user", "content": "hi"}])
