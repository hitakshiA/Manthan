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


@pytest.fixture(autouse=True)
def _patch_llm_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retry backoff a no-op in unit tests so the suite stays fast."""
    import src.core.llm as llm_module

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)


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
async def test_chat_retries_on_malformed_200_and_raises_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 200 response missing ``choices`` is treated as retryable.

    OpenRouter occasionally returns HTTP 200 with a semantic error
    envelope (upstream provider drop, queue timeout). The client should
    retry rather than fail on the first attempt, and only raise
    ``LlmError`` after all retries are exhausted.
    """
    import src.core.llm as llm_module

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"unexpected": "shape"})

    transport = httpx.MockTransport(handler)
    # Model cascade: primary + 2 fallbacks = 3 models, each with
    # max_retries=2 attempts, so total calls = 6.
    async with LlmClient(client=_build_client(transport), max_retries=2) as llm:
        with pytest.raises(LlmError, match="missing choices"):
            await llm.chat([{"role": "user", "content": "Hi"}])
    expected = 6  # 3 models x 2 retries
    assert call_count == expected, f"expected {expected}, got {call_count}"


@pytest.mark.asyncio
async def test_chat_retries_on_200_with_error_envelope_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider hiccup (200 with ``{"error": ...}``) retries and recovers."""
    import src.core.llm as llm_module

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                200,
                json={"error": {"message": "upstream provider timeout"}},
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
            },
        )

    transport = httpx.MockTransport(handler)
    async with LlmClient(client=_build_client(transport)) as llm:
        reply = await llm.chat([{"role": "user", "content": "Hi"}])
    assert reply == "hello"
    assert call_count == 2


@pytest.mark.asyncio
async def test_chat_without_context_manager_raises() -> None:
    llm = LlmClient()
    with pytest.raises(LlmError, match="context manager"):
        await llm.chat([{"role": "user", "content": "Hi"}])
