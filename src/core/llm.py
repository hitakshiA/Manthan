"""OpenRouter API client.

Thin async wrapper around the OpenRouter chat completions endpoint, used by
the Silver-stage profiling agent for column classification, description
generation, and clarification-question drafting. The client is intentionally
small: no streaming, no function calling, no automatic retry. Higher-level
retry and caching policies belong in the profiling module.

Usage:
    async with LlmClient() as llm:
        reply = await llm.chat([{"role": "user", "content": "hello"}])
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import httpx

from src.core.config import Settings, get_settings
from src.core.exceptions import LlmError, LlmTimeoutError
from src.core.logger import get_logger

_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE_SECONDS = 1.0
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_logger = get_logger()


class LlmClient:
    """Async client for OpenRouter-hosted chat completion models.

    The client owns its underlying :class:`httpx.AsyncClient` by default,
    but callers may inject a pre-configured client (useful for tests that
    want to install an :class:`httpx.MockTransport`).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        self._settings = settings or get_settings()
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None
        self._max_retries = max_retries

    async def __aenter__(self) -> LlmClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.openrouter_base_url,
                headers={
                    "Authorization": (
                        f"Bearer {self._settings.openrouter_api_key.get_secret_value()}"
                    ),
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the assistant text.

        Args:
            messages: OpenAI-style messages list. Each item must have
                ``role`` and ``content`` keys.
            model: Optional model slug override. Defaults to
                ``settings.openrouter_model``.
            temperature: Sampling temperature (default ``0.0`` for
                deterministic classification work).
            max_tokens: Optional ceiling on completion tokens.

        Returns:
            The assistant message content string.

        Raises:
            LlmError: If the client was not entered as an async context
                manager, the API returned a non-2xx status, or the response
                body could not be parsed.
            LlmTimeoutError: If the request exceeded the configured timeout.
        """
        if self._client is None:
            raise LlmError("LlmClient must be used as an async context manager")

        payload: dict[str, Any] = {
            "model": model or self._settings.openrouter_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                break
            except httpx.TimeoutException:
                last_error = LlmTimeoutError(
                    f"OpenRouter request timed out (attempt {attempt}/"
                    f"{self._max_retries})"
                )
                _logger.warning("llm.timeout", attempt=attempt, model=payload["model"])
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in _RETRYABLE_STATUS_CODES:
                    _logger.warning(
                        "llm.http_status_fatal",
                        status_code=status,
                        model=payload["model"],
                    )
                    raise LlmError(f"OpenRouter returned HTTP {status}") from exc
                last_error = LlmError(f"OpenRouter returned HTTP {status}")
                _logger.warning(
                    "llm.http_status_retryable",
                    attempt=attempt,
                    status_code=status,
                )
            except httpx.HTTPError as exc:
                last_error = LlmError(f"OpenRouter transport error: {exc}")
                _logger.warning("llm.transport_error", attempt=attempt, error=str(exc))

            if attempt < self._max_retries:
                await asyncio.sleep(_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
        else:
            raise (
                last_error
                if last_error is not None
                else LlmError("OpenRouter request failed without a captured error")
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LlmError(f"Malformed OpenRouter response: {exc}") from exc
