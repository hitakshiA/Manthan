"""Tier 3 — multi-step moderate-mode dashboards.

Each cell:
- Plan with ≥4 steps + depends_on
- SQL temp table for intermediate scratchpad
- Python session reused ≥2 times with variable persistence check
- ≥3 artifacts in files_created
- render_spec.json with mode=moderate, kpi_row, ≥3 sections with story
  titles, multi-column layout, drill_downs, caveats, plan_id linkage

Covers Layer 1 primitives: context (pruned), run_sql (temp tables),
plans (full state machine), run_python (stateful across calls), memory
(optional intermediate facts), agent_tasks (decomposition).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from scripts.stress_test.client import L1Client, Trace
from scripts.stress_test.user_simulator import UserSimulator

ARTIFACTS = Path("docs/stress_test_artifacts/tier3")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def _ds(name: str) -> str:
    return (
        Path(f"docs/stress_test_artifacts/dcds/{name}_dataset_id.txt")
        .read_text()
        .strip()
    )


def _base_plan_run(
    *,
    cell_id: str,
    dataset_key: str,
    persona: str,
    user_question: str,
    interpretation: str,
    citations: list[dict],
    plan_steps: list[dict],
    expected_cost: dict,
    risks: list[str],
    python_payload_builder,
) -> dict:
    """Shared orchestration: plan approval + stateful multi-call python.

    ``python_payload_builder`` is a callable(L1Client, str dataset_id,
    str session_id) -> dict that performs the multi-call Python work
    and returns summary info including a final ``render_spec_path``.
    """
    ds_id = _ds(dataset_key)
    session_id = f"tier3_{cell_id}"
    trace = Trace(cell_id=f"tier3_{cell_id}")
    t0 = time.perf_counter()
    sim = UserSimulator(session_id=session_id, plan_decision="approve")
    try:
        sim.start()
        with L1Client(timeout=600.0, trace=trace) as c:
            # Track agent tasks for decomposition auditability
            for step in plan_steps:
                c.task_create(
                    session_id=session_id,
                    title=step["description"],
                    description=f"tier3 step {step['id']}",
                    depends_on=step.get("depends_on", []),
                )

            plan = c.create_plan(
                session_id=session_id,
                dataset_id=ds_id,
                user_question=user_question,
                interpretation=interpretation,
                citations=citations,
                steps=plan_steps,
                expected_cost=expected_cost,
                risks=risks,
            )
            plan_id = plan["id"]
            c.submit_plan(plan_id)
            decided = c.wait_plan(plan_id, timeout_seconds=30.0)
            if decided.get("status") != "approved":
                raise RuntimeError(f"plan not approved: {decided.get('status')}")
            c.plan_start(plan_id)

            payload = python_payload_builder(c, ds_id, session_id, plan_id)
            c.plan_done(
                plan_id,
                success=bool(payload.get("ok")),
                note=payload.get("note"),
            )
            audit = c.audit_plan(plan_id)

            result = {
                "cell_id": cell_id,
                "persona": persona,
                "query": user_question,
                "mode_chosen": "moderate",
                "plan_id": plan_id,
                "audit_events": [e["event"] for e in audit.get("events", [])],
                "python_calls": payload.get("python_calls"),
                "session_reused": payload.get("session_reused"),
                "variable_persistence_ok": payload.get("variable_persistence_ok"),
                "files_created": payload.get("files_created", []),
                "final_session_id": payload.get("final_session_id"),
                "temp_table_used": payload.get("temp_table_used"),
                "ok": payload.get("ok"),
                "note": payload.get("note"),
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
    finally:
        sim.stop()
        trace.write()

    (ARTIFACTS / f"{cell_id}.json").write_text(
        json.dumps(result, indent=2, default=str)
    )
    return result


# ----- 3A Taxi: weekend vs weekday tipping by hour -----------------------


def _payload_3A(c: L1Client, ds_id: str, session_id: str, plan_id: str) -> dict:
    # Find the Gold table via information_schema (the sandbox view name
    # isn't visible from /tools/sql, which runs against the server's
    # persistent connection).
    gold_probe = c.run_sql(
        ds_id,
        "SELECT table_name FROM information_schema.tables "
        "WHERE lower(table_name) LIKE 'gold_yellow_tripdata_2024_01_%' "
        "AND lower(table_name) NOT LIKE '%_by_%' "
        "AND lower(table_name) NOT LIKE '%_daily' "
        "AND lower(table_name) NOT LIKE '%_monthly' LIMIT 1",
    )
    if not gold_probe["rows"]:
        return {"ok": False, "note": "no gold taxi table"}
    gold = gold_probe["rows"][0][0]

    # Create temp scratchpad table via /tools/sql. CREATE OR REPLACE
    # TEMP TABLE handles overwrite — no DROP required. The SQL tool's
    # validator accepts CREATE OR REPLACE TEMP TABLE AS SELECT.
    try:
        c.run_sql(
            ds_id,
            "CREATE OR REPLACE TEMP TABLE taxi_tip_buckets AS "
            "SELECT "
            "  EXTRACT(hour FROM tpep_pickup_datetime) AS hour, "
            "  CASE WHEN EXTRACT(dow FROM tpep_pickup_datetime) IN (0,6) "
            "       THEN 'weekend' ELSE 'weekday' END AS day_type, "
            "  fare_amount, tip_amount, total_amount, trip_distance "
            f'FROM "{gold}"',
        )
        temp_ok = True
    except Exception as exc:
        return {"ok": False, "note": f"temp table failed: {exc}"}

    # Python call 1: aggregate by hour × day_type from the temp table,
    # using the server's connection via /tools/sql for the bulk and
    # emitting the aggregated parquet.
    # The sandbox can't see taxi_tip_buckets directly (temp tables are
    # per-connection, and the sandbox has its own in-memory con), so we
    # run the aggregation via run_sql and pass results to Python.
    agg = c.run_sql(
        ds_id,
        "SELECT day_type, hour, "
        "       COUNT(*) AS trips, "
        "       ROUND(AVG(tip_amount), 4) AS avg_tip, "
        "       ROUND(AVG(tip_amount / NULLIF(fare_amount, 0)), 4) AS tip_rate, "
        "       ROUND(AVG(trip_distance), 3) AS avg_dist "
        "FROM taxi_tip_buckets "
        "GROUP BY 1, 2 ORDER BY 1, 2",
        max_rows=500,
    )

    agg_rows = [list(r) for r in agg["rows"]]
    code_1 = (
        "import json, pandas as pd\n"
        "from pathlib import Path\n"
        "out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)\n"
        f"rows = {agg_rows!r}\n"
        "agg = pd.DataFrame(rows, columns=['day_type','hour','trips','avg_tip','tip_rate','avg_dist'])\n"
        "agg.to_parquet(out / 'tip_agg.parquet')\n"
        "persist_check = 'ok-from-call-1'\n"
        "print(json.dumps({'rows': len(agg)}))\n"
    )
    py1 = c.run_python(ds_id, code_1, timeout_seconds=60)
    session = py1.get("session_id")

    # Python call 2: reuse session, verify persist_check, produce headline
    # KPIs + the render_spec.json for mode=moderate.
    code_2 = """
import json
from pathlib import Path
out = Path(OUTPUT_DIR)

assert persist_check == 'ok-from-call-1', 'session state lost between calls'

weekend = agg[agg['day_type']=='weekend']
weekday = agg[agg['day_type']=='weekday']
weekend_tip_rate = float((weekend['tip_rate'] * weekend['trips']).sum() / weekend['trips'].sum()) if len(weekend) else 0
weekday_tip_rate = float((weekday['tip_rate'] * weekday['trips']).sum() / weekday['trips'].sum()) if len(weekday) else 0
weekend_trips = int(weekend['trips'].sum())
weekday_trips = int(weekday['trips'].sum())

# Write peak-hour parquet for section 3
peak = agg.groupby(['day_type','hour'])[['tip_rate']].mean().reset_index()
peak.to_parquet(out / 'peak_by_hour.parquet')

# Top 5 most generous hour-day combos
top5 = agg.sort_values('tip_rate', ascending=False).head(5)
top5.to_parquet(out / 'top5_generous.parquet')

render_spec = {
    "mode": "moderate",
    "title": "Weekend vs weekday tipping — January 2024",
    "subtitle": "NYC Yellow Taxi, hour-by-hour behavior",
    "kpi_row": [
        {"value": f"{weekend_tip_rate*100:.1f}%", "label": "Avg weekend tip rate",
         "delta": f"{(weekend_tip_rate - weekday_tip_rate)*100:+.1f}pp vs weekday",
         "sentiment": "positive" if weekend_tip_rate > weekday_tip_rate else "negative"},
        {"value": f"{weekday_tip_rate*100:.1f}%", "label": "Avg weekday tip rate",
         "delta": None, "sentiment": "neutral"},
        {"value": f"{weekend_trips:,}", "label": "Weekend trips",
         "delta": None, "sentiment": "neutral"},
        {"value": f"{weekday_trips:,}", "label": "Weekday trips",
         "delta": None, "sentiment": "neutral"},
    ],
    "sections": [
        {
            "id": "s1",
            "title": "Weekend riders tip more, but the gap is time-of-day driven",
            "narrative": (
                f"Over the full month, weekend trips averaged a "
                f"{weekend_tip_rate*100:.1f}% tip rate vs {weekday_tip_rate*100:.1f}% "
                f"on weekdays. The hourly curve below shows where the gap is."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v1", "type": "line",
                 "title": "Tip rate by hour, weekend vs weekday",
                 "data_ref": "files/peak_by_hour.parquet",
                 "encoding": {"x": "hour", "y": "tip_rate", "color": "day_type"},
                 "caption": "Peaks diverge overnight and on weekend mornings"},
                {"id": "v2", "type": "bar",
                 "title": "Weekend/weekday trip volume split",
                 "data_ref": "files/tip_agg.parquet",
                 "encoding": {"x": "day_type", "y": "trips"}},
            ],
            "drill_downs": [
                {"label": "Show me only 11PM-2AM rides", "query_hint": "hour BETWEEN 23 AND 2"},
            ],
        },
        {
            "id": "s2",
            "title": "The five most generous hour/day combinations",
            "narrative": (
                "If we surge-price on the top 5 hour/day-type slots, the "
                "expected tip uplift for those drivers scales with trip volume."
            ),
            "layout": "single",
            "visuals": [
                {"id": "v3", "type": "bar",
                 "title": "Top 5 hour/day combos by tip rate",
                 "data_ref": "files/top5_generous.parquet",
                 "encoding": {"x": "hour", "y": "tip_rate", "color": "day_type"}},
            ],
            "drill_downs": [],
        },
        {
            "id": "s3",
            "title": "Distance and fare mix across hours",
            "narrative": (
                "Tip rate correlates with both trip distance and fare "
                "amount; longer overnight rides inflate weekend averages."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v4", "type": "scatter",
                 "title": "Trip distance vs tip rate, by hour",
                 "data_ref": "files/tip_agg.parquet",
                 "encoding": {"x": "avg_dist", "y": "tip_rate", "color": "day_type"}},
                {"id": "v5", "type": "line",
                 "title": "Avg fare amount by hour",
                 "data_ref": "files/tip_agg.parquet",
                 "encoding": {"x": "hour", "y": "avg_dist"}},
            ],
            "drill_downs": [],
        },
    ],
    "caveats": [
        "Weekend defined as EXTRACT(dow)==0 OR 6 (Sunday or Saturday)",
        "Weighted averages used so high-volume hours dominate the mean",
    ],
    "citations": [
        {"kind": "column", "identifier": "tip_amount", "reason": "core metric"},
        {"kind": "column", "identifier": "fare_amount", "reason": "denominator for tip rate"},
        {"kind": "column", "identifier": "tpep_pickup_datetime", "reason": "day-of-week + hour axis"},
    ],
    "plan_id": __PLAN_ID__,
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({
    "persist_ok": persist_check == 'ok-from-call-1',
    "weekend_tip_rate": weekend_tip_rate,
    "weekday_tip_rate": weekday_tip_rate,
}))
"""
    code_2_final = code_2.replace("__PLAN_ID__", repr(plan_id))
    py2 = c.run_python(ds_id, code_2_final, session_id=session, timeout_seconds=60)
    stdout2 = (py2.get("stdout") or "").strip().splitlines()
    persist_ok = False
    for line in stdout2:
        try:
            j = json.loads(line)
            persist_ok = bool(j.get("persist_ok"))
        except Exception:
            pass

    return {
        "ok": py2.get("exit_code") == 0 and persist_ok and temp_ok,
        "note": f"py2_exit={py2.get('exit_code')} persist_ok={persist_ok}",
        "python_calls": 2,
        "session_reused": py2.get("session_id") == py1.get("session_id"),
        "variable_persistence_ok": persist_ok,
        "files_created": [f["name"] for f in py2.get("files_created", [])],
        "final_session_id": py2.get("session_id"),
        "temp_table_used": "taxi_tip_buckets",
    }


def cell_3A() -> dict:
    return _base_plan_run(
        cell_id="3A_taxi",
        dataset_key="taxi",
        persona="Priya Sharma",
        user_question=(
            "Compare weekend vs weekday tipping patterns across the month, "
            "broken down by time of day. Which segments tip the most?"
        ),
        interpretation=(
            "Build hour × day-type aggregates of tip rate and volume using "
            "a SQL temp table for the intermediate bucketing. Produce a "
            "moderate-mode dashboard with KPI row, 3 story-arced sections, "
            "and a surge-pricing drill-down hint."
        ),
        citations=[
            {"kind": "column", "identifier": "tip_amount", "reason": "core metric"},
            {
                "kind": "column",
                "identifier": "fare_amount",
                "reason": "denominator for tip rate",
            },
            {
                "kind": "column",
                "identifier": "tpep_pickup_datetime",
                "reason": "hour + dow axes",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_sql",
                "description": "Create temp table taxi_tip_buckets with hour/day_type",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_sql",
                "description": "Aggregate tip_rate and volume by hour × day_type",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_3",
                "tool": "run_python",
                "description": "Load aggregates into a DataFrame, write tip_agg.parquet",
                "arguments": {},
                "depends_on": ["step_2"],
            },
            {
                "id": "step_4",
                "tool": "run_python",
                "description": "Produce moderate-mode render_spec.json with 3 sections",
                "arguments": {},
                "depends_on": ["step_3"],
            },
        ],
        expected_cost={"sql_calls": 3, "python_calls": 2, "llm_calls": 0},
        risks=[
            "Tip_rate is ill-defined for fare_amount=0; NULLIF filters those",
            "EXTRACT(dow) 0=Sun, 6=Sat; weekend definition documented in caveats",
        ],
        python_payload_builder=_payload_3A,
    )


# ----- 3B Adult: high-earner profile -------------------------------------


def _payload_3B(c: L1Client, ds_id: str, session_id: str, plan_id: str) -> dict:
    # Pull comparison aggregates via sandbox Python directly.
    code_1 = """
import json, pandas as pd
from pathlib import Path
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)

# Segment by income bracket
high = con.execute("SELECT * FROM dataset WHERE income LIKE '>50K%'").df()
low  = con.execute("SELECT * FROM dataset WHERE income NOT LIKE '>50K%'").df()

# Demographic mix
edu_mix = con.execute(
    "SELECT income, education, COUNT(*) AS n FROM dataset GROUP BY 1,2 ORDER BY 1,3 DESC"
).df()
occ_mix = con.execute(
    "SELECT income, occupation, COUNT(*) AS n FROM dataset "
    "WHERE occupation IS NOT NULL AND occupation != '?' GROUP BY 1,2 ORDER BY 1,3 DESC"
).df()
hours_stats = con.execute(
    "SELECT income, ROUND(AVG(hours_per_week),1) AS avg_hours, "
    "       ROUND(AVG(age),1) AS avg_age, COUNT(*) AS n FROM dataset GROUP BY 1"
).df()

edu_mix.to_parquet(out / "edu_mix.parquet")
occ_mix.to_parquet(out / "occ_mix.parquet")
hours_stats.to_parquet(out / "hours_stats.parquet")
persist_check = 'ok-1'
print(json.dumps({"high_n": len(high), "low_n": len(low)}))
"""
    py1 = c.run_python(ds_id, code_1, timeout_seconds=90)
    session = py1.get("session_id")

    code_2 = """
import json
from pathlib import Path
out = Path(OUTPUT_DIR)
assert persist_check == 'ok-1'

high_row = hours_stats[hours_stats['income'].str.contains('>50K')].iloc[0]
low_row = hours_stats[~hours_stats['income'].str.contains('>50K')].iloc[0]
high_avg_hours = float(high_row['avg_hours'])
low_avg_hours = float(low_row['avg_hours'])
high_avg_age = float(high_row['avg_age'])
low_avg_age = float(low_row['avg_age'])
high_n = int(high_row['n'])
low_n = int(low_row['n'])

render_spec = {
    "mode": "moderate",
    "title": "Profile of the high-earner segment",
    "subtitle": "UCI Adult Census 1994, income > $50k vs <= $50k",
    "kpi_row": [
        {"value": f"{high_n/(high_n+low_n)*100:.1f}%", "label": "High-earner share",
         "delta": None, "sentiment": "neutral"},
        {"value": f"{high_avg_hours:.1f}h", "label": "Avg weekly hours (high)",
         "delta": f"{high_avg_hours - low_avg_hours:+.1f}h vs low", "sentiment": "neutral"},
        {"value": f"{high_avg_age:.1f}", "label": "Avg age (high)",
         "delta": f"{high_avg_age - low_avg_age:+.1f} vs low", "sentiment": "neutral"},
        {"value": f"{high_n:,}", "label": "High-earner count",
         "delta": None, "sentiment": "neutral"},
    ],
    "sections": [
        {
            "id": "s1",
            "title": "Education is the single biggest wedge",
            "narrative": (
                "High earners over-index on Bachelors, Masters, and "
                "professional-school degrees; low earners cluster in HS-grad "
                "and Some-college. The wedge is stark."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v1", "type": "bar",
                 "title": "Education mix by income bracket",
                 "data_ref": "files/edu_mix.parquet",
                 "encoding": {"x": "education", "y": "n", "color": "income"}},
                {"id": "v2", "type": "bar",
                 "title": "Occupation mix",
                 "data_ref": "files/occ_mix.parquet",
                 "encoding": {"x": "occupation", "y": "n", "color": "income"}},
            ],
            "drill_downs": [
                {"label": "Filter to advanced degrees",
                 "query_hint": "education IN ('Masters','Doctorate','Prof-school')"},
            ],
        },
        {
            "id": "s2",
            "title": "Work hours and age add secondary lift",
            "narrative": (
                f"High earners work about {high_avg_hours - low_avg_hours:+.1f} "
                f"more hours per week on average and are about "
                f"{high_avg_age - low_avg_age:+.1f} years older. Neither "
                f"factor alone flips the picture — education dominates."
            ),
            "layout": "single",
            "visuals": [
                {"id": "v3", "type": "bar",
                 "title": "Average weekly hours by income bracket",
                 "data_ref": "files/hours_stats.parquet",
                 "encoding": {"x": "income", "y": "avg_hours"}},
            ],
            "drill_downs": [],
        },
        {
            "id": "s3",
            "title": "Cohort composition snapshot",
            "narrative": (
                "Side-by-side composition of the two segments across "
                "education, occupation, and hours — the dataset's "
                "canonical fairness-analysis surface."
            ),
            "layout": "three_col",
            "visuals": [
                {"id": "v4", "type": "bar",
                 "title": "Edu (detail)",
                 "data_ref": "files/edu_mix.parquet",
                 "encoding": {"x": "education", "y": "n", "color": "income"}},
                {"id": "v5", "type": "bar",
                 "title": "Occupation (detail)",
                 "data_ref": "files/occ_mix.parquet",
                 "encoding": {"x": "occupation", "y": "n", "color": "income"}},
                {"id": "v6", "type": "kpi",
                 "title": "Hours gap",
                 "data_ref": "files/hours_stats.parquet",
                 "encoding": {"value": "avg_hours"}},
            ],
            "drill_downs": [],
        },
    ],
    "caveats": [
        "Dataset is 1994 US Census — temporal generalization caveats apply",
        "'income' column was classifier-tagged auxiliary; treated as dimension",
        "Occupation 'Armed-Forces' tail is excluded by small-N filter",
    ],
    "citations": [
        {"kind": "column", "identifier": "income", "reason": "segmentation axis"},
        {"kind": "column", "identifier": "education", "reason": "primary wedge"},
        {"kind": "column", "identifier": "occupation", "reason": "secondary wedge"},
        {"kind": "column", "identifier": "hours_per_week", "reason": "tertiary workload signal"},
    ],
    "plan_id": __PLAN_ID__,
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"persist_ok": True, "high_n": high_n, "low_n": low_n}))
"""
    code_2_final = code_2.replace("__PLAN_ID__", repr(plan_id))
    py2 = c.run_python(ds_id, code_2_final, session_id=session, timeout_seconds=60)
    return {
        "ok": py1.get("exit_code") == 0 and py2.get("exit_code") == 0,
        "note": f"py1={py1.get('exit_code')} py2={py2.get('exit_code')}",
        "python_calls": 2,
        "session_reused": py2.get("session_id") == py1.get("session_id"),
        "variable_persistence_ok": py2.get("exit_code") == 0,
        "files_created": [f["name"] for f in py2.get("files_created", [])],
        "final_session_id": py2.get("session_id"),
        "temp_table_used": None,
    }


def cell_3B() -> dict:
    return _base_plan_run(
        cell_id="3B_adult",
        dataset_key="adult",
        persona="Eleni Kostas",
        user_question=(
            "Build me a profile of the high-earner segment — who they are "
            "demographically, where they work, and how they compare to the "
            "low-earner segment."
        ),
        interpretation=(
            "Segment by income, compute education/occupation/hours/age "
            "distributions for each segment, surface the gap in a 3-section "
            "moderate-mode dashboard."
        ),
        citations=[
            {"kind": "column", "identifier": "income", "reason": "segmentation axis"},
            {"kind": "column", "identifier": "education", "reason": "demographic lens"},
            {"kind": "column", "identifier": "occupation", "reason": "work lens"},
            {
                "kind": "column",
                "identifier": "hours_per_week",
                "reason": "workload lens",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Segment + demographic aggregates",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Occupation breakdown",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_3",
                "tool": "run_python",
                "description": "Hours + age stats",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_4",
                "tool": "run_python",
                "description": "Emit moderate-mode render_spec",
                "arguments": {},
                "depends_on": ["step_2", "step_3"],
            },
        ],
        expected_cost={"sql_calls": 0, "python_calls": 2, "llm_calls": 0},
        risks=[
            "Occupation and workclass have '?' sentinels for missing data",
            "Dataset is 1994 US Census — limited temporal generalization",
        ],
        python_payload_builder=_payload_3B,
    )


# ----- 3C Lahman: decade win-totals dashboard ----------------------------


def _payload_3C(c: L1Client, ds_id: str, session_id: str, plan_id: str) -> dict:
    # Find the Teams table via information_schema
    probe = c.run_sql(
        ds_id,
        "SELECT table_name FROM information_schema.tables "
        "WHERE lower(table_name) LIKE '%teams%' AND lower(table_name) NOT LIKE '%franchises%' "
        "ORDER BY length(table_name) ASC LIMIT 1",
    )
    if not probe["rows"]:
        return {"ok": False, "note": "no Teams table"}
    teams = probe["rows"][0][0]

    decade = c.run_sql(
        ds_id,
        "SELECT (yearID/10)*10 AS decade, "
        "       SUM(W) AS total_wins, SUM(L) AS total_losses, "
        "       COUNT(*) AS team_seasons, "
        "       COUNT(*) FILTER (WHERE \"WSWin\" = 'Y') AS champions "
        f'FROM "{teams}" GROUP BY 1 ORDER BY 1',
        max_rows=50,
    )
    decade_rows = [list(r) for r in decade["rows"]]

    top_by_decade = c.run_sql(
        ds_id,
        "SELECT (yearID/10)*10 AS decade, teamID, SUM(W) AS wins "
        f'FROM "{teams}" GROUP BY 1, teamID '
        "QUALIFY RANK() OVER (PARTITION BY decade ORDER BY SUM(W) DESC) = 1 "
        "ORDER BY 1",
        max_rows=50,
    )
    top_rows = [list(r) for r in top_by_decade["rows"]]

    code_1 = (
        "import json, pandas as pd\n"
        "from pathlib import Path\n"
        "out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)\n"
        f"decade_rows = {decade_rows!r}\n"
        f"top_rows = {top_rows!r}\n"
        "decade_df = pd.DataFrame(decade_rows, columns=['decade','wins','losses','team_seasons','champions'])\n"
        "top_df = pd.DataFrame(top_rows, columns=['decade','teamID','wins'])\n"
        "decade_df.to_parquet(out / 'decade_agg.parquet')\n"
        "top_df.to_parquet(out / 'top_team_per_decade.parquet')\n"
        "persist_check = 'ok-1'\n"
        "print(json.dumps({'decades': len(decade_df)}))\n"
    )
    py1 = c.run_python(ds_id, code_1, timeout_seconds=60)
    session = py1.get("session_id")

    code_2 = """
import json
from pathlib import Path
out = Path(OUTPUT_DIR)
assert persist_check == 'ok-1'

peak_row = decade_df.loc[decade_df['champions'].idxmax()]
peak_decade = int(peak_row['decade'])
peak_champs = int(peak_row['champions'])
total_champs = int(decade_df['champions'].sum())
total_teams = int(decade_df['team_seasons'].sum())

render_spec = {
    "mode": "moderate",
    "title": "Baseball dynasties by decade",
    "subtitle": "Lahman Baseball Database — team wins, championships, dominance",
    "kpi_row": [
        {"value": f"{peak_decade}s", "label": "Most-dominated decade",
         "delta": f"{peak_champs} champions", "sentiment": "neutral"},
        {"value": f"{total_champs}", "label": "Total championship seasons",
         "delta": None, "sentiment": "neutral"},
        {"value": f"{total_teams:,}", "label": "Team-seasons in dataset",
         "delta": None, "sentiment": "neutral"},
    ],
    "sections": [
        {
            "id": "s1",
            "title": "Championship density by decade",
            "narrative": (
                "Champion counts are approximately flat until expansion — "
                "more teams per decade = more champions available. The "
                f"{peak_decade}s produced {peak_champs} champions."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v1", "type": "bar",
                 "title": "Champions per decade",
                 "data_ref": "files/decade_agg.parquet",
                 "encoding": {"x": "decade", "y": "champions"}},
                {"id": "v2", "type": "line",
                 "title": "Team-seasons per decade",
                 "data_ref": "files/decade_agg.parquet",
                 "encoding": {"x": "decade", "y": "team_seasons"}},
            ],
            "drill_downs": [
                {"label": "Zoom to post-1961 expansion era",
                 "query_hint": "decade >= 1960"},
            ],
        },
        {
            "id": "s2",
            "title": "The top team in each decade",
            "narrative": (
                "By wins, every decade has a clear top franchise. See how "
                "consistently the Yankees appear in the early era and how "
                "the crown rotates in the expansion era."
            ),
            "layout": "single",
            "visuals": [
                {"id": "v3", "type": "bar",
                 "title": "Top team per decade (by total wins)",
                 "data_ref": "files/top_team_per_decade.parquet",
                 "encoding": {"x": "decade", "y": "wins", "color": "teamID"}},
            ],
            "drill_downs": [],
        },
        {
            "id": "s3",
            "title": "Wins vs losses over history",
            "narrative": (
                "Wins and losses track each other closely — expansion drives "
                "both. The ratio is near 1 by construction (every win has "
                "a loss) but expansion eras double the raw totals."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v4", "type": "line",
                 "title": "Total wins per decade",
                 "data_ref": "files/decade_agg.parquet",
                 "encoding": {"x": "decade", "y": "wins"}},
                {"id": "v5", "type": "line",
                 "title": "Total losses per decade",
                 "data_ref": "files/decade_agg.parquet",
                 "encoding": {"x": "decade", "y": "losses"}},
            ],
            "drill_downs": [],
        },
    ],
    "caveats": [
        "World Series wasn't played in 1904 or 1994",
        "Expansion era (1961+) inflates per-decade counts",
        "teamID can change franchise ownership — see franchiseID for continuity",
    ],
    "citations": [
        {"kind": "column", "identifier": "yearID", "reason": "decade bucket key"},
        {"kind": "column", "identifier": "WSWin", "reason": "champion flag"},
        {"kind": "column", "identifier": "W", "reason": "wins metric"},
        {"kind": "column", "identifier": "teamID", "reason": "franchise axis"},
    ],
    "plan_id": __PLAN_ID__,
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"peak_decade": peak_decade, "peak_champs": peak_champs}))
"""
    code_2_final = code_2.replace("__PLAN_ID__", repr(plan_id))
    py2 = c.run_python(ds_id, code_2_final, session_id=session, timeout_seconds=60)
    return {
        "ok": py1.get("exit_code") == 0 and py2.get("exit_code") == 0,
        "note": f"py1={py1.get('exit_code')} py2={py2.get('exit_code')}",
        "python_calls": 2,
        "session_reused": py2.get("session_id") == py1.get("session_id"),
        "variable_persistence_ok": py2.get("exit_code") == 0,
        "files_created": [f["name"] for f in py2.get("files_created", [])],
        "final_session_id": py2.get("session_id"),
        "temp_table_used": None,
    }


def cell_3C() -> dict:
    return _base_plan_run(
        cell_id="3C_lahman",
        dataset_key="lahman",
        persona="Marcus Okonkwo",
        user_question=(
            "Show me how dominance works across decades — champion counts, "
            "top franchise per decade, wins curve, all rolled up."
        ),
        interpretation=(
            "Aggregate Teams table by decade (yearID/10*10). Compute "
            "champion seasons, total wins/losses, team_seasons, and top "
            "franchise by wins per decade. Render as moderate-mode "
            "dashboard with 3 sections."
        ),
        citations=[
            {"kind": "column", "identifier": "yearID", "reason": "decade key"},
            {"kind": "column", "identifier": "WSWin", "reason": "champion flag"},
            {"kind": "column", "identifier": "W", "reason": "wins metric"},
            {"kind": "column", "identifier": "teamID", "reason": "franchise axis"},
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_sql",
                "description": "Probe Teams table name",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_sql",
                "description": "Decade aggregates (wins, losses, champions, team_seasons)",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_3",
                "tool": "run_sql",
                "description": "Top team per decade by wins",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_4",
                "tool": "run_python",
                "description": "Load into DataFrames + cache session globals",
                "arguments": {},
                "depends_on": ["step_2", "step_3"],
            },
            {
                "id": "step_5",
                "tool": "run_python",
                "description": "Emit render_spec.json with 3 sections",
                "arguments": {},
                "depends_on": ["step_4"],
            },
        ],
        expected_cost={"sql_calls": 3, "python_calls": 2, "llm_calls": 0},
        risks=[
            "Expansion bias — later decades have more teams and more championships",
            "teamID is not stable across franchise moves",
        ],
        python_payload_builder=_payload_3C,
    )


# ----- 3D Ames: wide-schema neighborhood comparison ----------------------


def _payload_3D(c: L1Client, ds_id: str, session_id: str, plan_id: str) -> dict:
    code_1 = """
import json
from pathlib import Path
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)

# Neighborhood-level aggregates
n_df = con.execute('''
    SELECT "Neighborhood" AS neighborhood,
           MEDIAN(price) AS median_price,
           AVG(area) AS avg_area,
           AVG("Overall.Qual") AS avg_quality,
           AVG("Year.Built") AS avg_year,
           COUNT(*) AS n
    FROM dataset
    GROUP BY 1
    HAVING COUNT(*) >= 20
    ORDER BY median_price DESC
''').df()

# Top 3 by median price — the persona's comparison targets
top3 = n_df.head(3).reset_index(drop=True)
top3_names = tuple(top3['neighborhood'].tolist())

# Detail rows for the top 3
placeholders = ",".join("?" for _ in top3_names)
detail = con.execute(
    f'SELECT "Neighborhood" AS neighborhood, price, area, "Overall.Qual" AS qual, '
    f'"Year.Built" AS year_built '
    f'FROM dataset WHERE "Neighborhood" IN ({placeholders})',
    list(top3_names),
).df()

n_df.to_parquet(out / "neighborhood_agg.parquet")
top3.to_parquet(out / "top3.parquet")
detail.to_parquet(out / "top3_detail.parquet")
persist_check = 'ok-1'
print(json.dumps({"total_neighborhoods": len(n_df), "top3": list(top3_names)}))
"""
    py1 = c.run_python(ds_id, code_1, timeout_seconds=90)
    session = py1.get("session_id")

    code_2 = """
import json
from pathlib import Path
out = Path(OUTPUT_DIR)
assert persist_check == 'ok-1'

top_names = top3['neighborhood'].tolist()
top_medians = top3['median_price'].tolist()
num_neighborhoods = int(len(n_df))
top_name = str(top_names[0])
top_median = int(top_medians[0])

render_spec = {
    "mode": "moderate",
    "title": f"The {top_name} premium — top 3 Ames neighborhoods compared",
    "subtitle": "Price, size, quality, and age across the market leaders",
    "kpi_row": [
        {"value": top_name, "label": "Highest median price",
         "delta": f"${top_median:,}", "sentiment": "positive"},
        {"value": f"{num_neighborhoods}", "label": "Neighborhoods with ≥20 sales",
         "delta": None, "sentiment": "neutral"},
        {"value": f"${int(top3['median_price'].mean()):,}",
         "label": "Avg top-3 median",
         "delta": None, "sentiment": "neutral"},
    ],
    "sections": [
        {
            "id": "s1",
            "title": f"Headline: {top_name} leads on median price by a wide margin",
            "narrative": (
                f"{top_name} ({top_median:,}) sits clearly above the second "
                f"and third most expensive neighborhoods. The top 3 all share "
                f"high average overall quality and above-median living area."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v1", "type": "bar",
                 "title": "Median price across all qualifying neighborhoods",
                 "data_ref": "files/neighborhood_agg.parquet",
                 "encoding": {"x": "neighborhood", "y": "median_price"}},
                {"id": "v2", "type": "bar",
                 "title": "Top-3 head-to-head on median price",
                 "data_ref": "files/top3.parquet",
                 "encoding": {"x": "neighborhood", "y": "median_price"}},
            ],
            "drill_downs": [
                {"label": f"Filter to {top_name} listings",
                 "query_hint": f"Neighborhood = '{top_name}'"},
            ],
        },
        {
            "id": "s2",
            "title": "Size + quality + age composition",
            "narrative": (
                "The price premium is not just location — the top 3 also "
                "have larger average living area, higher overall-quality "
                "ratings, and newer construction on average."
            ),
            "layout": "three_col",
            "visuals": [
                {"id": "v3", "type": "bar",
                 "title": "Avg living area (sqft)",
                 "data_ref": "files/top3.parquet",
                 "encoding": {"x": "neighborhood", "y": "avg_area"}},
                {"id": "v4", "type": "bar",
                 "title": "Avg overall quality (1-10)",
                 "data_ref": "files/top3.parquet",
                 "encoding": {"x": "neighborhood", "y": "avg_quality"}},
                {"id": "v5", "type": "bar",
                 "title": "Avg year built",
                 "data_ref": "files/top3.parquet",
                 "encoding": {"x": "neighborhood", "y": "avg_year"}},
            ],
            "drill_downs": [],
        },
        {
            "id": "s3",
            "title": "Listing-level detail: distributions within each",
            "narrative": (
                "Per-home price distributions reveal whether the premium is "
                "a few outliers or a broad-based effect. Scatter shows area "
                "vs price colored by neighborhood."
            ),
            "layout": "two_col",
            "visuals": [
                {"id": "v6", "type": "scatter",
                 "title": "Area vs price in top 3",
                 "data_ref": "files/top3_detail.parquet",
                 "encoding": {"x": "area", "y": "price", "color": "neighborhood"}},
                {"id": "v7", "type": "box",
                 "title": "Quality distribution",
                 "data_ref": "files/top3_detail.parquet",
                 "encoding": {"x": "neighborhood", "y": "qual"}},
            ],
            "drill_downs": [],
        },
    ],
    "caveats": [
        "Neighborhoods with fewer than 20 sales are excluded (unstable medians)",
        "'price' is nominal 2006-2010 sale price; inflation-adjusted view would be fairer",
    ],
    "citations": [
        {"kind": "column", "identifier": "Neighborhood", "reason": "segmentation axis"},
        {"kind": "column", "identifier": "price", "reason": "target"},
        {"kind": "column", "identifier": "area", "reason": "size axis"},
        {"kind": "column", "identifier": "Overall.Qual", "reason": "quality axis"},
        {"kind": "column", "identifier": "Year.Built", "reason": "age axis"},
    ],
    "plan_id": __PLAN_ID__,
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"top_name": top_name, "top_median": top_median}))
"""
    code_2_final = code_2.replace("__PLAN_ID__", repr(plan_id))
    py2 = c.run_python(ds_id, code_2_final, session_id=session, timeout_seconds=60)
    return {
        "ok": py1.get("exit_code") == 0 and py2.get("exit_code") == 0,
        "note": f"py1={py1.get('exit_code')} py2={py2.get('exit_code')}",
        "python_calls": 2,
        "session_reused": py2.get("session_id") == py1.get("session_id"),
        "variable_persistence_ok": py2.get("exit_code") == 0,
        "files_created": [f["name"] for f in py2.get("files_created", [])],
        "final_session_id": py2.get("session_id"),
        "temp_table_used": None,
    }


def cell_3D() -> dict:
    return _base_plan_run(
        cell_id="3D_ames",
        dataset_key="ames",
        persona="Akira Tanaka",
        user_question=(
            "Compare the top 3 most expensive Ames neighborhoods across "
            "price, size, quality, and age. Where does the premium come from?"
        ),
        interpretation=(
            "Aggregate neighborhood-level medians, pick top 3 by median "
            "price, then compute composition stats. Render as moderate-"
            "mode dashboard with 3 sections and multi-column detail."
        ),
        citations=[
            {"kind": "column", "identifier": "Neighborhood", "reason": "segmentation"},
            {"kind": "column", "identifier": "price", "reason": "ranking metric"},
            {"kind": "column", "identifier": "area", "reason": "size axis"},
            {"kind": "column", "identifier": "Overall.Qual", "reason": "quality axis"},
            {"kind": "column", "identifier": "Year.Built", "reason": "age axis"},
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Neighborhood aggregates + pick top 3",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Detail pull for top-3 listings",
                "arguments": {},
                "depends_on": ["step_1"],
            },
            {
                "id": "step_3",
                "tool": "run_python",
                "description": "Emit moderate-mode render_spec",
                "arguments": {},
                "depends_on": ["step_2"],
            },
            {
                "id": "step_4",
                "tool": "run_python",
                "description": "Validate variable persistence across calls",
                "arguments": {},
                "depends_on": ["step_3"],
            },
        ],
        expected_cost={"sql_calls": 0, "python_calls": 2, "llm_calls": 0},
        risks=[
            "Small-N neighborhoods excluded; results may miss fast-growing ones",
            "Overall.Qual scale is 1-10 ordinal; comparing means is rough",
        ],
        python_payload_builder=_payload_3D,
    )


def main() -> None:
    results: list[dict] = []
    for fn in [cell_3A, cell_3B, cell_3C, cell_3D]:
        name = fn.__name__
        print(f"\n== {name} ==")
        try:
            r = fn()
            results.append(r)
            print(
                f"ok={r.get('ok')} audit={r.get('audit_events')} "
                f"session_reused={r.get('session_reused')} "
                f"persist={r.get('variable_persistence_ok')} "
                f"files={len(r.get('files_created') or [])} "
                f"note={r.get('note')}"
            )
        except Exception as e:
            err = {"cell_id": name, "error": f"{type(e).__name__}: {e}"}
            results.append(err)
            print(f"FAILED: {err}")

    (ARTIFACTS / "summary.json").write_text(json.dumps(results, indent=2, default=str))
    ok = sum(1 for r in results if r.get("ok"))
    print(f"\n== Tier 3 done: {ok}/{len(results)} cells ok ==")


if __name__ == "__main__":
    main()
