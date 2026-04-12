"""The agent loop — one while-loop, well-defined tools.

Architecture follows Claude Code's pattern: a single async loop
where the LLM reasons, emits tool calls, observes results, and
iterates. Rich SSE events emitted at every decision point so
any frontend can render a live, transparent agent experience.

Key production features:
- Auto-discovery: tables are discovered BEFORE the first LLM call
  and injected into the system prompt (no reliance on the LLM
  remembering to call SHOW TABLES)
- Micro-level SSE: events emitted for discovery, thinking, tool
  start/complete, errors, plan gates, subagent lifecycle
- Tool result truncation: large results trimmed to stay within
  context budget
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
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

    # ── Auto-discovery ────────────────────────────────────────

    async def _discover_tables(self, dataset_id: str) -> list[str]:
        """Run SHOW TABLES before the loop starts. Returns table names."""
        try:
            r = await self.router.client.post(
                "/tools/sql",
                json={
                    "dataset_id": dataset_id,
                    "sql": "SHOW TABLES",
                    "max_rows": 200,
                },
            )
            if r.status_code == 200:
                data = r.json()
                return [row[0] for row in data.get("rows", [])]
        except Exception:
            pass
        return []

    # ── Synchronous run (for /agent/query/sync) ───────────────

    async def run(
        self,
        session_id: str,
        dataset_id: str,
        user_message: str,
    ) -> AgentResult:
        """Run the full agent loop. Collects events internally."""
        all_events: list[events.AgentEvent] = []

        async for event in self.run_stream(session_id, dataset_id, user_message):
            all_events.append(event)

        # Extract final text from the done event
        final_text = ""
        turns = 0
        tool_calls_total = 0
        elapsed = 0.0
        for e in reversed(all_events):
            if e.type == "done":
                final_text = e.data.get("summary", "")
                turns = e.data.get("turns", 0)
                tool_calls_total = e.data.get("tool_calls", 0)
                elapsed = e.data.get("elapsed_seconds", 0.0)
                break

        return AgentResult(
            text=final_text,
            turns=turns,
            tool_calls_total=tool_calls_total,
            elapsed_seconds=elapsed,
            events_emitted=all_events,
        )

    # ── Streaming run (for /agent/query SSE) ──────────────────

    async def run_stream(
        self,
        session_id: str,
        dataset_id: str,
        user_message: str,
    ) -> AsyncIterator[events.AgentEvent]:
        """Run the agent loop, yielding SSE events in real time."""
        t0 = time.perf_counter()
        model = self.config.resolved_model

        # ── Phase 0: Session start ──
        yield events.session_start(session_id, dataset_id, model)

        # ── Phase 1: Auto-discover tables ──
        yield events.discovering_tables(dataset_id)
        table_names = await self._discover_tables(dataset_id)
        yield events.tables_found(table_names, len(table_names))

        # ── Phase 2: Assemble system prompt with tables ──
        yield events.loading_schema(dataset_id)
        system = await assemble_prompt(self.config, dataset_id, table_names)

        # ── Phase 3: Check memory ──
        yield events.checking_memory(dataset_id)
        # (memory check is done inside assemble_prompt)

        # ── Phase 4: The loop ──
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]
        turns = 0
        tool_calls_total = 0

        while turns < self.config.max_turns:
            # Call the LLM
            response = await self._call_llm(system, messages)
            assistant_msg = response["choices"][0]["message"]

            # Emit thinking if the model produced text alongside tools
            content = assistant_msg.get("content")
            if content:
                yield events.thinking(content[:500])

            # Build message to append
            msg_to_append: dict[str, Any] = {"role": "assistant"}
            if content:
                msg_to_append["content"] = content
            if assistant_msg.get("tool_calls"):
                msg_to_append["tool_calls"] = assistant_msg["tool_calls"]
            messages.append(msg_to_append)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                # Agent is done — try to load render_spec from disk
                elapsed = time.perf_counter() - t0
                render_spec = await self._load_render_spec(dataset_id)
                yield events.done(
                    content or "",
                    turns,
                    tool_calls=tool_calls_total,
                    elapsed=elapsed,
                    render_spec=render_spec,
                )
                return

            # Execute each tool call
            tools_this_turn: list[str] = []
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}

                yield events.tool_start(name, args, turns + 1)
                tc_t0 = time.perf_counter()

                result_str = await self.router.execute(name, args)
                tool_calls_total += 1
                tc_ms = (time.perf_counter() - tc_t0) * 1000

                # Check for errors in the result
                is_err = False
                try:
                    parsed = json.loads(result_str)
                    if isinstance(parsed, dict) and "error" in parsed:
                        is_err = True
                except Exception:
                    pass

                if is_err:
                    yield events.tool_error(name, result_str[:300], will_retry=False)
                else:
                    yield events.tool_complete(name, result_str[:400], tc_ms)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    }
                )
                tools_this_turn.append(name)

            yield events.turn_complete(turns + 1, tools_this_turn)
            turns += 1

        # Max turns exceeded
        elapsed = time.perf_counter() - t0
        yield events.error("Max turns reached", recoverable=False)
        yield events.done(
            "Analysis incomplete — max turns reached.",
            turns,
            tool_calls=tool_calls_total,
            elapsed=elapsed,
        )

    # ── LLM call with retry ──────────────────────────────────

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

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._llm.post("/chat/completions", json=payload)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and "error" in data:
                    last_error = RuntimeError(str(data["error"])[:200])
                    continue
                choices = data.get("choices")
                if choices and isinstance(choices, list):
                    return data
                last_error = RuntimeError("No choices in response")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    import asyncio

                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                last_error = exc
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < 2:
                    continue
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"LLM failed after 3 attempts: {last_error}")

    # ── Render spec loader ──────────────────────────────────

    async def _load_render_spec(self, dataset_id: str) -> dict[str, Any] | None:
        """Try to read render_spec.json from the dataset output directory."""
        try:
            from src.core.config import get_settings

            out = Path(get_settings().data_directory) / dataset_id
            spec_path = out / "output" / "render_spec.json"
            if spec_path.exists() and spec_path.stat().st_size > 0:
                return json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None
