"""Tests for src.core.llm.

Uses :class:`httpx.MockTransport` to intercept requests at the transport
layer so we can verify the client without any network traffic and without
monkey-patching private attributes.
"""

import httpx
import pytest
from src.core.exceptions import LlmError, LlmTimeoutError
from src.core.llm import LlmClient


def _build_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=handler,
        base_url="https://openrouter.test/api/v1",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_chat_returns_assistant_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello, Manthan!"}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with LlmClient(client=_build_client(transport)) as llm:
        result = await llm.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello, Manthan!"


@pytest.mark.asyncio
async def test_chat_raises_timeout_on_httpx_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    transport = httpx.MockTransport(handler)
    async with LlmClient(client=_build_client(transport)) as llm:
        with pytest.raises(LlmTimeoutError):
            await llm.chat([{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_chat_raises_llm_error_on_http_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    async with LlmClient(client=_build_client(transport)) as llm:
        with pytest.raises(LlmError):
            await llm.chat([{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_chat_raises_llm_error_on_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    transport = httpx.MockTransport(handler)
    async with LlmClient(client=_build_client(transport)) as llm:
        with pytest.raises(LlmError, match="Malformed"):
            await llm.chat([{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_chat_without_context_manager_raises() -> None:
    llm = LlmClient()
    with pytest.raises(LlmError, match="context manager"):
        await llm.chat([{"role": "user", "content": "Hi"}])
