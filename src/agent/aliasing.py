"""Physical-name → business-name rewriting for agent-facing previews.

The semantic layer wraps DuckDB's ``gold_<stem>_<uuid>[_<suffix>]``
tables behind stable entity slugs. That wrapping is load-bearing for
exec trust: the user should never see ``gold_orders_16b49dbd39_by_status``
in a narrative or tool preview.

This module centralizes the masking logic so ingredient events
(``tool_start``, ``tool_complete``, ``sql_result``) and any prompt
post-processing can reach for one function. It's intentionally pure
— build an :class:`AliasCatalog` once from the active entities, then
call :meth:`AliasCatalog.mask` on any text. No DuckDB, no network.

The masker prefers the rollup slug when the physical name has a
matching suffix (``..._by_status`` → ``orders.by_status``), and falls
back to the entity slug alone (``gold_orders_16b49dbd39`` →
``orders``). Unknown physical names are left untouched — we never
rewrite text we don't recognize.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.semantic.schema import DataContextDocument


@dataclass(slots=True)
class AliasCatalog:
    """Physical-name → entity-scoped display-name registry.

    Built from the DCDs of the active workspace. Physical names are
    stored verbatim and the masker compiles a single regex union for
    fast replacement across long tool-call previews.
    """

    physical_to_display: dict[str, str] = field(default_factory=dict)
    _pattern: re.Pattern[str] | None = field(default=None, init=False, repr=False)

    def register_entity(self, dcd: DataContextDocument) -> None:
        """Add an entity's physical tables to the catalog."""
        entity = dcd.dataset.entity
        if entity is None:
            return
        # Primary table → the entity slug.
        self.physical_to_display[entity.physical_table] = entity.slug
        # Each rollup → ``slug.<rollup_slug>``.
        for rollup in entity.rollups:
            self.physical_to_display[rollup.physical_table] = (
                f"{entity.slug}.{rollup.slug}"
            )
        # Invalidate the compiled pattern.
        self._pattern = None

    def mask(self, text: str) -> str:
        """Replace any physical table names in ``text`` with their display form.

        Bare-identifier matches only — we do NOT rewrite inside string
        literals (DuckDB's ``read_parquet('gold_orders_...')`` calls),
        because those paths are real filesystem references the agent
        sometimes needs to preserve verbatim.
        """
        if not text or not self.physical_to_display:
            return text
        pattern = self._compile()
        if pattern is None:
            return text
        return pattern.sub(lambda m: self.physical_to_display.get(m.group(0), m.group(0)), text)

    def _compile(self) -> re.Pattern[str] | None:
        if self._pattern is not None:
            return self._pattern
        if not self.physical_to_display:
            return None
        # Longest-first so ``gold_orders_<uuid>_by_status`` wins over
        # ``gold_orders_<uuid>`` when both would match at the same spot.
        names = sorted(self.physical_to_display.keys(), key=len, reverse=True)
        escaped = [re.escape(n) for n in names]
        # Require word boundaries so we don't rewrite suffixes of other
        # identifiers by accident. The character class allows underscores
        # and alphanumerics only — matching DuckDB's identifier rules.
        self._pattern = re.compile(r"\b(?:" + "|".join(escaped) + r")\b")
        return self._pattern


def build_catalog_from_dcds(dcds: dict[str, DataContextDocument]) -> AliasCatalog:
    """Build an :class:`AliasCatalog` from a dataset-id → DCD map.

    Callers: the agent loop does this once at ``session_start`` (cheap
    — a few dozen regex atoms), passes the catalog into event factories
    that render tool previews.
    """
    catalog = AliasCatalog()
    for dcd in dcds.values():
        catalog.register_entity(dcd)
    return catalog
