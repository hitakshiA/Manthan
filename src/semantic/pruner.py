"""Query-relevant DCD pruning.

When an analysis agent issues a query, feeding the entire DCD into its
prompt wastes tokens on columns that have nothing to do with the
question. :func:`prune_for_query` returns a copy of the DCD trimmed down
to the columns and metrics that matter for a specific query, while
always keeping the pivot columns (temporal + primary dimensions) so the
agent still has enough context to write a runnable SQL statement.

The scoring is deliberately simple: tokenize the query, score each
column by literal substring/token matches against its name and
description, and keep the top N.
"""

from __future__ import annotations

import re

from src.semantic.schema import DataContextDocument, DcdColumn, DcdDataset

_MAX_COLUMNS_DEFAULT = 30
_MIN_COLUMNS_DEFAULT = 4

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def prune_for_query(
    dcd: DataContextDocument,
    query: str,
    *,
    max_columns: int = _MAX_COLUMNS_DEFAULT,
) -> DataContextDocument:
    """Return a pruned :class:`DataContextDocument` scoped to ``query``.

    Args:
        dcd: The full DCD to prune.
        query: The user's natural-language question.
        max_columns: Upper bound on columns retained in the pruned DCD.
            Datasets below this threshold are returned unchanged.

    Returns:
        A new :class:`DataContextDocument` instance whose ``columns``
        list is a (stable-order) subset of the original. Temporal and
        metric columns are always retained. Computed metrics whose
        dependencies are all still present are retained; others are
        dropped so the pruned DCD remains consistent.
    """
    all_columns = dcd.dataset.columns
    if len(all_columns) <= max_columns:
        return dcd

    tokens = _tokenize(query)

    scored: list[tuple[int, int, DcdColumn]] = []
    for index, column in enumerate(all_columns):
        score = _score_column(column, tokens)
        scored.append((score, index, column))

    # Force-keep columns that are essential for context regardless of score.
    forced_names: set[str] = set()
    if dcd.dataset.temporal.column:
        forced_names.add(dcd.dataset.temporal.column)
    for column in all_columns:
        if column.role == "metric":
            forced_names.add(column.name)

    forced = [c for c in all_columns if c.name in forced_names]
    forced_names = {c.name for c in forced}

    # Sort by descending score, preserving original order for ties.
    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked: list[DcdColumn] = []
    for _score, _index, column in scored:
        if column.name in forced_names:
            continue
        ranked.append(column)

    remaining_budget = max(max_columns - len(forced), _MIN_COLUMNS_DEFAULT)
    selected_extra = ranked[:remaining_budget]

    keep: list[DcdColumn] = []
    keep_names: set[str] = set()
    for column in all_columns:
        if column.name in forced_names or column in selected_extra:
            keep.append(column)
            keep_names.add(column.name)

    pruned_metrics = [
        m
        for m in dcd.dataset.computed_metrics
        if all(dep in keep_names for dep in m.depends_on)
    ]

    new_dataset = DcdDataset(
        id=dcd.dataset.id,
        name=dcd.dataset.name,
        description=dcd.dataset.description,
        source=dcd.dataset.source,
        temporal=dcd.dataset.temporal,
        columns=keep,
        computed_metrics=pruned_metrics,
        relationships=dcd.dataset.relationships,
        quality=dcd.dataset.quality,
        verified_queries=dcd.dataset.verified_queries,
        agent_instructions=dcd.dataset.agent_instructions,
    )

    return DataContextDocument(version=dcd.version, dataset=new_dataset)


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}


def _score_column(column: DcdColumn, tokens: set[str]) -> int:
    name_tokens = _tokenize(column.name)
    description_tokens = _tokenize(column.description)

    score = 0
    for token in tokens:
        if token in name_tokens:
            score += 3
        if token in description_tokens:
            score += 1
    return score
