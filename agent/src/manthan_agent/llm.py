"""OpenRouter LLM client.

Thin wrapper around the official `openai` SDK pointed at OpenRouter's
OpenAI-compatible endpoint. The model is a config string so we can swap
between deepseek / claude / gpt / gemini by changing one env var.

The agent loop in agent.py calls chat() in a loop, handling tool_calls
on the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion

from .config import Config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMNotConfigured(RuntimeError):
    """Raised when OPENROUTER_API_KEY is missing."""


def client(cfg: Config) -> OpenAI:
    """Return an OpenAI client pointed at OpenRouter.

    Sets the OpenRouter attribution headers so usage shows up under the
    Manthan project on the OpenRouter dashboard.
    """
    if not cfg.openrouter_api_key:
        raise LLMNotConfigured(
            "OPENROUTER_API_KEY is not set. "
            "Add it to manthanv2/agent/.env and re-run."
        )
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=cfg.openrouter_api_key,
        default_headers={
            "HTTP-Referer": "https://manthan-ui.vercel.app",
            "X-Title": "Manthan",
            # Forward strict-mode tool calls to providers that support it.
            # Without this header OpenRouter strips `strict: true` from the
            # tool-call schema. With it, DeepSeek's beta strict-mode kicks
            # in (constrained decoding at the token level - the model
            # literally cannot emit a malformed tool call).
            "structured-outputs-2025-11-13": "true",
        },
    )


def chat(
    cfg: Config,
    messages: list[dict[str, Any]],
    *,
    tools: Iterable[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> ChatCompletion:
    """One-shot chat completion. Returns the raw OpenAI response object.

    The agent loop is responsible for inspecting `response.choices[0].message`
    for `tool_calls`, executing them, and appending the result back to the
    messages list before calling chat() again.
    """
    return client(cfg).chat.completions.create(
        model=cfg.model,
        messages=messages,
        tools=list(tools) if tools else None,
        temperature=temperature,
        max_tokens=max_tokens,
    )
