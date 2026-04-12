"""Tier 2 — ambiguous question → ask_user → plan → approve → execute.

Each cell:
1. Starts a user-simulator thread
2. Posts an ask_user question with 2-3 options
3. Blocks on wait_ask_user — simulator auto-answers after a brief delay
4. Creates a plan with interpretation + DCD citations + 2-4 steps
5. Submits plan, blocks on wait — simulator auto-approves
6. execute_start → runs tools → execute_done
7. Emits mode=simple render_spec.json with caveats naming the resolved
   ambiguity
8. Captures full trace + plan audit trail
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from scripts.stress_test.client import L1Client, Trace
from scripts.stress_test.user_simulator import UserSimulator

ARTIFACTS = Path("docs/stress_test_artifacts/tier2")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def _ds(name: str) -> str:
    return (
        Path(f"docs/stress_test_artifacts/dcds/{name}_dataset_id.txt")
        .read_text()
        .strip()
    )


def _run_cell(
    *,
    cell_id: str,
    dataset_key: str,
    persona: str,
    user_query: str,
    ask_prompt: str,
    ask_options: list[str],
    ask_answer_hint: str,  # substring match for the simulator
    simulator_answer: str,
    interpretation: str,
    citations: list[dict],
    plan_steps: list[dict],
    risks: list[str],
    expected_cost: dict,
    python_code: str,
) -> dict:
    """Drive a single Tier 2 cell end to end."""
    ds_id = _ds(dataset_key)
    session_id = f"tier2_{cell_id}"
    trace = Trace(cell_id=f"tier2_{cell_id}")

    sim = UserSimulator(
        session_id=session_id,
        ask_user_answers={ask_answer_hint: simulator_answer},
        plan_decision="approve",
    )
    t0 = time.perf_counter()
    try:
        sim.start()
        with L1Client(timeout=600.0, trace=trace) as c:
            # 1. Read pruned context
            _, _ctx = c.get_context(ds_id, query=user_query)

            # 2. Ask the user (simulator answers)
            q = c.ask_user(
                session_id=session_id,
                prompt=ask_prompt,
                options=ask_options,
                allow_free_text=True,
                context=f"User originally asked: {user_query!r}",
            )
            answered = c.wait_ask_user(q["id"], timeout_seconds=30.0)
            if answered.get("status") != "answered":
                raise RuntimeError(f"ask_user not answered in time: {answered}")
            resolved_answer = answered.get("answer") or ""

            # 3. Create the plan
            plan = c.create_plan(
                session_id=session_id,
                dataset_id=ds_id,
                user_question=user_query,
                interpretation=interpretation.format(answer=resolved_answer),
                citations=citations,
                steps=plan_steps,
                expected_cost=expected_cost,
                risks=risks,
            )
            plan_id = plan["id"]

            # 4. Submit → wait → (simulator approves) → audit
            c.submit_plan(plan_id)
            decided = c.wait_plan(plan_id, timeout_seconds=30.0)
            if decided.get("status") != "approved":
                raise RuntimeError(f"plan not approved: status={decided.get('status')}")

            # 5. execute_start
            c.plan_start(plan_id)

            # 6. Run the Python payload — it produces the render_spec.json
            injected = python_code.replace(
                "{resolved_answer}", resolved_answer.replace('"', '\\"')
            )
            py = c.run_python(ds_id, injected, timeout_seconds=120)

            # 7. execute_done
            ok = py.get("exit_code") == 0
            c.plan_done(plan_id, success=ok, note=f"python exit={py.get('exit_code')}")

            # 8. Pull audit trail
            audit = c.audit_plan(plan_id)

            result = {
                "cell_id": cell_id,
                "persona": persona,
                "query": user_query,
                "resolved_ambiguity": resolved_answer,
                "plan_id": plan_id,
                "plan_status_after_execute": decided.get("status"),
                "audit_events": [e["event"] for e in audit.get("events", [])],
                "python_exit": py.get("exit_code"),
                "files_created": [f["name"] for f in py.get("files_created", [])],
                "stdout_tail": (py.get("stdout") or "")[-400:],
                "stderr_tail": (py.get("stderr") or "")[-400:],
                "session_id": py.get("session_id"),
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
    finally:
        sim.stop()
        trace.write()

    (ARTIFACTS / f"{cell_id}.json").write_text(
        json.dumps(result, indent=2, default=str)
    )
    return result


def cell_2A() -> dict:
    """Priya / Taxi: 'How busy were we last week?' — ambiguity: metric + window."""
    code = '''
import json
from pathlib import Path

# Last week of January 2024 = 2024-01-22 through 2024-01-28 (Mon-Sun).
trips_by_day = con.execute("""
    SELECT DATE_TRUNC('day', tpep_pickup_datetime) AS day,
           COUNT(*) AS trip_count,
           ROUND(SUM(total_amount), 2) AS total_revenue
    FROM dataset
    WHERE tpep_pickup_datetime >= DATE '2024-01-22'
      AND tpep_pickup_datetime < DATE '2024-01-29'
    GROUP BY 1 ORDER BY 1
""").df()

total_trips = int(trips_by_day["trip_count"].sum())
total_revenue = float(trips_by_day["total_revenue"].sum())
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
trips_by_day.to_parquet(out / "trips_last_week.parquet")

render_spec = {
    "mode": "simple",
    "headline": {
        "value": f"{total_trips:,}",
        "label": "Trips Jan 22-28 (last full week)",
    },
    "narrative": (
        f"For Jan 22-28, 2024, Yellow Taxi completed {total_trips:,} trips "
        f"with a combined fare+tip total of ${int(total_revenue):,}. "
        f"The daily curve shows the week-over-week rhythm."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "line",
            "title": "Trips per day, Jan 22-28 2024",
            "data_ref": "files/trips_last_week.parquet",
            "encoding": {"x": "day", "y": "trip_count"},
            "caption": "Trip volume by day",
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "tpep_pickup_datetime",
         "reason": "defines the time window"},
        {"kind": "column", "identifier": "total_amount",
         "reason": "secondary measure to cross-check volume"},
    ],
    "caveats": [
        "Resolved 'last week' via user clarification: {resolved_answer}",
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"total_trips": total_trips, "total_revenue": total_revenue}))
'''
    return _run_cell(
        cell_id="2A_taxi",
        dataset_key="taxi",
        persona="Priya Sharma",
        user_query="How busy were we last week?",
        ask_prompt=(
            "'Last week' and 'busy' both need clarification. The dataset "
            "covers all of Jan 2024. How should I interpret last week?"
        ),
        ask_options=[
            "trip count by day for Jan 22-28",
            "trip count for Jan 22-28 vs prior 7 days",
            "total revenue for Jan 22-28",
        ],
        ask_answer_hint="last week",
        simulator_answer="trip count by day for Jan 22-28",
        interpretation=(
            "Compute trip count per day for Jan 22-28, 2024 with total "
            "revenue as a secondary confirmation metric. User clarification: "
            "{answer}"
        ),
        citations=[
            {
                "kind": "column",
                "identifier": "tpep_pickup_datetime",
                "reason": "defines the 7-day window",
            },
            {
                "kind": "column",
                "identifier": "total_amount",
                "reason": "revenue cross-check",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Aggregate trips_by_day from dataset view",
                "arguments": {"sql": "SELECT date_trunc('day', pickup) ... GROUP BY 1"},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Emit render_spec with line chart of daily volume",
                "arguments": {},
                "depends_on": ["step_1"],
            },
        ],
        risks=[
            "Jan 22-28 falls entirely within the dataset — no out-of-range edge case",
            "'Busy' could alternatively mean driver hours, which we're not surfacing",
        ],
        expected_cost={"sql_calls": 1, "python_calls": 1, "llm_calls": 0},
        python_code=code,
    )


def cell_2B() -> dict:
    """Eleni / Adult: 'Who counts as successful in this data?'."""
    code = '''
import json
from pathlib import Path

# Successful = income > $50k alone (per user clarification).
# Characterize the successful group: education distribution + hours worked.
edu_split = con.execute("""
    SELECT education, COUNT(*) AS n
    FROM dataset
    WHERE income LIKE '>50K%'
    GROUP BY 1 ORDER BY n DESC
""").df()

avg_hours = con.execute("""
    SELECT income,
           ROUND(AVG(hours_per_week), 2) AS avg_hours,
           COUNT(*) AS n
    FROM dataset GROUP BY 1
""").df()

successful = int(avg_hours[avg_hours["income"].str.contains(">50K")].iloc[0]["n"])
total = int(avg_hours["n"].sum())
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
edu_split.to_parquet(out / "successful_edu.parquet")
avg_hours.to_parquet(out / "avg_hours.parquet")

render_spec = {
    "mode": "simple",
    "headline": {
        "value": f"{successful/total*100:.1f}%",
        "label": "Share of 'successful' respondents",
    },
    "narrative": (
        f"Under the income-only definition, {successful:,} of {total:,} "
        f"respondents ({successful/total*100:.1f}%) qualify as successful. "
        f"They cluster in higher-education buckets; see the education "
        f"breakdown for composition."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "bar",
            "title": "Successful (>$50k) respondents by education level",
            "data_ref": "files/successful_edu.parquet",
            "encoding": {"x": "education", "y": "n"},
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "income", "reason": "sole success criterion"},
        {"kind": "column", "identifier": "education", "reason": "composition breakdown"},
    ],
    "caveats": [
        "'Successful' resolved to income-only per user clarification: {resolved_answer}",
        "Excludes subjective wellbeing — only measurable labor income captured",
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"successful": successful, "total": total}))
'''
    return _run_cell(
        cell_id="2B_adult",
        dataset_key="adult",
        persona="Eleni Kostas",
        user_query="Who counts as successful in this data?",
        ask_prompt=(
            "'Successful' is subjective. I can measure it as: (a) income "
            "alone (>$50k), (b) income AND high education, or (c) income, "
            "education, and low weekly hours. Which definition should I "
            "use?"
        ),
        ask_options=[
            "income alone (>$50k)",
            "income + high education",
            "income + education + low hours",
        ],
        ask_answer_hint="successful",
        simulator_answer="income alone (>$50k) — other signals are downstream composition",
        interpretation=(
            "Successful = income >$50k, treated as the binary target. "
            "Surface the education mix and avg hours of the successful "
            "cohort as secondary composition. User clarification: {answer}"
        ),
        citations=[
            {
                "kind": "column",
                "identifier": "income",
                "reason": "binary target defining success",
            },
            {
                "kind": "column",
                "identifier": "education",
                "reason": "composition breakdown",
            },
            {
                "kind": "column",
                "identifier": "hours_per_week",
                "reason": "secondary workload signal",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Count successful cohort size + education mix",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Emit render_spec with bar chart of education mix",
                "arguments": {},
                "depends_on": ["step_1"],
            },
        ],
        risks=[
            "Success is operationally defined and may not match the user's mental model",
            "Income distribution has a subjective 'high earner' threshold at $50k",
        ],
        expected_cost={"sql_calls": 0, "python_calls": 1, "llm_calls": 0},
        python_code=code,
    )


def cell_2C() -> dict:
    """Marcus / Lahman: 'Which era dominates baseball?'.

    Lahman upload-multi only materializes the primary file (AllstarFull)
    as a Gold parquet — other tables (like Teams) live in the server's
    DuckDB but not in the sandbox. For this cell I pre-compute the
    decade aggregation via ``run_sql`` inside this function, then bake
    the resulting rows into the Python payload as a literal list — a
    documented Layer 2 workaround for multi-file datasets.
    """
    # Pre-compute the decade rollup against the server's Gold catalog.
    with L1Client(timeout=60.0) as pre:
        ds_id = _ds("lahman")
        probe = pre.run_sql(
            ds_id,
            "SELECT table_name FROM information_schema.tables "
            "WHERE lower(table_name) LIKE '%teams%' "
            "ORDER BY length(table_name) ASC LIMIT 5",
        )
        teams_table = None
        for row in probe["rows"]:
            tn = row[0]
            if "teams" in tn.lower() and not tn.startswith("raw_teams_franchises"):
                teams_table = tn
                break
        if not teams_table:
            return {"cell_id": "2C_lahman", "error": "no Teams table"}
        sql = (
            "SELECT (yearID / 10) * 10 AS decade, COUNT(*) AS champion_seasons "
            f'FROM "{teams_table}" '
            "WHERE \"WSWin\" = 'Y' "
            "GROUP BY 1 ORDER BY 1"
        )
        r = pre.run_sql(ds_id, sql)
        decade_rows = [(int(row[0]), int(row[1])) for row in r["rows"]]

    code_template = """
import json
from pathlib import Path
import pandas as pd

decade_rows = __DECADE_ROWS__
decades = pd.DataFrame(decade_rows, columns=["decade", "champion_seasons"])

top_idx = decades["champion_seasons"].idxmax()
top_decade = int(decades.iloc[top_idx]["decade"])
top_count = int(decades.iloc[top_idx]["champion_seasons"])
out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
decades.to_parquet(out / "champions_by_decade.parquet")

render_spec = {
        "mode": "simple",
    "headline": {
            "value": f"{top_decade}s",
        "label": f"Most-dominated decade ({top_count} World Series champions)",
    },
    "narrative": (
        f"Under the 'championships per decade' definition of dominance, "
        f"the {top_decade}s produced {top_count} World Series-winning "
        f"team-seasons — more than any other decade in the Lahman dataset."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "bar",
            "title": "Championships per decade",
            "data_ref": "files/champions_by_decade.parquet",
            "encoding": {"x": "decade", "y": "champion_seasons"},
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "WSWin", "reason": "World Series winner flag"},
        {
            "kind": "column", "identifier": "yearID", "reason": "temporal axis grouped by decade"},
    ],
    "caveats": [
        "Resolved 'era' via user clarification: {resolved_answer}",
        "Uses decade-of-birth style binning — does not account for expansion "
        "league entries before 1961",
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"top_decade": top_decade, "top_count": top_count}))
"""
    code = code_template.replace("__DECADE_ROWS__", repr(decade_rows))
    return _run_cell(
        cell_id="2C_lahman",
        dataset_key="lahman",
        persona="Marcus Okonkwo",
        user_query="Which era dominates baseball?",
        ask_prompt=(
            "'Era' and 'dominates' both need clarification. Should I "
            "measure by: (a) championships per decade, (b) franchises "
            "dynasty-length runs, or (c) total wins per decade?"
        ),
        ask_options=[
            "championships per decade",
            "dynasty-length runs by franchise",
            "total wins per decade",
        ],
        ask_answer_hint="era",
        simulator_answer="championships per decade — cleanest signal for the board",
        interpretation=(
            "Count championship seasons (WSWin='Y') grouped by decade "
            "(yearID / 10 * 10). The decade with the most champions is "
            "'dominant'. User clarification: {answer}"
        ),
        citations=[
            {
                "kind": "column",
                "identifier": "WSWin",
                "reason": "World Series winner flag",
            },
            {
                "kind": "column",
                "identifier": "yearID",
                "reason": "temporal axis for decade bucketing",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Discover the Teams table in the sandbox's duckdb",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Aggregate championships by decade",
                "arguments": {},
                "depends_on": ["step_1"],
            },
        ],
        risks=[
            "Expansion-era bias: more teams → more championships available per decade",
            "WS was not played in every year (1904, 1994)",
        ],
        expected_cost={"sql_calls": 0, "python_calls": 1, "llm_calls": 0},
        python_code=code,
    )


def cell_2D() -> dict:
    """Akira / Ames: 'Which homes are undervalued?' — ambiguity about baseline."""
    code = """
import json
from pathlib import Path

# Undervalued := price per sq ft below neighborhood median by ≥20%.
# Two-step: build neighborhood medians, then join manually in pandas to
# avoid case-sensitive SQL USING quirks.
medians = con.execute(
    'SELECT "Neighborhood" AS neighborhood, '
    '       MEDIAN(price * 1.0 / NULLIF(area, 0)) AS median_ppsf '
    "FROM dataset GROUP BY 1"
).df()
homes = con.execute(
    'SELECT "Neighborhood" AS neighborhood, price, area, '
    "       price * 1.0 / NULLIF(area, 0) AS ppsf "
    "FROM dataset WHERE area > 0"
).df()
joined = homes.merge(medians, on="neighborhood", how="left")
joined["ratio_vs_median"] = joined["ppsf"] / joined["median_ppsf"]
ranked = (
    joined[joined["ratio_vs_median"] <= 0.80]
    .sort_values("ratio_vs_median")
    .head(25)
    .reset_index(drop=True)
)

total_undervalued = int(len(ranked))
ratio_min = float(ranked["ratio_vs_median"].min()) if total_undervalued else 0.0
out = Path(OUTPUT_DIR)
out.mkdir(parents=True, exist_ok=True)
ranked.to_parquet(out / "undervalued_top25.parquet")

render_spec = {
    "mode": "simple",
    "headline": {
        "value": f"{total_undervalued}",
        "label": "Homes priced ≥20% below neighborhood median $/sqft",
    },
    "narrative": (
        f"Using 'price per sq ft ≤ 80% of the neighborhood median' as the "
        f"undervalued signal, {total_undervalued} homes meet the threshold. "
        f"The most extreme is {ratio_min*100:.0f}% of its neighborhood median."
    ),
    "visuals": [
        {
            "id": "v1",
            "type": "bar",
            "title": "Top 25 undervalued homes by ratio vs neighborhood $/sqft",
            "data_ref": "files/undervalued_top25.parquet",
            "encoding": {"x": "neighborhood", "y": "ratio_vs_median"},
        }
    ],
    "citations": [
        {"kind": "column", "identifier": "price", "reason": "numerator of $/sqft"},
        {"kind": "column", "identifier": "area", "reason": "denominator of $/sqft"},
        {"kind": "column", "identifier": "Neighborhood", "reason": "baseline grouping"},
    ],
    "caveats": [
        "Resolved 'undervalued' via user clarification: {resolved_answer}",
        "Does not adjust for age, condition, or quality ratings",
    ],
}
(out / "render_spec.json").write_text(json.dumps(render_spec, indent=2))
print(json.dumps({"undervalued_count": total_undervalued, "lowest_ratio": ratio_min}))
"""
    return _run_cell(
        cell_id="2D_ames",
        dataset_key="ames",
        persona="Akira Tanaka",
        user_query="Which homes are undervalued?",
        ask_prompt=(
            "'Undervalued' needs a baseline. Should I use: (a) $/sqft "
            "below neighborhood median, (b) absolute price below city "
            "median for same size bucket, or (c) price below a regression-"
            "predicted value?"
        ),
        ask_options=[
            "$/sqft below neighborhood median (≥20%)",
            "absolute price below city median (same size bucket)",
            "price below regression-predicted value",
        ],
        ask_answer_hint="undervalued",
        simulator_answer=(
            "$/sqft below neighborhood median by at least 20% — "
            "neighborhood-relative is the fairest baseline"
        ),
        interpretation=(
            "Flag homes whose price-per-square-foot is ≤ 80% of their "
            "neighborhood median $/sqft. Rank ascending by ratio. "
            "User clarification: {answer}"
        ),
        citations=[
            {
                "kind": "column",
                "identifier": "price",
                "reason": "numerator of price-per-sqft",
            },
            {
                "kind": "column",
                "identifier": "area",
                "reason": "denominator of price-per-sqft",
            },
            {
                "kind": "column",
                "identifier": "Neighborhood",
                "reason": "baseline grouping for relative comparison",
            },
        ],
        plan_steps=[
            {
                "id": "step_1",
                "tool": "run_python",
                "description": "Compute neighborhood median $/sqft and join back",
                "arguments": {},
            },
            {
                "id": "step_2",
                "tool": "run_python",
                "description": "Emit render_spec with ranked undervalued list",
                "arguments": {},
                "depends_on": ["step_1"],
            },
        ],
        risks=[
            "Doesn't adjust for home condition/age/quality",
            "Small neighborhoods may have unstable medians",
        ],
        expected_cost={"sql_calls": 0, "python_calls": 1, "llm_calls": 0},
        python_code=code,
    )


def main() -> None:
    results: list[dict] = []
    for cell_func in [cell_2A, cell_2B, cell_2C, cell_2D]:
        name = cell_func.__name__
        print(f"\n== {name} ==")
        try:
            r = cell_func()
            results.append(r)
            print(
                f"exit={r.get('python_exit')} "
                f"files={len(r.get('files_created') or [])} "
                f"audit={r.get('audit_events')}"
            )
            if r.get("python_exit") and r["python_exit"] != 0:
                print("STDERR:", (r.get("stderr_tail") or "")[:500])
        except Exception as e:
            err = {"cell_id": name, "error": f"{type(e).__name__}: {e}"}
            results.append(err)
            print(f"FAILED: {err}")

    (ARTIFACTS / "summary.json").write_text(json.dumps(results, indent=2, default=str))
    ok = sum(1 for r in results if r.get("python_exit") == 0)
    print(f"\n== Tier 2 done: {ok}/{len(results)} cells ok ==")


if __name__ == "__main__":
    main()
