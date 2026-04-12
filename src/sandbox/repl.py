"""Stateful Python REPL worker for agent-driven analysis.

Runs as a long-lived subprocess spawned by
:class:`src.tools.python_session.PythonSession`. Each worker holds one
persistent ``globals`` dict so variables survive across ``run_python``
calls — the agent can load a DataFrame once and iterate on it across
many turns without re-parsing Parquet every time.

## Protocol

Line-delimited JSON over stdin/stdout. One request per line, one
response per line, always flushed. Single reader on the parent side.

First line after startup: the **bootstrap** request.
Every subsequent line: an **exec** request.

### Bootstrap request (first line only)

```json
{"data_dir": "/abs/path/to/data", "output_dir": "/abs/path/to/output"}
```

Worker loads every ``*.parquet`` file under ``data_dir`` into DuckDB,
exposes the first one as ``df`` (pandas DataFrame) and ``con`` (DuckDB
connection), then replies:

```json
{"ready": true, "bootstrapped_files": ["gold_sales_xxx.parquet", ...]}
```

### Exec request

```json
{"code": "print(df.shape)"}
```

Response:

```json
{
  "stdout": "(500, 12)\n",
  "stderr": "",
  "exit_code": 0,
  "repr": null
}
```

``repr`` is the ``repr()`` of the last expression's value when the code
ends in a bare expression (like a REPL), ``null`` otherwise. Errors
become ``stderr`` traceback + ``exit_code`` 1; the worker stays alive
so the agent can recover and keep going.
"""

from __future__ import annotations

import ast
import io
import json
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

_SESSION_GLOBALS: dict[str, Any] = {}


def _bootstrap(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Populate ``_SESSION_GLOBALS`` with the dataset prelude.

    Every ``gold_*.parquet`` file under ``data_dir`` is attached as a
    DuckDB view whose name is the parquet stem (e.g.
    ``gold_teams_40db28``). The *first* parquet file (alphabetically)
    is additionally aliased as ``dataset`` for backward compatibility —
    agents can always ``SELECT * FROM dataset`` to reach the primary
    Gold table. ``df`` is a pandas DataFrame loaded from ``dataset``.

    For multi-file uploads this means all Gold tables are queryable
    without manual ``read_parquet()`` calls:

    .. code-block:: python

        # primary table
        con.execute("SELECT * FROM dataset LIMIT 5")

        # additional table from a multi-file upload
        con.execute("SELECT * FROM gold_teams_40db28 LIMIT 5")

        # discover available views
        con.execute("SHOW TABLES").df()
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    parquet_files = sorted(data_dir.glob("*.parquet"))
    df = pd.DataFrame()
    attached_views: list[str] = []

    for pf in parquet_files:
        view_name = pf.stem
        escaped = str(pf).replace("'", "''")
        try:
            con.execute(
                f'CREATE VIEW "{view_name}" '
                f"AS SELECT * FROM read_parquet('{escaped}')"
            )
            attached_views.append(view_name)
        except Exception:
            # Skip files with names that DuckDB can't accept as
            # identifiers (shouldn't happen with Gold parquets, but
            # defensive).
            pass

    if parquet_files:
        # Alias the first parquet as the canonical ``dataset`` view.
        primary = parquet_files[0]
        escaped = str(primary).replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW dataset AS SELECT * FROM read_parquet('{escaped}')"
        )
        df = con.execute("SELECT * FROM dataset").df()

    _SESSION_GLOBALS.clear()
    _SESSION_GLOBALS.update(
        {
            "__name__": "__manthan_session__",
            "__builtins__": __builtins__,
            "DATA_DIR": data_dir,
            "OUTPUT_DIR": output_dir,
            "con": con,
            "df": df,
            "pd": pd,
            "duckdb": duckdb,
            "Path": Path,
        }
    )
    return {
        "ready": True,
        "bootstrapped_files": [p.name for p in parquet_files],
        "attached_views": attached_views,
    }


def _execute(code: str) -> dict[str, Any]:
    """Run ``code`` in the persistent globals and capture stdout/stderr.

    If the code ends in a bare expression the repr of its value is
    captured into the ``repr`` field so REPL-style one-liners
    (``df.head()``) round-trip cleanly back to the agent.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    last_repr: str | None = None
    exit_code = 0

    try:
        module = ast.parse(code, mode="exec")
        last_expr: ast.Expression | None = None
        if module.body and isinstance(module.body[-1], ast.Expr):
            expr_node = module.body.pop()
            last_expr = ast.Expression(body=expr_node.value)  # type: ignore[attr-defined]

        body_source = ast.unparse(module) if module.body else ""

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            if body_source:
                exec(
                    compile(body_source, "<manthan-session>", "exec"),
                    _SESSION_GLOBALS,
                )
            if last_expr is not None:
                value = eval(
                    compile(last_expr, "<manthan-session>", "eval"),
                    _SESSION_GLOBALS,
                )
                if value is not None:
                    last_repr = repr(value)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    except BaseException:
        exit_code = 1
        traceback.print_exc(file=stderr_buf)

    return {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "exit_code": exit_code,
        "repr": last_repr,
    }


def _write_response(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _handle_request(line: str) -> None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        _write_response(
            {
                "stdout": "",
                "stderr": f"session worker: invalid JSON request ({exc})",
                "exit_code": 2,
                "repr": None,
            }
        )
        return

    code = request.get("code", "")
    if not isinstance(code, str):
        _write_response(
            {
                "stdout": "",
                "stderr": "session worker: 'code' must be a string",
                "exit_code": 2,
                "repr": None,
            }
        )
        return

    result = _execute(code)
    _write_response(result)


def main() -> None:
    bootstrap_line = sys.stdin.readline()
    if not bootstrap_line:
        return
    try:
        bootstrap = json.loads(bootstrap_line)
    except json.JSONDecodeError as exc:
        _write_response({"ready": False, "error": f"invalid bootstrap JSON: {exc}"})
        return

    try:
        ack = _bootstrap(
            data_dir=Path(bootstrap["data_dir"]),
            output_dir=Path(bootstrap["output_dir"]),
        )
    except Exception as exc:
        _write_response({"ready": False, "error": f"bootstrap failed: {exc}"})
        return

    _write_response(ack)

    for line in sys.stdin:
        if not line.strip():
            continue
        _handle_request(line)


if __name__ == "__main__":
    main()
