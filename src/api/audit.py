"""On-demand, streaming audit description for a cited number.

Every numeric_claim event already carries a regex-built ``description``
— enough for 80% of drawer opens. But the whole point of the audit
drawer is to let an analyst or exec **trace a number back to its
semantic contract**, not just read a tidy summary. So when the drawer
opens we fire a focused LLM call that reads the full DCD metric
contract (slug, label, expression, filter, unit, aggregation
semantics, grain, synonyms), re-examines the run-level filters and
dimensions, and writes a 2–3 sentence audit trail explicitly naming
the governed metric and the provenance chain.

We stream token-by-token via SSE so the drawer renders the description
as it's composed. The final ``done`` event carries the full masked
description plus a cache key so the client can memoize repeat opens.

If the model emits only reasoning and no content (common with GLM
:exacto), we salvage the last paragraph of the reasoning trace as the
description. If anything fails, the stream terminates with an error
event and the drawer falls back to the regex summary already on the
claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.aliasing import build_catalog_from_dcds
from src.agent.config import AgentConfig
from src.agent.events import reset_alias_catalog, set_alias_catalog
from src.core.state import AppState, get_state
from src.semantic.schema import DataContextDocument, DcdMetric

StateDep = Annotated[AppState, Depends(get_state)]

router = APIRouter(prefix="/audit", tags=["audit"])


class ClaimDescribeRequest(BaseModel):
    """Everything the drawer knows about the clicked claim plus the
    dataset id so we can look up the DCD for extra context."""

    dataset_id: str
    value: float
    formatted: str
    label: str | None = None
    entity: str | None = None
    metric_ref: str | None = None
    filters_applied: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    grain: str | None = None
    sql: str | None = None
    row_count_scanned: int | None = None
    current_description: str | None = Field(
        default=None,
        description=(
            "The best description we have right now — usually the "
            "regex-generated one. The LLM treats it as a starting "
            "point and may refine / expand it."
        ),
    )


class ClaimDescribeResponse(BaseModel):
    """Non-streaming response shape. Kept for clients that don't want SSE."""

    description: str
    cache_key: str


SYSTEM_PROMPT = """\
Write a 3-sentence business-English audit sentence for a cited number — the sentence an analyst needs to defend the number in a board meeting.

Name the metric or column (using the DCD label, never the physical dotted name). State how it's derived — for a governed metric, quote its contract filter in backticks; for raw SQL, describe the expression in plain English. Weave in the run-level filters and dimensions with their values in backticks. Close by citing the evidence: "calculated from N of M rows from the {dataset} (from `filename`, ingested DD Mon YYYY)" when those fields are provided, plus any quality caveat that matters.

Use backticks for slugs, identifiers, and filter predicates — the drawer renders them as chips. Never use physical table names. Never invent facts. Output only the finished 3-sentence audit paragraph as flowing prose — no preamble, no headers, no numbered steps, no bullet list, no "Draft:" or "Sentence N:" labels.
"""


def _find_metric(dcd: DataContextDocument, metric_ref: str | None) -> DcdMetric | None:
    """Locate the governed metric contract by slug."""
    if not metric_ref or not dcd.dataset.entity:
        return None
    for m in dcd.dataset.entity.metrics:
        if m.slug == metric_ref:
            return m
    return None


def _referenced_columns(sql: str | None, dcd: DataContextDocument | None) -> list[Any]:
    """Best-effort match of DCD columns appearing in the SQL.

    We don't need to parse SQL properly — we just need the columns
    the LLM should cite so it can say "Sum of the Debt at end of
    fiscal year field" instead of generic "a column". A column is
    considered referenced if its raw name (or any of its synonyms)
    occurs as a substring of the SQL, case-insensitive. False
    positives on generic words are bounded by DCD columns being
    domain-specific, and rare false matches don't hurt — the LLM
    cites the ones that make sense contextually.
    """
    if not sql or not dcd:
        return []
    sql_low = sql.lower()
    referenced: list[Any] = []
    seen: set[str] = set()
    # Search the single-table columns list first, then any multi-table
    # tables' columns for multi-file datasets.
    pools = [dcd.dataset.columns]
    for t in dcd.dataset.tables:
        pools.append(t.columns)
    for cols in pools:
        for col in cols:
            if col.name in seen:
                continue
            candidates = [col.name]
            if col.label:
                candidates.append(col.label)
            candidates.extend(col.synonyms or [])
            for cand in candidates:
                if not cand or len(cand) < 3:
                    continue
                if cand.lower() in sql_low:
                    referenced.append(col)
                    seen.add(col.name)
                    break
    # Cap to keep prompt focused.
    return referenced[:8]


def _format_ingested_at(source_ingested_at: Any) -> str:
    """Render the DCD ingestion timestamp as a short human date."""
    if not source_ingested_at:
        return ""
    try:
        return source_ingested_at.strftime("%d %b %Y")
    except AttributeError:
        s = str(source_ingested_at)
        return s[:10] if len(s) >= 10 else s


def _build_user_prompt(
    req: ClaimDescribeRequest,
    dcd: DataContextDocument | None,
    metric: DcdMetric | None,
) -> str:
    """Compose a structured context block for the LLM.

    The goal is to give the model the exact pieces of the semantic
    contract it needs to cite, in a predictable layout so it can't
    miss them. We explicitly separate CONTRACT vs RUN so the prompt
    instruction to state the contract first and then layer the run
    filters maps cleanly onto headings.
    """
    lines: list[str] = []
    lines.append("=== CITED NUMBER ===")
    lines.append(f"Value: {req.formatted} (raw {req.value})")
    if req.label:
        lines.append(f"Label: {req.label}")

    if dcd and dcd.dataset.entity:
        lines.append("")
        lines.append("=== ENTITY (semantic layer) ===")
        ent = dcd.dataset.entity
        lines.append(f"Name: {ent.name}")
        lines.append(f"Slug: {ent.slug}")
        if ent.description:
            lines.append(f"Description: {ent.description[:300]}")
    elif req.entity:
        lines.append("")
        lines.append("=== ENTITY ===")
        lines.append(f"Slug: {req.entity} (no governed entity metadata)")

    if metric:
        lines.append("")
        lines.append("=== GOVERNED METRIC CONTRACT (source of truth) ===")
        lines.append(f"Label: {metric.label}")
        lines.append(f"Slug: {metric.slug}")
        if metric.description:
            lines.append(f"Business definition: {metric.description}")
        lines.append(f"SQL expression: {metric.expression}")
        if metric.filter:
            lines.append(f"Always-applied filter (contract): {metric.filter}")
        else:
            lines.append("Always-applied filter (contract): (none)")
        if metric.unit:
            lines.append(f"Unit: {metric.unit}")
        lines.append(f"Aggregation semantics: {metric.aggregation_semantics}")
        if metric.default_grain:
            lines.append(f"Default grain: {metric.default_grain}")
        if metric.valid_dimensions:
            lines.append(
                f"Valid slice dimensions: {', '.join(metric.valid_dimensions)}"
            )
        if metric.synonyms:
            lines.append(f"Synonyms: {', '.join(metric.synonyms)}")
    elif req.metric_ref:
        lines.append("")
        lines.append("=== GOVERNED METRIC CONTRACT ===")
        lines.append(f"Slug referenced: {req.metric_ref} (contract not found in DCD)")
    else:
        lines.append("")
        lines.append("=== GOVERNED METRIC CONTRACT ===")
        lines.append(
            "(none — this number was not produced via a named governed metric; "
            "describe the expression in plain English)"
        )

    # Source columns actually touched by the SQL — give the LLM the
    # business labels so it can name columns in prose instead of
    # saying "a column". Each entry carries role + completeness so
    # the prompt can flag "not 100% populated" when relevant.
    ref_cols = _referenced_columns(req.sql, dcd)
    if ref_cols:
        lines.append("")
        lines.append("=== SOURCE COLUMNS TOUCHED BY THE SQL ===")
        for col in ref_cols:
            label = col.label or col.name
            parts = [f"- {label} (physical: {col.name})"]
            parts.append(f"  role: {col.role}")
            if col.description:
                parts.append(f"  description: {col.description[:200]}")
            if col.completeness is not None and col.completeness < 1.0:
                parts.append(
                    f"  completeness: {col.completeness * 100:.1f}% "
                    f"(NOT fully populated — flag in audit if relevant)"
                )
            if col.aggregation:
                parts.append(f"  typical aggregation: {col.aggregation}")
            lines.extend(parts)

    # Dataset scope — the denominator for "of N rows" framing, plus
    # source provenance for the audit footer.
    if dcd:
        ds = dcd.dataset
        lines.append("")
        lines.append("=== DATASET SCOPE (for audit footer) ===")
        lines.append(f"Dataset name: {ds.name}")
        lines.append(f"Total rows in the dataset: {ds.source.row_count}")
        if ds.source.original_filename:
            lines.append(f"Source filename: {ds.source.original_filename}")
        ingested = _format_ingested_at(ds.source.ingested_at)
        if ingested:
            lines.append(f"Ingested at: {ingested}")
        if ds.temporal and ds.temporal.range:
            r = ds.temporal.range
            if r.start and r.end:
                lines.append(f"Temporal coverage: {r.start} to {r.end}")
        if ds.quality and ds.quality.known_limitations:
            lines.append("Known data-quality limitations:")
            for lim in ds.quality.known_limitations[:3]:
                lines.append(f"  - {lim}")
        if ds.quality and ds.quality.overall_score < 0.9:
            lines.append(
                f"Overall quality score: {ds.quality.overall_score:.2f} "
                f"(below 0.9 — consider flagging)"
            )

    lines.append("")
    lines.append("=== THIS RUN ===")
    if req.filters_applied:
        lines.append("Filters applied on top of the contract:")
        for f in req.filters_applied:
            lines.append(f"  - {f}")
    else:
        lines.append("Filters applied on top of the contract: (none)")
    if req.dimensions:
        lines.append(f"Grouped by: {', '.join(req.dimensions)}")
    if req.grain:
        lines.append(f"Time grain: {req.grain}")
    if req.row_count_scanned is not None:
        total = dcd.dataset.source.row_count if dcd else None
        if total and total > 0 and total >= req.row_count_scanned:
            pct = req.row_count_scanned / total * 100
            lines.append(
                f"Rows scanned: {req.row_count_scanned} of {total} "
                f"({pct:.1f}% of the dataset)"
            )
        else:
            lines.append(f"Rows scanned: {req.row_count_scanned}")
    if req.sql:
        lines.append(f"SQL executed:\n{req.sql}")

    if req.current_description:
        lines.append("")
        lines.append(
            f"Prior auto-generated summary (reference only; "
            f"don't repeat verbatim, produce a real audit trail): "
            f"{req.current_description}"
        )

    return "\n".join(lines)


_META_PREFIXES = (
    "okay",
    "ok ",
    "wait",
    "hmm",
    "let",
    "let's",
    "so ",
    "alright",
    "now,",
    "actually,",
    "thinking",
    "the user",
    "i need to",
    "i should",
    "i'll",
    "first,",
    "note:",
)


def _salvage_reasoning(reasoning: str) -> str:
    """Extract the last draft answer from a reasoning trace.

    GLM :exacto reasoning traces interleave meta-commentary ("Let's
    combine sentences 2 and 3") with draft answers (often quoted).
    Strategy, in order:
      1. If the trace contains quoted spans, return the longest one
         from the tail — those are typically the model's final draft.
      2. Otherwise, walk paragraphs from last to first and pick the
         first one that looks like prose (doesn't open with a meta
         prefix, isn't bulleted, contains a period).
    """
    import re

    # Look for paired-quote draft candidates — straight or curly.
    quote_candidates = re.findall(r'"([^"]{40,})"', reasoning)
    quote_candidates += re.findall(r"“([^”]{40,})”", reasoning)
    if quote_candidates:
        return max(quote_candidates, key=len).strip()

    paras = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
    for p in reversed(paras):
        low = p.lower()
        if p.startswith(("*", "#", "-", ">", "•")):
            continue
        if any(low.startswith(pref) for pref in _META_PREFIXES):
            continue
        if "." not in p:
            continue
        return p
    # Last resort — take the final paragraph even if it looks metaish.
    return paras[-1] if paras else ""


def _cache_key(req: ClaimDescribeRequest) -> str:
    blob = "|".join(
        [
            req.dataset_id,
            req.formatted,
            str(req.value),
            req.label or "",
            req.metric_ref or "",
            req.entity or "",
            "||".join(req.filters_applied),
            ",".join(req.dimensions),
            req.grain or "",
            (req.sql or "")[:500],
        ]
    )
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


_DRAFT_LEAK_MARKERS = (
    "**drafting",
    "*drafting",
    "drafting the sentence",
    "*sentence 1",
    "*sentence 2",
    "*sentence 3",
    "*sentence 4",
    "sentence 1:",
    "sentence 2:",
    "sentence 3:",
    "sentence 4:",
    "**refining",
    "*refining",
    "**polishing",
    "*polishing",
    "polishing the prose",
    "*step 1",
    "*step 2",
    "*step 3",
    "*step 4",
    "**step 1",
    "**step 2",
    "**step 3",
    "**step 4",
    "evidence footer.*",
    "the prompt says",
    "draft:",
    "what is measured.*",
    "iterative process",
    "*constraint check",
    "**constraint check",
    "*wait,",
    "*checked*",
    "so i should write",
    "let me re-read",
    "constraint check:",
    "*check:*",
    "hard rules:",
)


def _looks_like_draft_leak(text: str) -> bool:
    """Return True if the model emitted its internal planning/drafting
    trace as content instead of a polished audit sentence. Happens
    with reasoning-heavy models like GLM :exacto — they translate
    any structured prompt into step-by-step drafting that leaks into
    the content channel. We detect it and either extract the clean
    paragraph buried inside or fall back to the regex summary."""
    if not text:
        return False
    low = text.lower()
    hits = sum(1 for m in _DRAFT_LEAK_MARKERS if m in low)
    # Two+ draft markers, OR presence of "draft:" anywhere (most
    # damning — model literally labeled a draft attempt), OR a
    # heavily indented bullet structure ("    *   *") which is
    # typical of drafting/outline mode.
    if hits >= 2:
        return True
    if "draft:" in low:
        return True
    return text.count("    *   *") >= 2


def _extract_polished_paragraph(text: str) -> str:
    """Rescue attempt when the stream contains drafting.

    Scan the response for the longest paragraph that looks like
    flowing audit prose — no bullet markers at the start, at least
    two sentence-enders, no drafting labels, ≥120 chars. When the
    model drafts step-by-step it often buries a clean "Polished
    prose" paragraph inside the trash; we surface that instead of
    showing the mess or falling all the way back to regex.
    """
    if not text:
        return ""
    candidates: list[str] = []
    for raw_para in text.split("\n\n"):
        p = raw_para.strip()
        if not p or len(p) < 120:
            continue
        first = p.lstrip()
        if first.startswith(("*", "-", "#", ">", "•", "1.", "2.", "3.", "4.")):
            continue
        low = p.lower()
        if any(m in low for m in _DRAFT_LEAK_MARKERS):
            continue
        # Must look like prose — at least two sentence enders.
        if p.count(". ") + p.count(".\n") < 2:
            continue
        candidates.append(p)
    if not candidates:
        return ""
    # Prefer the longest candidate; ties go to the later one (final
    # draft after revisions).
    candidates.sort(key=lambda p: (len(p), text.index(p)))
    return candidates[-1]


def _sse(event: dict[str, Any]) -> bytes:
    """Serialize an event to an SSE frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


async def _stream_description(
    body: ClaimDescribeRequest, state: AppState
) -> AsyncIterator[bytes]:
    """Stream the audit description token-by-token via SSE.

    Emits frames of shape:
      { "token": "..." }          while tokens arrive
      { "done": true, "description": "<full masked>", "cache_key": "..." }
      { "error": "<msg>" }        on failure (drawer falls back to regex)
    """
    dcd = state.dcds.get(body.dataset_id)
    metric = _find_metric(dcd, body.metric_ref) if dcd else None
    user_prompt = _build_user_prompt(body, dcd, metric)

    catalog = build_catalog_from_dcds({body.dataset_id: dcd} if dcd else {})
    token = set_alias_catalog(catalog)

    try:
        config = AgentConfig()
        from src.core.config import get_settings

        api_key = (
            config.openrouter_api_key
            or get_settings().openrouter_api_key.get_secret_value()
        )
        if not api_key:
            yield _sse({"error": "No LLM credentials"})
            return

        payload: dict[str, Any] = {
            "model": config.resolved_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1500,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        content_accum = ""
        reasoning_accum = ""

        try:
            async with (
                httpx.AsyncClient(
                    base_url=config.openrouter_base_url,
                    headers=headers,
                    timeout=60.0,
                ) as client,
                client.stream("POST", "/chat/completions", json=payload) as r,
            ):
                if r.status_code >= 400:
                    err_body = (await r.aread()).decode("utf-8", errors="replace")
                    yield _sse({"error": f"upstream {r.status_code}: {err_body[:200]}"})
                    return

                # OpenRouter forwards the OpenAI-style SSE stream:
                # lines of ``data: {json}`` separated by blank lines,
                # terminated by ``data: [DONE]``. Each delta carries
                # ``choices[0].delta.content`` (primary tokens) or
                # ``.reasoning`` (used by GLM :exacto to stream the
                # internal trace before the real answer). We forward
                # only content tokens to the client but retain the
                # reasoning buffer for the empty-content salvage.
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk, dict) and "error" in chunk:
                        yield _sse({"error": str(chunk["error"])[:200]})
                        return
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        # Mask physical names on the fly — catches
                        # anything the model inlined before we can
                        # do a whole-text pass.
                        masked_piece = catalog.mask(piece) if catalog else piece
                        content_accum += piece
                        yield _sse({"token": masked_piece})
                        # Early leak guard: if the model is emitting
                        # its own drafting dialogue instead of the
                        # audit sentence, detect it as soon as we
                        # have enough text to tell (≥120 chars) and
                        # bail out before the mess dominates the
                        # drawer. The client reacts by clearing
                        # what it showed and falling back to the
                        # regex summary.
                        if 120 <= len(content_accum) <= 500 and (
                            _looks_like_draft_leak(content_accum)
                        ):
                            yield _sse({"error": "draft_leak"})
                            return
                    reasoning_piece = delta.get("reasoning")
                    if reasoning_piece:
                        reasoning_accum += reasoning_piece
        except httpx.HTTPError as e:
            yield _sse({"error": f"upstream network error: {e!s}"[:200]})
            return

        description = content_accum.strip()

        # Reasoning-trace salvage: GLM :exacto occasionally exhausts the
        # token budget inside the reasoning field and emits an empty
        # content stream. The reasoning trace typically contains
        # meta-commentary ("Let's combine...", "Okay, now...") followed
        # by one or more DRAFT paragraphs (often quoted). We extract the
        # last draft — preferring quoted content — and salvage that.
        if not description and reasoning_accum.strip():
            salvaged = _salvage_reasoning(reasoning_accum)
            if salvaged:
                masked_salvage = catalog.mask(salvaged) if catalog else salvaged
                description = salvaged
                # Stream it in one frame so the client sees tokens.
                yield _sse({"token": masked_salvage})

        if not description:
            yield _sse({"error": "empty content"})
            return

        # Final leak check — catches drafting that crept in below
        # the 120-char early-detection threshold (the first chars
        # were clean, later ones weren't). When we find one, try
        # to rescue the polished paragraph hiding inside the trash
        # before giving up.
        if _looks_like_draft_leak(description):
            polished = _extract_polished_paragraph(description)
            if polished:
                masked_polished = catalog.mask(polished) if catalog else polished
                # Tell the client to discard the leaked tokens it
                # already rendered, then stream the clean paragraph
                # as the replacement content.
                yield _sse({"reset": True})
                yield _sse({"token": masked_polished})
                yield _sse(
                    {
                        "done": True,
                        "description": masked_polished,
                        "cache_key": _cache_key(body),
                    }
                )
                return
            yield _sse({"error": "draft_leak"})
            return

        masked_full = catalog.mask(description) if catalog else description
        yield _sse(
            {
                "done": True,
                "description": masked_full,
                "cache_key": _cache_key(body),
            }
        )
    finally:
        reset_alias_catalog(token)


@router.post("/describe-claim")
async def describe_claim_stream(
    body: ClaimDescribeRequest, state: StateDep
) -> StreamingResponse:
    """Stream an audit-grade description over SSE.

    Content-Type: text/event-stream. Each frame is ``data: {...}\\n\\n``
    with one of: ``{token: "..."}``, ``{done: true, description, cache_key}``,
    ``{error: "..."}``.
    """
    return StreamingResponse(
        _stream_description(body, state),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so tokens arrive as they're written.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/describe-claim/json", response_model=ClaimDescribeResponse)
async def describe_claim_json(
    body: ClaimDescribeRequest, state: StateDep
) -> ClaimDescribeResponse:
    """Non-streaming fallback for clients that can't consume SSE.

    Collects the stream server-side and returns the final description.
    Kept so tests and tools can hit a plain JSON endpoint.
    """
    description = ""
    cache_key = ""
    error = ""
    async for frame in _stream_description(body, state):
        line = frame.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if "token" in payload:
            # Tokens are already masked; accumulate for the final field.
            description += payload["token"]
        elif payload.get("done"):
            description = payload.get("description", description)
            cache_key = payload.get("cache_key", "")
        elif "error" in payload:
            error = payload["error"]
            break
    if error and not description:
        raise HTTPException(status_code=502, detail=error)
    return ClaimDescribeResponse(
        description=description.strip(),
        cache_key=cache_key or _cache_key(body),
    )
