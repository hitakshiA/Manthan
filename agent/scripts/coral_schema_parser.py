"""Read real Coral source manifests to extract column declarations.

Coral's real source manifests (`/coral/sources/core/<source>/manifest.yaml`
and `/coral/sources/community/<source>/manifest.yaml`) declare every
column the source exposes - for Stripe that's 78 cols per disputes, 376
per charges, etc.

This module locates the manifest for a given source, parses it, and
returns the column lists per table. Used by setup_coral_bridge.py to
render mock manifests that match real Coral's schema surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CORAL_ROOT = Path("/Users/akshmnd/Dev Projects/coral/sources")
_SOURCE_DIRS = (_CORAL_ROOT / "core", _CORAL_ROOT / "community")


def find_manifest(source: str) -> Path | None:
    for parent in _SOURCE_DIRS:
        cand = parent / source / "manifest.yaml"
        if cand.exists():
            return cand
    return None


def load_real_columns(source: str) -> dict[str, list[dict[str, Any]]]:
    """Return {table_name: [column_dict, ...]} for a real Coral source.

    Each column_dict has at least {"name": str, "type": str, "nullable": bool}
    plus whatever else the manifest declared. Returns {} if the source
    manifest isn't found.
    """
    path = find_manifest(source)
    if path is None:
        return {}
    with path.open() as f:
        data = yaml.safe_load(f)
    out: dict[str, list[dict[str, Any]]] = {}
    for t in data.get("tables") or []:
        name = t.get("name")
        cols_raw = t.get("columns") or []
        cols: list[dict[str, Any]] = []
        for c in cols_raw:
            if not isinstance(c, dict):
                continue
            cols.append(
                {
                    "name": c.get("name"),
                    "type": c.get("type", "Utf8"),
                    "nullable": c.get("nullable", True),
                    "description": c.get("description"),
                }
            )
        if name and cols:
            out[name] = cols
    return out


def column_names(source: str, table: str) -> set[str]:
    """Convenience: just the column-name set for one table."""
    cols = load_real_columns(source).get(table, [])
    return {c["name"] for c in cols if c.get("name")}


if __name__ == "__main__":
    # Smoke: print column counts for our sources
    for src in ("stripe", "intercom", "salesforce", "zendesk", "slack",
                "notion", "posthog", "gmail", "sentry"):
        cols_by_table = load_real_columns(src)
        if not cols_by_table:
            print(f"{src:14s}  (manifest not found)")
            continue
        total = sum(len(v) for v in cols_by_table.values())
        print(
            f"{src:14s}  {len(cols_by_table):>4d} tables  {total:>6d} cols total  "
            f"(largest: {max((len(v) for v in cols_by_table.values()), default=0)})"
        )
