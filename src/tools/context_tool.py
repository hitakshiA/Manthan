"""Data Context Document retrieval tool.

:func:`get_context` returns a YAML rendering of the DCD for a dataset,
optionally pruned to the columns relevant to a specific natural-language
query via :func:`src.semantic.pruner.prune_for_query`.
"""

from __future__ import annotations

from src.semantic.pruner import prune_for_query
from src.semantic.schema import DataContextDocument


def get_context(
    dcd: DataContextDocument,
    *,
    query: str | None = None,
    max_columns: int = 30,
) -> str:
    """Return the DCD as YAML, optionally pruned to ``query``.

    Args:
        dcd: The full Data Context Document.
        query: Optional natural-language question. When provided, the
            DCD is pruned to the most relevant columns for that query.
        max_columns: Upper bound on columns retained when pruning.

    Returns:
        A YAML string ready to hand to an analysis agent.
    """
    target = dcd
    if query is not None and query.strip():
        target = prune_for_query(dcd, query, max_columns=max_columns)
    return target.to_yaml()
