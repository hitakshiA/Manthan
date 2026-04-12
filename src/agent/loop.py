"""The agent loop — one while-loop, well-defined tools.

This is Layer 2's entire brain. The LLM reasons, emits tool calls,
observes results, and iterates until it responds with plain text.
No framework, no state machine, no multi-agent swarm.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.agent import events
from src.agent.config import AgentConfig
from src.agent.prompt import assemble_prompt
from src.agent.tools import TOOL_DEFINITIONS, ToolRouter


@dataclass
class AgentResult:
    """Final output of an agent run."""

    text: str
    turns: int
    tool_calls_total: int
    elapsed_seconds: float
    events_emitted: list[events.AgentEvent] = field(default_factory=list)


class ManthanAgent:
    """The autonomous analyst agent."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        # Resolve API key: agent config → env var → Layer 1 settings
        api_key = self.config.openrouter_api_key
        if not api_key:
            from src.core.config import get_settings

            api_key = get_settings().openrouter_api_key.get_secret_value()
        self.router = ToolRouter(self.config)
        self._llm = httpx.AsyncClient(
            base_url=self.config.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=float(self.config.timeout_seconds),
        )

    async def close(self) -> None:
        await self.router.close()
        await self._llm.aclose()

    async def __aenter__(self) -> ManthanAgent:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def run(
        self,
        session_id: str,
        dataset_id: str,
        user_message: str,
    ) -> AgentResult:
        """Run the full agent loop. Returns when the LLM is done."""
        t0 = time.perf_counter()
        system = await assemble_prompt(self.config, dataset_id)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]
        turns = 0
        tool_calls_total = 0
        all_events: list[events.AgentEvent] = []
        final_text = ""

        while turns < self.config.max_turns:
            # Call the LLM
            response = await self._call_llm(system, messages)
            assistant_msg = response["choices"][0]["message"]

            # Build the assistant message for the messages list
            msg_to_append: dict[str, Any] = {
                "role": "assistant",
            }
            if assistant_msg.get("content"):
                msg_to_append["content"] = assistant_msg["content"]
            if assistant_msg.get("tool_calls"):
                msg_to_append["tool_calls"] = assistant_msg["tool_calls"]
            messages.append(msg_to_append)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                # Agent is done — responded with plain text
                final_text = assistant_msg.get("content", "")
                all_events.append(events.done(final_text, turns))
                break

            # Execute each tool call
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}

                all_events.append(events.tool_call(name, json.dumps(args)[:200]))
                print(
                    f"  [agent] turn={turns + 1} tool={name} args={json.dumps(args)[:120]}"
                )

                result_str = await self.router.execute(name, args)
                tool_calls_total += 1
                print(f"  [agent] result={result_str[:150]}")

                all_events.append(events.tool_result(name, result_str[:300]))

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    }
                )

            turns += 1

        elapsed = time.perf_counter() - t0
        return AgentResult(
            text=final_text,
            turns=turns,
            tool_calls_total=tool_calls_total,
            elapsed_seconds=round(elapsed, 2),
            events_emitted=all_events,
        )

    async def run_stream(
        self,
        session_id: str,
        dataset_id: str,
        user_message: str,
    ) -> AsyncIterator[events.AgentEvent]:
        """Run the agent loop, yielding SSE events as they happen."""
        system = await assemble_prompt(self.config, dataset_id)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]
        turns = 0

        while turns < self.config.max_turns:
            response = await self._call_llm(system, messages)
            assistant_msg = response["choices"][0]["message"]

            msg_to_append: dict[str, Any] = {"role": "assistant"}
            if assistant_msg.get("content"):
                msg_to_append["content"] = assistant_msg["content"]
                yield events.thinking(assistant_msg["content"][:500])
            if assistant_msg.get("tool_calls"):
                msg_to_append["tool_calls"] = assistant_msg["tool_calls"]
            messages.append(msg_to_append)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                yield events.done(assistant_msg.get("content", ""), turns)
                return

            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}

                yield events.tool_call(name, json.dumps(args)[:200])
                result_str = await self.router.execute(name, args)
                yield events.tool_result(name, result_str[:300])

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    }
                )

            turns += 1

        yield events.error("Max turns reached", recoverable=False)

    async def _call_llm(
        self,
        system: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call OpenRouter with the current messages + tools."""
        payload: dict[str, Any] = {
            "model": self.config.resolved_model,
            "messages": [
                {"role": "system", "content": system},
                *messages,
            ],
            "tools": TOOL_DEFINITIONS,
            "temperature": self.config.temperature,
        }

        for attempt in range(3):
            try:
                r = await self._llm.post("/chat/completions", json=payload)
                r.raise_for_status()
                data = r.json()
                if data.get("choices"):
                    return data
                # Retry on malformed response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    import asyncio

                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                raise
            except httpx.TimeoutException:
                if attempt < 2:
                    continue
                raise

        raise RuntimeError("LLM call failed after 3 attempts")
