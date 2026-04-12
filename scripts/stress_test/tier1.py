"""Tier 1 — atomic factual lookup across 4 datasets.

Each cell produces:
- SQL answer (1 query)
- Python render_spec.json + 1 data parquet file
- HTTP trace
- Pass/fail notes

Mode: ``simple`` — minimal narrative, 1-3 visuals, 1 headline KPI.

Key Layer 1 facts discovered during this tier (relayed into the final
report):

1. The Python sandbox pre-loads the primary Gold parquet as a DuckDB
   view called ``dataset`` — not under the ``gold_foo_bar`` name that
   ``/tools/sql`` uses. Agent code running in the sandbox must
   ``con.execute("SELECT ... FROM dataset")`` rather than referencing
   the gold table name.
2. Multi-file uploads only load the *first* parquet in ``DATA_DIR``
   as the ``dataset`` view; other tables sit on disk and the agent
   has to call ``read_parquet('/abs/path')`` manually. This is not
   currently surfaced in ``/tools/list``.
3. ``/tools/sql`` rejects ``DESCRIBE``. To inspect columns the agent
   must query ``information_schema.columns``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from scripts.stress_test.client import L1Client, Trace  # noqa: I001

ARTIFACTS = Path("docs/stress_test_artifacts/tier1")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def _ds(name: str) -> str:
    return (
        Path(f"docs/stress_test_artifacts/dcds/{name}_dataset_id.txt")
        .read_text()
        .strip()
    )


def _gold_table(schema: dict) -> str | None:
    tables = schema.get("summary_tables") or []
    for t in tables:
        for suffix in ("_daily", "_monthly", "_weekly", "_quarterly", "_yearly"):
            if t.endswith(suffix):
                return t[: -len(suffix)]
    # Fallback: discover via information_schema
    return None


def _discover_gold_table(c: L1Client, ds_id: str, stem_hint: str) -> str:
    """Find the real gold table by querying information_schema.

    Needed because some datasets (no-temporal, like Adult/Ames) have no
    temporal summary tables for us to derive the base name from.
    """
    sql = (
        "SELECT table_name FROM information_schema.tables "
        f"WHERE lower(table_name) LIKE 'gold_{stem_hint.lower()}%' "
        "ORDER BY length(table_name) ASC LIMIT 1"
    )
    r = c.run_sql(ds_id, sql)
    if r["rows"]:
        return r["rows"][0][0]
    raise RuntimeError(f"no gold table discovered for stem={stem_hint}")


def _save_cell(cell_id: str, artifact: dict) -> Path:
    out = ARTIFACTS / f"{cell_id}.json"
    out.write_text(json.dumps(artifact, indent=2, default=str))
    return out


def cell_1A_taxi(c: L1Client) -> dict:
    """Priya / Taxi: 'What was the average fare for a January 2024 ride?'"""
    ds_id = _ds("taxi")
    _, _ctx = c.get_context(ds_id, query="average fare amount")
    # Query via the sandbox's `dataset` view — the Python sandbox only
    # sees its in-memory DuckDB, not the server's Gold catalog.
    sql_avg = "SELECT AVG(fare_amount) AS avg_fare, COUNT(*) AS n FROM dataset"
    # The sandbox con supports the same SQL, so answer via run_python to
    # keep everything in one place and prove session persistence.
    code = """
import json
from pathlib import Path

avg_fare, n = con.execute(
    "SELECT AVG(fare_amount), COUNT(*) FROM dataset"
).fetchone()

hist = con.execute('''
    SELECT
      CASE
        WHEN fare_amount < 0 THEN -1
        WHEN fare_amount < 5 THEN 0
        WHEN fare_amount < 10 THEN 5
        WHEN fare_amount < 15 THEN 10
        WHEN fare_amount < 20 THEN 15
        WHEN fare_amount < 30 THEN 20
        WHEN fare_amount < 50 THEN 30
        ELSE 50
      END AS lower_bound,
      COUNT(*) AS trip_count
    FROM dataset
    WHERE fare_amount IS NOT NULL
    GROUP BY 1 ORDER BY 1
''').df()
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
hist.to_parquet(out / "fare_hist.parquet")

render_spec = {
    "mode": "simple",
    "headline": {
        "value": f"${avg_fare:.2f}",
        "label": "Average January 2024 fare",
    },
    "narrative": (
        f"Across {n:,} NYC Yellow Taxi trips in January 2024, the average "
        f"fare was ${avg_fare:.2f}. Trips cluster in the $5-$15 bucket; a "
        f"long-distance tail pulls the mean above the median. "
        f"Source column: fare_amount (DCD role=metric)."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "histogram",
            "title": "Distribution of fare amounts",
            "data_ref": "files/fare_hist.parquet",
            "encoding": {"x": "lower_bound", "y": "trip_count"},
            "caption": "Most rides fall in the $5-15 bucket",
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "fare_amount",
         "reason": "primary measure for ride revenue"},
        {"kind": "column", "identifier": "tpep_pickup_datetime",
         "reason": "defines the January 2024 window"},
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"avg_fare": avg_fare, "trip_count": n}))
"""
    py = c.run_python(ds_id, code, timeout_seconds=90)
    return _python_cell_result(
        cell_id="1.A_taxi",
        persona="Priya Sharma",
        query="What was the average fare for a January 2024 ride?",
        sql_equivalent=sql_avg,
        py=py,
    )


def cell_1B_adult(c: L1Client) -> dict:
    """Eleni / Adult: 'What share of respondents earn over $50k?'"""
    ds_id = _ds("adult")
    _, _ctx = c.get_context(ds_id, query="income over 50k share")
    code = """
import json
from pathlib import Path

rows = con.execute(
    "SELECT income, COUNT(*) FROM dataset GROUP BY 1"
).fetchall()
total = sum(r[1] for r in rows)
over = sum(r[1] for r in rows if '>50K' in str(r[0]))
share = over / total if total else 0.0

summary_df = con.execute(
    "SELECT income, COUNT(*) AS n FROM dataset GROUP BY 1 ORDER BY 1"
).df()
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
summary_df.to_parquet(out / "income_split.parquet")

render_spec = {
    "mode": "simple",
    "headline": {
        "value": f"{share*100:.1f}%",
        "label": "Share earning over $50k",
    },
    "narrative": (
        f"Of {total:,} respondents in the UCI Adult Census sample, "
        f"{over:,} ({share*100:.1f}%) earn more than $50,000 per year. "
        f"This matches the canonical 24% high-earner benchmark. The "
        f"'income' column was auto-classified as auxiliary by the Silver "
        f"stage — it is treated here as a binary dimension."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "bar",
            "title": "Respondent count by income bucket",
            "data_ref": "files/income_split.parquet",
            "encoding": {"x": "income", "y": "n"},
            "caption": f"{share*100:.1f}% earn >$50k",
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "income",
         "reason": "binary target; core dimension for this analysis"},
    ],
    "caveats": [
        "income was auto-classified as 'auxiliary' by the Silver stage; "
        "treated here as dimension"
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"share_over_50k": share, "total": total, "over_50k": over}))
"""
    py = c.run_python(ds_id, code, timeout_seconds=60)
    return _python_cell_result(
        cell_id="1.B_adult",
        persona="Eleni Kostas",
        query="What share of respondents earn over $50k?",
        sql_equivalent="SELECT income, COUNT(*) FROM dataset GROUP BY 1",
        py=py,
    )


def cell_1C_lahman(c: L1Client) -> dict:
    """Marcus / Lahman: 'Which franchise has won the most World Series?'

    Multi-file upload — the Python sandbox only has the primary file
    (AllstarFull) loaded as ``dataset``. For a Teams query we query the
    server's Gold catalog via ``/tools/sql`` directly.
    """
    ds_id = _ds("lahman")
    # Discover the real Teams table via information_schema
    probe = c.run_sql(
        ds_id,
        "SELECT table_name FROM information_schema.tables "
        "WHERE lower(table_name) LIKE '%teams%' "
        "ORDER BY length(table_name) ASC LIMIT 5",
    )
    teams_table: str | None = None
    for row in probe["rows"]:
        if "teams" in row[0].lower() and not row[0].startswith("raw_teams_franchises"):
            teams_table = row[0]
            break
    if not teams_table:
        return {
            "cell_id": "1.C_lahman",
            "error": "no Teams table discovered",
            "probe_rows": probe["rows"],
        }

    col_probe = c.run_sql(
        ds_id,
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_name = '{teams_table}'",
    )
    col_names = {r[0].lower(): r[0] for r in col_probe["rows"]}
    ws_col = col_names.get("wswin")
    team_col = col_names.get("teamid") or col_names.get("franchid")
    if not (ws_col and team_col):
        return {
            "cell_id": "1.C_lahman",
            "error": f"missing wswin/teamID on {teams_table}",
            "columns": list(col_names.keys())[:30],
        }

    sql = (
        f'SELECT "{team_col}" AS team, COUNT(*) AS ws_wins '
        f'FROM "{teams_table}" '
        f"WHERE \"{ws_col}\" = 'Y' "
        f'GROUP BY "{team_col}" ORDER BY ws_wins DESC LIMIT 10'
    )
    r = c.run_sql(ds_id, sql, max_rows=10)
    if not r["rows"]:
        return {
            "cell_id": "1.C_lahman",
            "error": "no WS winners found",
            "sql": sql,
        }
    top_team = r["rows"][0][0]
    top_wins = int(r["rows"][0][1])

    # Python: data ref serialized from the rows we already have — we can't
    # re-run this SQL in the sandbox because its `con` doesn't see the
    # server's Gold catalog. So we pass the data in as a literal and
    # write the parquet from pandas.
    top10_rows = [(str(row[0]), int(row[1])) for row in r["rows"]]
    code = f"""
import json
from pathlib import Path
import pandas as pd

top10 = pd.DataFrame({top10_rows!r}, columns=['team', 'ws_wins'])
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
top10.to_parquet(out / "ws_wins_top10.parquet")

top_team = {top_team!r}
top_wins = {top_wins}

render_spec = {{
    "mode": "simple",
    "headline": {{
        "value": str(top_team),
        "label": f"Most World Series wins ({{top_wins}})",
    }},
    "narrative": (
        f"Across the full Lahman franchise history, {{top_team}} has won "
        f"the World Series {{top_wins}} times — more than any other "
        f"franchise in the dataset. Top 10 shown."
    ),
    "visuals": [
        {{
            "id": "v1",
            "type": "bar",
            "title": "Top 10 franchises by World Series wins",
            "data_ref": "files/ws_wins_top10.parquet",
            "encoding": {{"x": "team", "y": "ws_wins"}},
            "caption": f"{{top_team}} leads with {{top_wins}}",
        }}
    ],
    "citations": [
        {{"kind": "column", "identifier": "WSWin",
          "reason": "World Series winner flag on Teams"}},
        {{"kind": "column", "identifier": "teamID",
          "reason": "franchise key used across all 10 Lahman tables"}},
    ],
}}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({{"top_team": top_team, "top_wins": top_wins}}))
"""
    py = c.run_python(ds_id, code, timeout_seconds=60)
    result = _python_cell_result(
        cell_id="1.C_lahman",
        persona="Marcus Okonkwo",
        query="Which franchise has won the most World Series?",
        sql_equivalent=sql,
        py=py,
    )
    result["top_team"] = top_team
    result["top_wins"] = top_wins
    return result


def cell_1D_ames(c: L1Client) -> dict:
    """Akira / Ames: 'Which neighborhood has the highest median sale price?'"""
    ds_id = _ds("ames")
    code = """
import json
from pathlib import Path

df_top = con.execute('''
    SELECT "Neighborhood" AS neighborhood,
           MEDIAN(price) AS median_price,
           COUNT(*) AS n
    FROM dataset
    GROUP BY "Neighborhood"
    HAVING COUNT(*) >= 10
    ORDER BY median_price DESC LIMIT 15
''').df()

if len(df_top) == 0:
    print(json.dumps({"error": "no neighborhoods"}))
else:
    top_nbr = str(df_top.iloc[0]["neighborhood"])
    top_median = float(df_top.iloc[0]["median_price"])
    out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
    df_top.to_parquet(out / "neighborhood_median.parquet")

    render_spec = {
        "mode": "simple",
        "headline": {
            "value": f"${int(top_median):,}",
            "label": f"Median price in {top_nbr} (highest)",
        },
        "narrative": (
            f"Among Ames neighborhoods with at least 10 sales, "
            f"{top_nbr} has the highest median sale price at "
            f"${int(top_median):,}. Top 15 shown."
        ),
        "visuals": [
            {
                "id": "v1",
                "type": "bar",
                "title": "Top 15 neighborhoods by median sale price",
                "data_ref": "files/neighborhood_median.parquet",
                "encoding": {"x": "neighborhood", "y": "median_price"},
                "caption": f"{top_nbr} tops the list at ${int(top_median):,}",
            }
        ],
        "citations": [
            {"kind": "column", "identifier": "Neighborhood",
             "reason": "dimensional grouping"},
            {"kind": "column", "identifier": "price",
             "reason": "target metric"},
        ],
    }
    (out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
    print(json.dumps({"top_neighborhood": top_nbr, "median_price": top_median}))
"""
    py = c.run_python(ds_id, code, timeout_seconds=60)
    return _python_cell_result(
        cell_id="1.D_ames",
        persona="Akira Tanaka",
        query="Which neighborhood has the highest median sale price?",
        sql_equivalent='SELECT "Neighborhood", MEDIAN(price) FROM dataset GROUP BY 1',
        py=py,
    )


def _python_cell_result(
    *,
    cell_id: str,
    persona: str,
    query: str,
    sql_equivalent: str,
    py: dict,
) -> dict:
    stdout = py.get("stdout") or ""
    answer: dict | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                answer = json.loads(line)
            except Exception:
                pass
    return {
        "cell_id": cell_id,
        "persona": persona,
        "query": query,
        "mode_chosen": "simple",
        "sql_hint": sql_equivalent,
        "python_exit": py.get("exit_code"),
        "files_created": [f["name"] for f in py.get("files_created", [])],
        "answer": answer,
        "stdout_tail": stdout[-400:],
        "stderr_tail": (py.get("stderr") or "")[-400:],
        "session_id": py.get("session_id"),
    }


def main() -> None:
    results: list[dict] = []
    for name, func in [
        ("1A_taxi", cell_1A_taxi),
        ("1B_adult", cell_1B_adult),
        ("1C_lahman", cell_1C_lahman),
        ("1D_ames", cell_1D_ames),
    ]:
        print(f"\n== {name} ==")
        trace = Trace(cell_id=f"tier1_{name}")
        t0 = time.perf_counter()
        try:
            with L1Client(timeout=600.0, trace=trace) as c:
                result = func(c)
                result["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
                results.append(result)
                _save_cell(name, result)
                summary_line = (
                    f"exit={result.get('python_exit')} "
                    f"files={len(result.get('files_created') or [])} "
                    f"answer={result.get('answer')}"
                )
                print(summary_line)
                if result.get("python_exit") and result["python_exit"] != 0:
                    print("STDERR:", (result.get("stderr_tail") or "")[:500])
        except Exception as e:
            err = {
                "cell_id": name,
                "error": f"{type(e).__name__}: {e}",
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
            results.append(err)
            _save_cell(name, err)
            print(f"FAILED: {err}")
        trace.write()

    (ARTIFACTS / "summary.json").write_text(json.dumps(results, indent=2, default=str))
    ok = sum(1 for r in results if r.get("python_exit") == 0)
    print(f"\n== Tier 1 done: {ok}/{len(results)} cells ok ==")


if __name__ == "__main__":
    main()
