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

from src.agent import events, session_history
from src.agent.aliasing import build_catalog_from_dcds
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

        # Build the alias catalog once per request so every tool
        # preview / sql_result emitted during this run renders
        # business-facing entity slugs instead of ``gold_<name>_<uuid>``.
        # The ContextVar token is released in the `finally` wrapper at
        # the bottom of this method so concurrent requests don't leak
        # catalogs into each other.
        catalog_token: object | None = None
        try:
            from src.core.state import get_state

            catalog = build_catalog_from_dcds(get_state().dcds)
            catalog_token = events.set_alias_catalog(catalog)
        except Exception:
            # If state isn't ready (very early boot / tests), skip
            # masking silently — physical names are still correct,
            # just not pretty.
            catalog_token = None

        try:
            async for event in self._run_stream_inner(
                session_id, dataset_id, user_message, t0, model
            ):
                yield event
        finally:
            if catalog_token is not None:
                events.reset_alias_catalog(catalog_token)

    async def _run_stream_inner(
        self,
        session_id: str,
        dataset_id: str,
        user_message: str,
        t0: float,
        model: str,
    ) -> AsyncIterator[events.AgentEvent]:
        """Body of run_stream, wrapped so the alias catalog is always
        released cleanly regardless of how the generator exits."""

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
        # Seed from prior session turns so follow-ups see the full
        # transcript (user questions + agent answers + tool results).
        prior = session_history.get_history(session_id)
        messages: list[dict[str, Any]] = [
            *prior,
            {"role": "user", "content": user_message},
        ]
        turns = 0
        tool_calls_total = 0
        nudged_for_empty = False

        while turns < self.config.max_turns:
            # Call the LLM
            response = await self._call_llm(system, messages)
            assistant_msg = response["choices"][0]["message"]

            # Emit narrative for longer exec-facing prose; thinking for
            # short status-like deliberation. The final summary + ---NEXT---
            # block routinely exceeds 500 chars, so route long content
            # through the narrative path (which has a 6000-char budget and
            # parses the ---NEXT--- marker into follow-up chips).
            content = assistant_msg.get("content")
            if content:
                if len(content) > 400 or "---NEXT---" in content:
                    yield events.narrative(content)
                else:
                    yield events.thinking(content)

            # Build message to append
            msg_to_append: dict[str, Any] = {"role": "assistant"}
            if content:
                msg_to_append["content"] = content
            if assistant_msg.get("tool_calls"):
                msg_to_append["tool_calls"] = assistant_msg["tool_calls"]
            messages.append(msg_to_append)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                # Silent-exit guard. Some models (GLM in particular) end
                # a turn with empty content AND no tool_calls after
                # receiving tool results — the exec sees "Done" with no
                # output. If we've already executed tools in this
                # session, nudge once with a forcing message and retry.
                # If the second pass is still empty, emit a plain-
                # English error narrative so at least *something* is
                # visible instead of a blank chat.
                if (
                    (not content or not content.strip())
                    and tool_calls_total > 0
                    and not nudged_for_empty
                ):
                    nudged_for_empty = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You received tool results but returned "
                                "an empty response. Do NOT stay silent. "
                                "Either: (a) produce the final narrative "
                                "answer the user asked for, or (b) call "
                                "create_artifact / emit_visual to finish "
                                "the task. If you cannot finish, say why "
                                "in one sentence."
                            ),
                        }
                    )
                    # Loop around — same turn budget, retry with nudge
                    continue

                # Ground-truth guard: the agent cited specific numbers
                # (detected via ``[value]()`` citation format OR bare
                # currency/percent tokens) but didn't run a single
                # data tool. That means the figure came from
                # prior-session memory or model priors, not the
                # dataset in front of us. Nudge once to force a
                # verified pull.
                if (
                    content
                    and tool_calls_total == 0
                    and not nudged_for_empty
                    and _content_cites_numbers(content)
                ):
                    nudged_for_empty = True
                    # Don't keep the unverified content in history —
                    # the retry should start fresh.
                    if messages and messages[-1].get("role") == "assistant":
                        messages.pop()
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You cited specific numbers without "
                                "running any data tool. Every figure in "
                                "a Manthan answer must come from a "
                                "compute_metric or run_sql call you "
                                "execute in THIS turn — not memory, not "
                                "priors. Call the appropriate tool(s) "
                                "now and re-answer with verified values."
                            ),
                        }
                    )
                    continue

                # Agent is done — try to load render_spec from disk
                elapsed = time.perf_counter() - t0
                render_spec = await self._load_render_spec(dataset_id)
                session_history.set_history(session_id, messages)

                # If we still have no content after the nudge retry,
                # surface it instead of vanishing.
                if (not content or not content.strip()) and tool_calls_total > 0:
                    yield events.narrative(
                        "I pulled the data but didn't produce a final "
                        "answer — that's a model hiccup, not a missing "
                        "result. Try asking the same question again; the "
                        "cached work should make the retry instant."
                    )

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

                # Handle emit_visual locally (inline visual in conversation)
                if name == "emit_visual":
                    from uuid import uuid4

                    visual_id = f"vis_{uuid4().hex[:8]}"
                    yield events.inline_visual(
                        visual_id=visual_id,
                        visual_type=args.get("visual_type", "stat_card"),
                        html=args.get("html", ""),
                        height=args.get("height", 200),
                    )

                    result_str = json.dumps(
                        {"status": "rendered", "visual_id": visual_id}
                    )
                    tool_calls_total += 1
                    tc_ms = (time.perf_counter() - tc_t0) * 1000
                    yield events.tool_complete(
                        name, f"Rendered: {args.get('visual_type', 'visual')}", tc_ms
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        }
                    )
                    tools_this_turn.append(name)
                    continue

                # Handle ask_user locally so we can emit waiting_for_user
                # (with propose-first structure) between question creation
                # and the blocking wait.
                if name == "ask_user":
                    body: dict[str, Any] = {
                        "session_id": args["session_id"],
                        "prompt": args.get("prompt", ""),
                        "options": args.get("options", []),
                        "allow_free_text": True,
                    }
                    if args.get("proposed_interpretation"):
                        body["proposed_interpretation"] = args[
                            "proposed_interpretation"
                        ]
                    if args.get("why_this_matters"):
                        body["why_this_matters"] = args["why_this_matters"]
                    if args.get("ambiguity_type"):
                        body["ambiguity_type"] = args["ambiguity_type"]

                    try:
                        r_create = await self.router.client.post("/ask_user", json=body)
                        r_create.raise_for_status()
                        q = r_create.json()

                        yield events.waiting_for_user(
                            question_id=q["id"],
                            prompt=args.get("prompt", ""),
                            options=args.get("options", []),
                            interpretation=args.get("proposed_interpretation"),
                            why=args.get("why_this_matters"),
                            ambiguity_type=args.get("ambiguity_type"),
                        )

                        r_wait = await self.router.client.post(
                            f"/ask_user/{q['id']}/wait",
                            params={"timeout_seconds": 30},
                        )
                        r_wait.raise_for_status()
                        result_json = r_wait.json()

                        if result_json.get("timed_out"):
                            result_str = json.dumps(
                                {
                                    "status": "timed_out",
                                    "note": (
                                        "Exec did not respond within 30s. "
                                        "Proceed with your proposed_interpretation."
                                    ),
                                }
                            )
                        else:
                            result_str = r_wait.text
                            answer = result_json.get("answer", "")
                            if answer:
                                yield events.user_answered(answer)
                    except Exception as exc:
                        result_str = json.dumps({"error": str(exc)[:500]})

                    tool_calls_total += 1
                    tc_ms = (time.perf_counter() - tc_t0) * 1000
                    yield events.tool_complete(name, result_str[:400], tc_ms)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        }
                    )
                    tools_this_turn.append(name)
                    continue

                # Handle create_artifact locally (no HTTP dispatch)
                if name == "create_artifact":
                    from uuid import uuid4

                    from src.agent.artifact_repair import (
                        extract_html_from_llm_response,
                        validate_artifact_html_async,
                    )

                    artifact_id = f"art_{uuid4().hex[:8]}"
                    title = args.get("title", "Artifact")
                    html = args.get("html", "")
                    filename = args.get("filename", "artifact.html")

                    # Heal agent-authored SyntaxErrors before anything reads
                    # the HTML. ``events.artifact_created`` would fix the
                    # SSE payload but the on-disk copy serves ``/output/``
                    # (download, browser preview), so fix that too.
                    html = events._close_unclosed_try(html)

                    # Server-side JS parse. If any inline <script> fails
                    # ``node --check``, kick a focused repair pass. One
                    # retry, bounded — if still broken we ship the
                    # original and let the client best-effort-render.
                    validation = await validate_artifact_html_async(html)
                    if not validation.ok and not validation.skipped:
                        yield events.repairing_artifact(artifact_id, validation.error)
                        try:
                            repaired = await self._repair_artifact_html(
                                html, validation.error
                            )
                            repaired = extract_html_from_llm_response(repaired)
                            if repaired.strip():
                                repaired = events._close_unclosed_try(repaired)
                                revalidation = await validate_artifact_html_async(
                                    repaired
                                )
                                if revalidation.ok:
                                    html = repaired
                        except Exception:
                            # Repair is best-effort; fall through with
                            # the (still-broken) original rather than
                            # blocking the conversation.
                            pass

                    # Save to disk for persistence
                    try:
                        from src.core.config import get_settings

                        artifact_dir = (
                            Path(get_settings().data_directory) / dataset_id / "output"
                        )
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        (artifact_dir / filename).write_text(html)
                    except Exception:
                        pass

                    yield events.artifact_created(
                        artifact_id=artifact_id,
                        title=title,
                        code=html,
                        filename=filename,
                    )

                    result_str = json.dumps(
                        {"status": "created", "artifact_id": artifact_id}
                    )
                    tool_calls_total += 1
                    tc_ms = (time.perf_counter() - tc_t0) * 1000
                    yield events.tool_complete(name, f"Created: {title}", tc_ms)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        }
                    )
                    tools_this_turn.append(name)
                    continue

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
                    parsed = None

                if is_err:
                    yield events.tool_error(name, result_str[:300], will_retry=False)
                else:
                    yield events.tool_complete(name, result_str[:400], tc_ms)

                    # Auto-emit sql_result for visible inline tables
                    if name == "run_sql" and parsed and isinstance(parsed, dict):
                        columns = parsed.get("columns", [])
                        rows = parsed.get("rows", [])
                        if columns and rows:
                            yield events.sql_result(
                                tool_call_id=tc["id"],
                                query=args.get("sql", ""),
                                columns=columns,
                                rows=rows,
                                row_count=parsed.get("row_count", len(rows)),
                                truncated=parsed.get("truncated", False),
                                elapsed_ms=tc_ms,
                            )

                        # Phase 3 extension — auto-emit numeric_claim for
                        # run_sql scalar results (1x1). These are the
                        # exec-facing numbers the agent typically cites
                        # inline; without a backing claim the narrative's
                        # number would render without a "How was this
                        # calculated?" drawer. We also emit a claim for
                        # EVERY numeric cell in a small result set
                        # (<=30 cells) so a "by month" table still has
                        # per-value traceability when the agent restates
                        # individual numbers in prose.
                        try:
                            total_cells = sum(len(r) for r in rows)
                        except Exception:
                            total_cells = 0
                        # Expanded from 30 → 200 cells. Execs re-quote
                        # individual cells from bar-chart / table outputs
                        # ("Massachusetts 35.8%", "$24.8M on welfare") and
                        # every one deserves a lineage hook. Above 200
                        # cells the claim list blows up without benefit.
                        if columns and rows and total_cells <= 200:
                            sql_text = args.get("sql", "")
                            for row in rows:
                                for cell, col in zip(row, columns, strict=False):
                                    if not isinstance(cell, (int, float)):
                                        continue
                                    if isinstance(cell, bool):
                                        continue
                                    if _is_dimension_column(col):
                                        continue  # year / id / code — not a measure
                                    unit_guess = _guess_unit(col)
                                    yield events.numeric_claim(
                                        value=float(cell),
                                        formatted=_format_metric_value(
                                            cell, unit_guess
                                        ),
                                        label=_humanize_column_name(col),
                                        description=_describe_sql_cell(col, sql_text),
                                        entity=None,
                                        metric_ref=None,
                                        filters_applied=[],
                                        dimensions=[],
                                        grain=None,
                                        sql=sql_text,
                                        row_count_scanned=parsed.get("row_count"),
                                        run_id=session_id,
                                        unit=unit_guess,
                                    )

                    # Phase 3 audit surface — auto-emit numeric_claim
                    # for EVERY numeric cell in a compute_metric
                    # result, not just scalars. A "top state by
                    # revenue" query returns 1 row × (state, value)
                    # = not a scalar — but the exec still cites that
                    # value in prose ("California at $436.5M"). The
                    # per-cell emit ensures each cited number carries
                    # the metric's rich semantic metadata (governed
                    # description, declared filter, unit) so the
                    # audit drawer lights up instead of falling back
                    # to generic provenance.
                    if (
                        name == "compute_metric"
                        and parsed
                        and isinstance(parsed, dict)
                        and parsed.get("rows")
                    ):
                        cm_cols = parsed.get("columns", [])
                        cm_rows = parsed.get("rows", [])
                        try:
                            cm_cells = sum(len(r) for r in cm_rows)
                        except Exception:
                            cm_cells = 0
                        metric_unit = parsed.get("metric_unit")
                        metric_label = (
                            parsed.get("metric_label")
                            or parsed.get("metric_slug")
                            or name
                        )
                        metric_desc = parsed.get("metric_description")
                        metric_filters = (
                            [parsed["metric_filter"]]
                            if parsed.get("metric_filter")
                            else []
                        )
                        metric_dimensions = parsed.get("dimensions") or []
                        if cm_cols and cm_rows and cm_cells <= 200:
                            for row in cm_rows:
                                for cell, col in zip(row, cm_cols, strict=False):
                                    if not isinstance(cell, (int, float)):
                                        continue
                                    if isinstance(cell, bool):
                                        continue
                                    # Skip the grouping / dimension
                                    # columns that happen to be
                                    # numeric (e.g. year). Only emit
                                    # for the actual metric column(s).
                                    if col in metric_dimensions:
                                        continue
                                    if _is_dimension_column(col):
                                        continue
                                    yield events.numeric_claim(
                                        value=float(cell),
                                        formatted=_format_metric_value(
                                            cell, metric_unit
                                        ),
                                        label=metric_label,
                                        description=metric_desc,
                                        entity=args.get("entity"),
                                        metric_ref=parsed.get("metric_slug"),
                                        filters_applied=list(metric_filters),
                                        dimensions=list(metric_dimensions),
                                        grain=parsed.get("grain"),
                                        sql=parsed.get("sql_used"),
                                        row_count_scanned=parsed.get("row_count"),
                                        run_id=session_id,
                                        unit=metric_unit,
                                    )

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
        session_history.set_history(session_id, messages)
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
            "max_tokens": 131072,
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

    # ── Artifact repair (single-shot fix pass) ───────────────

    async def _repair_artifact_html(
        self,
        broken_html: str,
        parse_error: str,
    ) -> str:
        """Fire one focused LLM call to fix a JS parse error in an
        artifact. Returns the raw model response (caller strips
        fences via ``extract_html_from_llm_response``). Separate from
        ``_call_llm`` because this pass doesn't use the agent's tool
        catalog — it's a single repair prompt, no function calling."""
        from src.agent.artifact_repair import REPAIR_SYSTEM_PROMPT

        payload: dict[str, Any] = {
            "model": self.config.resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": REPAIR_SYSTEM_PROMPT.format(error=parse_error[:1200]),
                },
                {
                    "role": "user",
                    "content": (
                        "Here is the broken artifact HTML. Return the "
                        "complete fixed HTML document, nothing else.\n\n" + broken_html
                    ),
                },
            ],
            "temperature": 0.1,
            "max_tokens": 65536,
        }
        r = await self._llm.post("/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(str(data["error"])[:200])
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("repair: no choices")
        return choices[0].get("message", {}).get("content", "") or ""

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


def _content_cites_numbers(text: str) -> bool:
    """True if the assistant narrative looks like it cites concrete
    numbers — either via the ``[value]()`` citation format the prompt
    mandates, or as bare currency / percentage / large-integer
    tokens. Used to detect zero-tool answers that leaked model-prior
    numbers into prose."""
    if not text:
        return False
    import re

    # ``[anything]()`` — empty-href pattern the agent uses to mark cited numbers
    if re.search(r"\[[^\]]+\]\(\)", text):
        return True
    # Bare currency: $X, $X.XM, $X.XB, $X,XXX.XX
    if re.search(r"\$\s*\d[\d,.]*\s*(?:[KMBT](?!\w))?", text):
        return True
    # Bare percentage: "12.3%"
    if re.search(r"\b\d+(?:\.\d+)?\s*%", text):
        return True
    # Big integers (4+ digits, likely counts): "313,000" or "313000 flights"
    return bool(re.search(r"\b\d{1,3}(?:,\d{3})+\b", text))


def _describe_sql_cell(
    column: str,
    sql: str,
    entity: str | None = None,
) -> str | None:
    """Plain-English one-liner for a numeric cell produced by run_sql.

    Parses the SQL with simple regex (full sqlglot is overkill for a
    one-line description) and composes ``{aggregation} {column} [from
    {entity}] [where {filter}]``. The drawer renders this in its
    "What this measures" section. Falls back to ``None`` for
    unparseable SQL — the drawer then uses a column-label heuristic.
    """
    if not sql:
        return None
    col_label = _humanize_column_name(column)
    import re

    # Detect aggregation by matching the result column in the SELECT
    # list. Supports both ``SUM(x) AS col`` and ``SUM(x) col`` forms.
    agg_word = None
    patterns = [
        # "SUM(expr) AS column"
        rf"(SUM|AVG|COUNT|MIN|MAX|MEDIAN)\s*\([^)]*\)\s+AS\s+\"?{re.escape(column)}\"?",
        # "SUM(expr) column" (AS omitted)
        rf"(SUM|AVG|COUNT|MIN|MAX|MEDIAN)\s*\([^)]*\)\s+\"?{re.escape(column)}\"?",
    ]
    for pat in patterns:
        m = re.search(pat, sql, re.IGNORECASE)
        if m:
            agg_word = m.group(1).upper()
            break
    agg_verb = {
        "SUM": "Total",
        "AVG": "Average",
        "COUNT": "Count of",
        "MIN": "Lowest",
        "MAX": "Highest",
        "MEDIAN": "Median",
    }.get(agg_word or "", "")

    # Avoid redundant phrasing when the column alias already carries
    # the aggregation word or its common abbreviations
    # ("total_revenue" + "Total" reads as "Total Total Revenue").
    redundancy = {
        "SUM": {"total", "sum"},
        "AVG": {"avg", "average", "mean"},
        "COUNT": {"count", "num", "n"},
        "MIN": {"min", "lowest"},
        "MAX": {"max", "highest", "top"},
        "MEDIAN": {"median"},
    }.get(agg_word or "", set())
    col_words = {w.lower() for w in col_label.split()}
    if agg_verb and (col_words & redundancy):
        agg_verb = ""
    subject = f"{agg_verb} {col_label}".strip() if agg_verb else col_label
    parts = [subject]
    if entity:
        parts.append(f"from {entity}")

    where_m = re.search(
        r"\bWHERE\s+(.+?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|\s+HAVING|\s+LIMIT|\s*$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if where_m:
        raw_where = where_m.group(1).strip().rstrip(";")
        # Keep it short; the drawer renders filters in its own section.
        if len(raw_where) < 90:
            parts.append(f"where {raw_where}")
    return ", ".join(parts).strip() or None


def _humanize_column_name(name: str) -> str:
    """Turn a raw dataset column name into an exec-facing label.

    Examples:
      ``Totals.Revenue`` → ``Revenue``
      ``Details.Education.Education Total`` → ``Education Total``
      ``on_time_rate`` → ``On Time Rate``
      ``debt_to_revenue_pct`` → ``Debt To Revenue Pct``

    The rule is "last meaningful segment, underscores to spaces,
    Title Case". Dotted paths are a DCD convention
    (``{group}.{subgroup}.{metric}``) where the final segment is the
    name an exec would recognize.
    """
    if not name:
        return name
    # Keep only the last dotted segment; the path before it is internal.
    last = name.rsplit(".", 1)[-1].strip()
    if not last:
        return name
    return last.replace("_", " ").strip().title()


_MONEY_COL_HINTS = (
    "revenue",
    "expenditure",
    "spending",
    "spend",
    "cost",
    "price",
    "amount",
    "total",
    "debt",
    "funding",
    "budget",
    "tax",
    "wage",
    "income",
    "profit",
    "loss",
    "salary",
    "pay",
    "capital",
    "value",
    "assets",
    "liabilities",
    "subtotal",
    "grand_total",
    "usd",
    "dollars",
    "dollar",
)
_PCT_COL_HINTS = ("pct", "percent", "_rate", "ratio", "share")
# Columns whose values are labels/dimensions even when stored as
# integers. Skipping these from auto-claim emission — they never make
# sense as "Cited numbers" with audit drawers ("how was the year 2019
# calculated?" is nonsense).
_DIMENSION_COL_PATTERNS = (
    "year",
    "month",
    "day",
    "quarter",
    "week",
    "fiscal_year",
    "fy",
    "_id",
    "_code",
    "_key",
    "_sku",
    "zip",
    "zipcode",
    "postal",
    "fips",
    "pin",
    "phone",
)


def _is_dimension_column(name: str) -> bool:
    if not name:
        return False
    low = name.lower().replace(" ", "_").rsplit(".", 1)[-1]
    # Normalise the hint list: ``_id`` and ``id`` should both catch
    # bare ``Code`` / ``id`` as well as suffixed ``state_id`` /
    # ``zip_code``. Deduped at comparison time.
    for hint in _DIMENSION_COL_PATTERNS:
        bare = hint.lstrip("_")
        if (
            low in (hint, bare)
            or low.endswith("_" + bare)
            or low.startswith(bare + "_")
        ):
            return True
    return False


def _guess_unit(column: str | None) -> str | None:
    """Infer a display unit from a column name.

    The run_sql tool doesn't carry explicit units per column, but the
    column name almost always does ("Totals.Revenue" → money,
    "on_time_rate" → percent). We use this when auto-emitting
    ``numeric_claim`` events so the formatted string matches what the
    exec sees in the narrative — ``$436.5M`` instead of ``436,532,750``.
    """
    if not column:
        return None
    low = column.lower()
    for hint in _PCT_COL_HINTS:
        if hint in low:
            return "percent"
    for hint in _MONEY_COL_HINTS:
        if hint in low:
            return "USD"
    return None


def _format_metric_value(value: float, unit: str | None) -> str:
    """Light exec-friendly formatting for a numeric_claim's display
    string. The agent can always override by authoring its own text
    in the narrative; this is the drawer-label fallback."""
    if value is None:
        return "—"
    unit_l = (unit or "").lower()
    if unit_l in {"usd", "eur", "gbp", "inr", "cad", "aud"}:
        sign = "-" if value < 0 else ""
        absval = abs(value)
        if absval >= 1_000_000_000:
            return f"{sign}${absval / 1_000_000_000:.1f}B"
        if absval >= 1_000_000:
            return f"{sign}${absval / 1_000_000:.1f}M"
        if absval >= 1_000:
            return f"{sign}${absval / 1_000:.1f}K"
        return f"{sign}${absval:,.2f}"
    if unit_l in {"percent", "%"}:
        return f"{value:.1f}%"
    # Integer-looking values
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return f"{int(value):,}"
    return f"{value:,.2f}"
