"""Set up the Coral ↔ brutal-scenario bridge.

  1. Dumps the chosen scenario's duckdb_world to JSON (the MCP server
     reads this at startup).
  2. Generates one Coral source manifest per logical source (stripe,
     intercom, etc.) in `.manthan/coral_sources/`. Each manifest is a
     backend:mcp source whose `tool` per table is the corresponding
     `get_<source>_<table>` exposed by manthan_mock_mcp.py.
  3. Prints the `coral source add` commands you need to run.

Run:
    cd manthanv2/agent
    .venv/bin/python scripts/setup_coral_bridge.py [--scenario S01B-acme-brutal]

This script is idempotent - overwriting JSON and manifest files is fine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# scripts/ isn't a package
sys.path.insert(0, str(Path(__file__).parent))

from brutal_scenarios import SCENARIOS_BRUTAL
from coral_scenarios_data import SCENARIOS_CORAL
from coral_schema_parser import load_real_columns

_AGENT_ROOT = Path(__file__).parent.parent
_DATA_DIR = _AGENT_ROOT / ".manthan"
_JSON_PATH = _DATA_DIR / "scenario_world.json"
_MANIFEST_DIR = _DATA_DIR / "coral_sources"
_MCP_SCRIPT = (_AGENT_ROOT / "scripts" / "manthan_mock_mcp.py").resolve()
# Don't `.resolve()` this - the .venv/bin/python symlink is what activates
# the venv site-packages (where mcp + duckdb live). Following the symlink
# resolves to the bare base python without the venv.
_VENV_PYTHON = _AGENT_ROOT.resolve() / ".venv" / "bin" / "python"


# DuckDB type → Coral DSL type (Utf8, Int64, Float64, Boolean, Json)
def _infer_coral_type(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "Utf8"
    if all(isinstance(v, bool) for v in non_null):
        return "Boolean"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        return "Int64"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "Float64"
    return "Utf8"  # safest default; covers timestamps, strings, mixed


def _column_set(rows: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for row in rows:
        for k in row:
            seen.setdefault(k, None)
    return list(seen.keys())


def _manifest_for_source(
    source: str,
    tables: dict[str, list[dict[str, Any]]],
) -> str:
    """Render one Coral source manifest (YAML) for a logical source.

    Hybrid column strategy:
      1. Pull the REAL Coral column list for this (source, table) from
         coral/sources/<core|community>/<source>/manifest.yaml.
      2. Add our scenario-specific convenience columns (those that
         aren't in real Coral but we want to query directly, e.g.
         customer_email on stripe.disputes).
      3. Result: the manifest declares a real-Coral-sized column surface
         (~50-100 cols per table) while our data populates only a small
         subset. Coral returns rows with the rest as NULL - the same
         sparsity pattern real production data has.
    """
    real_cols_by_table = load_real_columns(source)
    lines: list[str] = [
        "dsl_version: 3",
        f"name: {source}",
        "version: 0.1.0-mock",
        f"description: Mock {source} source backed by the manthan_mock_mcp scenario world.",
        "backend: mcp",
        "server:",
        "  transport: stdio",
        f"  command: {_VENV_PYTHON}",
        "  args:",
        f"    - {_MCP_SCRIPT}",
        f"    - {_JSON_PATH.resolve()}",  # scenario world path
        "tables:",
    ]
    for table, rows in tables.items():
        if not rows:
            continue
        tool_name = f"get_{source.lower()}_{table.lower()}"
        ours = _column_set(rows)
        our_types = {c: _infer_coral_type([r.get(c) for r in rows]) for c in ours}

        # Real columns for THIS table (may be empty if the table isn't
        # part of the real source - e.g. our slack.messages, where the
        # real Coral slack source doesn't expose a messages table).
        real_cols = real_cols_by_table.get(table, [])
        real_col_names = {c["name"] for c in real_cols if c.get("name")}

        # Merged column list. Real columns come first (canonical names);
        # our extras are appended.
        merged: list[tuple[str, str, bool]] = []  # (name, type, is_real)
        for rc in real_cols:
            name = rc.get("name")
            if not name:
                continue
            ctype = rc.get("type") or "Utf8"
            merged.append((name, ctype, True))
        for c in ours:
            if c not in real_col_names:
                merged.append((c, our_types[c], False))

        n_real = sum(1 for _, _, is_real in merged if is_real)
        n_extra = len(merged) - n_real
        descr = (
            f"Mock {source}.{table} rows from the scenario world. "
            f"{n_real} real Coral cols + {n_extra} mock-extra. "
            f"Real-shaped sparse data: most cols NULL per row."
        )
        # Description may contain colons (e.g. "data: most cols NULL") which
        # break unquoted YAML scalars. JSON-escape it to be safe.
        safe_descr = json.dumps(descr)
        lines.append(f"  - name: {table}")
        lines.append(f"    description: {safe_descr}")
        lines.append(f"    tool: {tool_name}")
        lines.append("    response:")
        lines.append("      rows_path: [result]")
        lines.append("    columns:")
        for name, ctype, _is_real in merged:
            lines.append(f"      - name: {name}")
            lines.append(f"        type: {ctype}")
            lines.append("        nullable: true")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        default="S01B-acme-brutal",
        help="Scenario case_id to bridge (default: S01B-acme-brutal).",
    )
    args = parser.parse_args()

    all_scenarios = [*SCENARIOS_BRUTAL, *SCENARIOS_CORAL]
    scenario = next(
        (s for s in all_scenarios if s.case_id == args.scenario), None
    )
    if scenario is None:
        sys.stderr.write(
            f"Unknown scenario: {args.scenario}\n"
            f"Available: {[s.case_id for s in all_scenarios]}\n"
        )
        return 1
    if scenario.duckdb_world is None:
        sys.stderr.write(f"Scenario {scenario.case_id} has no duckdb_world.\n")
        return 1

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    # Wipe stale manifests from prior scenarios - Coral will still have
    # them registered, but the user is expected to `coral source remove`
    # before re-registering. The print at the end lists fresh ones.
    for stale in _MANIFEST_DIR.glob("*.yaml"):
        stale.unlink()

    # 1) Dump world
    _JSON_PATH.write_text(json.dumps(scenario.duckdb_world, default=str))
    total_rows = sum(
        len(rows)
        for tables in scenario.duckdb_world.values()
        for rows in tables.values()
    )
    print(
        f"Wrote scenario world: {_JSON_PATH}  "
        f"({len(scenario.duckdb_world)} sources, {total_rows} rows)"
    )

    # 2) Generate manifests
    manifest_paths: list[Path] = []
    for source, tables in scenario.duckdb_world.items():
        if not any(tables.values()):
            continue
        path = _MANIFEST_DIR / f"{source}.yaml"
        path.write_text(_manifest_for_source(source, tables))
        manifest_paths.append(path)
        n_tables = sum(1 for rows in tables.values() if rows)
        print(f"Wrote manifest: {path}  ({n_tables} tables)")

    # 3) Print coral commands
    print()
    print("Next steps (run by hand or via `make coral-bridge`):")
    print()
    print(f"  CORAL={_AGENT_ROOT.parent.parent / 'coral' / 'target' / 'release' / 'coral'}")
    print()
    print("  # Remove any prior mock sources")
    for p in manifest_paths:
        source_name = p.stem
        print(f"  \"$CORAL\" source remove {source_name} 2>/dev/null || true")
    print()
    print("  # Add fresh ones")
    for p in manifest_paths:
        print(f"  \"$CORAL\" source add --file {p}")
    print()
    print("  # Confirm")
    print('  "$CORAL" source list')
    print('  "$CORAL" sql "SELECT * FROM stripe.disputes LIMIT 3"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
