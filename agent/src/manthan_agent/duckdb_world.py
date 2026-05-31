"""Build an in-memory DuckDB populated from a scenario world dict.

The scenario world is the brutal-data structure:

    world: dict[source_name, dict[table_name, list[row_dict]]]

For each source we CREATE SCHEMA, for each table CREATE TABLE with types
inferred from the rows, and INSERT every row. The agent then runs its
SQL against the resulting connection - same dialect as real Coral,
real cross-source JOINs, real volume.

Why DuckDB and not SQLite: schema namespacing (`stripe.disputes` rather
than `stripe_disputes`), native TIMESTAMP/INTERVAL arithmetic, fast
in-memory, identical SQL to what Coral's data plane will run.
"""

from __future__ import annotations

import re
from typing import Any

import duckdb

# Sample column values to figure out the right DuckDB type. We bias
# strongly toward VARCHAR (safest for mixed data) and only upgrade to
# TIMESTAMP/BOOLEAN/BIGINT/DOUBLE when we're confident.
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _infer_column_type(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "VARCHAR"

    # All bools?
    if all(isinstance(v, bool) for v in non_null):
        return "BOOLEAN"
    # All ints (and not bools)?
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        return "BIGINT"
    # All numeric (mix of int/float)?
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "DOUBLE"
    # All strings?
    if all(isinstance(v, str) for v in non_null):
        if all(_ISO_TS.match(v) for v in non_null):
            return "TIMESTAMP"
        if all(_ISO_DATE.match(v) for v in non_null):
            return "DATE"
        return "VARCHAR"
    return "VARCHAR"


def _column_set(rows: list[dict[str, Any]]) -> list[str]:
    """Stable column order, taking the union across rows.

    First row's keys come first; new keys discovered later are appended
    in insertion order.
    """
    seen: dict[str, None] = {}
    for row in rows:
        for k in row:
            seen.setdefault(k, None)
    return list(seen.keys())


def build_world(world: dict[str, dict[str, list[dict[str, Any]]]]) -> duckdb.DuckDBPyConnection:
    """Spin up a fresh in-memory DuckDB and populate it from the scenario.

    Empty tables (zero rows) are still created with VARCHAR columns
    inferred from a sentinel. Tables with at least one row get types
    inferred per column.
    """
    con = duckdb.connect(":memory:")

    for source_name, tables in world.items():
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {source_name}")
        for table_name, rows in tables.items():
            cols = _column_set(rows) if rows else []
            if not cols:
                # Empty table - skip creation; the agent's JOIN against
                # a missing table will surface as a SQL error, which is
                # itself useful evidence of absence.
                continue

            col_types = {
                c: _infer_column_type([row.get(c) for row in rows]) for c in cols
            }
            col_defs = ", ".join(f'"{c}" {col_types[c]}' for c in cols)
            con.execute(f"CREATE TABLE {source_name}.{table_name} ({col_defs})")

            placeholders = ", ".join("?" for _ in cols)
            stmt = (
                f"INSERT INTO {source_name}.{table_name} "
                f"({', '.join(f'\"{c}\"' for c in cols)}) "
                f"VALUES ({placeholders})"
            )
            for row in rows:
                con.execute(stmt, [row.get(c) for c in cols])

    return con


def list_catalog(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Return [{name, tables}, ...] for every populated schema."""
    schemas = con.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'main', 'pg_catalog')
        ORDER BY schema_name
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for (schema_name,) in schemas:
        tables = con.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = ? ORDER BY table_name
            """,
            [schema_name],
        ).fetchall()
        out.append({"name": schema_name, "tables": [t for (t,) in tables]})
    return out


def describe_table(
    con: duckdb.DuckDBPyConnection,
    qualified_name: str,
) -> list[dict[str, str]]:
    """Return [{name, type}, ...] for a `<schema>.<table>` qualified name."""
    if "." not in qualified_name:
        return []
    schema, table = qualified_name.split(".", 1)
    cols = con.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema, table],
    ).fetchall()
    return [{"name": n, "type": t} for (n, t) in cols]


def execute_query(
    con: duckdb.DuckDBPyConnection,
    query: str,
    row_cap: int = 50,
) -> tuple[list[str], list[dict[str, Any]], int, str | None]:
    """Run an agent-issued SQL query.

    Returns (columns, rows, total_matches, error). On SQL error,
    rows is empty and error contains DuckDB's message. The agent can
    self-correct off the error.

    row_cap limits how many rows we serialize back into the agent's
    context so a `SELECT *` from a 5,000-row table doesn't melt the
    LLM. total_matches reports the true cardinality for honesty.
    """
    try:
        cur = con.execute(query)
    except Exception as e:
        return [], [], 0, str(e)

    all_rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    serialized = [dict(zip(cols, r, strict=False)) for r in all_rows[:row_cap]]
    return cols, serialized, len(all_rows), None
