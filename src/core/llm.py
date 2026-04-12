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

_DEFAULT_TIMEOUT_SECONDS = 180.0
# With a 3-model cascade, each model gets a SHORT retry window.
# The cascade itself is the redundancy — don't burn 4 minutes
# retrying one model when there are two more to try.
_DEFAULT_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE_SECONDS = 2.0
_RETRY_BACKOFF_CAP_SECONDS = 10.0
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

        Tries the primary model first, then each fallback model in order.
        Each model gets the full retry budget. If all models fail, the
        last error is raised so the caller (typically the classifier)
        can fall back to the heuristic path.

        The model cascade is:

        1. ``model`` param (if provided) or ``settings.openrouter_model``
        2. Each model in ``settings.openrouter_fallback_models`` (in order)

        This gives Layer 1 provider diversification: if Google AI Studio
        rate-limits Gemma, we try NVIDIA's Nemotron, then OpenInference's
        gpt-oss, and only then fall back to the deterministic heuristic.
        """
        if self._client is None:
            raise LlmError("LlmClient must be used as an async context manager")

        # Build the ordered model cascade.
        primary = model or self._settings.resolved_model
        fallbacks = list(self._settings.resolved_fallback_models)
        model_cascade = [primary, *fallbacks]

        last_error: Exception | None = None
        for model_slug in model_cascade:
            try:
                result = await self._try_model(
                    model_slug,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return result
            except (LlmError, LlmTimeoutError) as exc:
                last_error = exc
                _logger.warning(
                    "llm.model_failed_trying_next",
                    failed_model=model_slug,
                    error=str(exc)[:200],
                    remaining=len(model_cascade) - model_cascade.index(model_slug) - 1,
                )
                continue

        raise (
            last_error
            if last_error is not None
            else LlmError("All models in cascade failed")
        )

    async def _try_model(
        self,
        model_slug: str,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """Try one model with the full retry budget. Raises on failure."""
        payload: dict[str, Any] = {
            "model": model_slug,
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
                # OpenRouter occasionally returns HTTP 200 with a semantic
                # error envelope (e.g. upstream provider drop / queue
                # timeout surfaced as ``{"error": {...}}``). Treat that
                # the same as a retryable transport error so a provider
                # hiccup on attempt 1 does not kill the whole pipeline.
                data = response.json()
                if isinstance(data, dict) and "error" in data:
                    err_detail = data["error"]
                    last_error = LlmError(
                        f"OpenRouter returned 200 with error envelope: {err_detail}"
                    )
                    _logger.warning(
                        "llm.body_error_envelope",
                        attempt=attempt,
                        error=str(err_detail)[:200],
                    )
                elif (
                    not isinstance(data, dict)
                    or not data.get("choices")
                    or not isinstance(data["choices"], list)
                    or "message" not in data["choices"][0]
                    or "content" not in data["choices"][0]["message"]
                    or data["choices"][0]["message"].get("content") is None
                ):
                    last_error = LlmError(
                        f"OpenRouter response missing choices/message/content: "
                        f"{str(data)[:200]}"
                    )
                    _logger.warning(
                        "llm.body_missing_choices",
                        attempt=attempt,
                        body_preview=str(data)[:200],
                    )
                else:
                    return data["choices"][0]["message"]["content"]
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
                # Any 429 = this model is rate-limited. Don't retry
                # the same model — immediately bail out to let the
                # cascade try the next model in the list. This keeps
                # total cascade time under 30s instead of burning
                # minutes retrying a rate-limited provider.
                if status == 429:
                    _logger.warning(
                        "llm.rate_limited_skip_to_next",
                        status_code=status,
                        model=payload["model"],
                    )
                    raise LlmError(
                        f"Model {payload['model']} rate-limited (429)"
                    ) from exc
                last_error = LlmError(f"OpenRouter returned HTTP {status}")
                _logger.warning(
                    "llm.http_status_retryable",
                    attempt=attempt,
                    status_code=status,
                )
            except httpx.HTTPError as exc:
                last_error = LlmError(f"OpenRouter transport error: {exc}")
                _logger.warning("llm.transport_error", attempt=attempt, error=str(exc))
            except ValueError as exc:
                # response.json() parse failure — treat as retryable
                last_error = LlmError(f"OpenRouter response not JSON: {exc}")
                _logger.warning("llm.body_not_json", attempt=attempt, error=str(exc))

            if attempt < self._max_retries:
                backoff = min(
                    _RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                    _RETRY_BACKOFF_CAP_SECONDS,
                )
                await asyncio.sleep(backoff)

        raise (
            last_error
            if last_error is not None
            else LlmError("OpenRouter request failed without a captured error")
        )
