"""Sandbox prelude.

Auto-loaded before user code runs. Opens every Parquet file under
``/data/`` into a DuckDB in-memory database and exposes three variables:

- ``con``: a ``duckdb.DuckDBPyConnection``
- ``df``: the primary dataset materialized as a pandas DataFrame
- ``OUTPUT_DIR``: a pathlib.Path pointing at ``/output``

The prelude is intentionally tiny so debugging failures in user code is
straightforward.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path("/data")
OUTPUT_DIR = Path("/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

con: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")

_parquet_files = sorted(DATA_DIR.glob("*.parquet"))
if _parquet_files:
    # CREATE VIEW does not accept parameter binding in DuckDB; the path
    # is sandbox-internal and resolved from a controlled glob so direct
    # interpolation is safe here.
    _escaped = str(_parquet_files[0]).replace("'", "''")
    con.execute(f"CREATE VIEW dataset AS SELECT * FROM read_parquet('{_escaped}')")
    df: pd.DataFrame = con.execute("SELECT * FROM dataset").df()
else:
    df = pd.DataFrame()

__all__ = ["DATA_DIR", "OUTPUT_DIR", "con", "df"]
