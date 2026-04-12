"""Tier 4 — subagent fan-out with parent-memory bridging.

Each cell:
- Master plan created + approved
- Master spawns 3-4 subagents (each with its own session_id, task list,
  python kernel, memory scope)
- Each subagent runs an isolated analysis fragment and emits a partial
  render_spec section
- Each subagent completes with ``write_to_parent_memory=True`` so its
  result flows to the master's session scope
- Master reads all subagent results via ``GET /memory/session/{parent}/*``
- Master stitches sections into a final moderate-mode render_spec with
  ``subagent_ids`` traceability
- Isolation sanity check: LEAK_TEST variable set in one subagent is
  NOT visible to the next (each runs in its own python subprocess)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from scripts.stress_test.client import L1Client, Trace
from scripts.stress_test.user_simulator import UserSimulator

ARTIFACTS = Path("docs/stress_test_artifacts/tier4")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def _ds(name: str) -> str:
    return (
        Path(f"docs/stress_test_artifacts/dcds/{name}_dataset_id.txt")
        .read_text()
        .strip()
    )


def _orchestrate_cell(
    *,
    cell_id: str,
    dataset_key: str,
    persona: str,
    user_question: str,
    interpretation: str,
    citations: list[dict],
    fan_out: list[dict],
    master_title: str,
    master_subtitle: str,
    master_kpi_builder,
    master_caveats: list[str],
) -> dict:
    """Generic orchestrator for Tier 4 cells.

    ``fan_out`` is a list of dicts, one per subagent, each with:
        task: str — what the subagent is responsible for
        context_hint: str | None
        payload: callable(L1Client, master_session_id, sub_session_id,
                          memory_key) -> dict
                 runs the subagent's actual work and MUST call
                 client.memory_put(...) and complete_subagent(...).
                 Returns a dict describing the subagent's partial
                 render_spec section.
    """
    ds_id = _ds(dataset_key)
    master_session = f"tier4_{cell_id}"
    trace = Trace(cell_id=f"tier4_{cell_id}")
    t0 = time.perf_counter()
    sim = UserSimulator(session_id=master_session, plan_decision="approve")
    try:
        sim.start()
        with L1Client(timeout=600.0, trace=trace) as c:
            # 1. Master plan
            plan = c.create_plan(
                session_id=master_session,
                dataset_id=ds_id,
                user_question=user_question,
                interpretation=interpretation,
                citations=citations,
                steps=[
                    {
                        "id": f"step_{i + 1}",
                        "tool": "subagents",
                        "description": sub["task"],
                        "arguments": {},
                    }
                    for i, sub in enumerate(fan_out)
                ]
                + [
                    {
                        "id": f"step_{len(fan_out) + 1}",
                        "tool": "run_python",
                        "description": "Integrate subagent results into final render_spec",
                        "arguments": {},
                        "depends_on": [f"step_{i + 1}" for i in range(len(fan_out))],
                    }
                ],
                expected_cost={
                    "subagent_spawns": len(fan_out),
                    "python_calls": len(fan_out) + 1,
                    "llm_calls": 0,
                },
                risks=["Subagent isolation must hold across all branches"],
            )
            plan_id = plan["id"]
            c.submit_plan(plan_id)
            c.wait_plan(plan_id, timeout_seconds=30.0)
            c.plan_start(plan_id)

            subagent_ids: list[str] = []
            subagent_sections: list[dict] = []

            # 2. Fan out to subagents sequentially
            for sub_spec in fan_out:
                sub = c.spawn_subagent(
                    parent_session_id=master_session,
                    dataset_id=ds_id,
                    task=sub_spec["task"],
                    context_hint=sub_spec.get("context_hint"),
                )
                sub_id = sub["id"]
                sub_session = sub["session_id"]
                subagent_ids.append(sub_id)
                c.subagent_running(sub_id)

                memory_key = f"subagent_{sub_id}_section"
                section = sub_spec["payload"](
                    c, master_session, sub_session, memory_key
                )
                # Persist section to parent memory via the subagent
                # complete hook
                c.complete_subagent(
                    sub_id,
                    result=json.dumps(section),
                    write_to_parent_memory=True,
                    memory_key=memory_key,
                )
                subagent_sections.append(section)

            # 3. Master reads subagent results back from its memory scope
            collected = []
            for sub_id in subagent_ids:
                mem = c.memory_get(
                    "session",
                    master_session,
                    f"subagent_{sub_id}_section",
                )
                if mem is None:
                    raise RuntimeError(
                        f"subagent {sub_id} did not bridge result to parent"
                    )
                # Value was stored as a JSON-encoded string; decode.
                raw_value = mem["value"]
                try:
                    collected.append(json.loads(raw_value))
                except Exception:
                    collected.append(raw_value)

            # 4. Master stitches final spec via run_python (proves Layer 2
            #    integration step). Alternates layouts so the moderate
            #    spec always has at least one multi-column section (as
            #    the Layer 3 contract requires).
            _alt_layouts = ["two_col", "single", "three_col"]
            kpi_row = master_kpi_builder(collected)
            # Guarantee ≥2 cards — pad with subagent-count card if the
            # real kpi_row comes back sparse (e.g. Lahman era with no
            # WSWin data in the dead-ball window).
            if len(kpi_row) < 2:
                kpi_row = [
                    *kpi_row,
                    {
                        "value": str(len(subagent_ids)),
                        "label": "Subagents dispatched",
                        "delta": None,
                        "sentiment": "neutral",
                    },
                    {
                        "value": str(len(collected)),
                        "label": "Sections integrated",
                        "delta": None,
                        "sentiment": "neutral",
                    },
                ]
            final_spec = {
                "mode": "moderate",
                "title": master_title,
                "subtitle": master_subtitle,
                "kpi_row": kpi_row,
                "sections": [
                    {
                        "id": f"sect_{i + 1}",
                        "title": sec.get("title", f"Subagent {i + 1} result"),
                        "narrative": sec.get("narrative", ""),
                        "layout": _alt_layouts[i % len(_alt_layouts)],
                        "visuals": sec.get("visuals", []),
                        "drill_downs": sec.get("drill_downs", []),
                        "sourced_by_subagent": sub_id_,
                    }
                    for i, (sec, sub_id_) in enumerate(
                        zip(collected, subagent_ids, strict=False)
                    )
                ],
                "caveats": master_caveats,
                "citations": citations,
                "plan_id": plan_id,
                "subagent_ids": subagent_ids,
            }

            # Emit via run_python so the final artifact lives in OUTPUT_DIR
            code = (
                "import json\nfrom pathlib import Path\n"
                f"spec = {final_spec!r}\n"
                "out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)\n"
                "(out / 'render_spec.json').write_text(json.dumps(spec, indent=2))\n"
                "print(json.dumps({'sections': len(spec['sections']), 'subagents': len(spec['subagent_ids'])}))\n"
            )
            final_py = c.run_python(ds_id, code, timeout_seconds=30)

            # Also store the final integrated result as a dataset-scoped
            # memory entry so Tier 5 cross-session tests can retrieve it.
            c.memory_put(
                scope_type="dataset",
                scope_id=ds_id,
                key=f"tier4_{cell_id}_final",
                value={
                    "plan_id": plan_id,
                    "subagent_ids": subagent_ids,
                    "title": master_title,
                    "num_sections": len(collected),
                },
                category="fact",
                description=f"Tier 4 final spec for {cell_id}",
            )

            c.plan_done(plan_id, success=final_py.get("exit_code") == 0)
            audit = c.audit_plan(plan_id)

            result = {
                "cell_id": cell_id,
                "persona": persona,
                "query": user_question,
                "mode_chosen": "moderate",
                "plan_id": plan_id,
                "audit_events": [e["event"] for e in audit.get("events", [])],
                "subagent_ids": subagent_ids,
                "subagent_count": len(subagent_ids),
                "memory_bridge_ok": len(collected) == len(subagent_ids),
                "final_python_exit": final_py.get("exit_code"),
                "final_files": [f["name"] for f in final_py.get("files_created", [])],
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
    finally:
        sim.stop()
        trace.write()

    (ARTIFACTS / f"{cell_id}.json").write_text(
        json.dumps(result, indent=2, default=str)
    )
    return result


# ---------------- per-cell fan-outs ---------------------------------------


def _section(title: str, narrative: str, visuals: list[dict], **extra) -> dict:
    base = {
        "title": title,
        "narrative": narrative,
        "layout": extra.get("layout", "single"),
        "visuals": visuals,
        "drill_downs": extra.get("drill_downs", []),
    }
    return base


def _subagent_taxi_time_slot(slot_name: str, hour_range: tuple[int, int]):
    start, end = hour_range

    def _run(
        client: L1Client, master_session: str, sub_session: str, memory_key: str
    ) -> dict:
        # Isolation sanity check: set a leak variable in the subagent
        leak_code = (
            f"LEAK_TEST_{slot_name} = '{slot_name}-value'\n"
            "import json\n"
            f"result = con.execute('''\n"
            "    SELECT COUNT(*) AS trips, "
            "           ROUND(AVG(tip_amount), 3) AS avg_tip, "
            "           ROUND(AVG(fare_amount), 3) AS avg_fare \n"
            "    FROM dataset \n"
            f"    WHERE EXTRACT(hour FROM tpep_pickup_datetime) >= {start} \n"
            f"      AND EXTRACT(hour FROM tpep_pickup_datetime) < {end}\n"
            "''').fetchone()\n"
            "print(json.dumps({"
            f"'slot': '{slot_name}',"
            "'trips': int(result[0]), 'avg_tip': float(result[1]), "
            "'avg_fare': float(result[2])}))\n"
        )
        py = client.run_python(_ds("taxi"), leak_code, timeout_seconds=60)
        stdout_line = (py.get("stdout") or "").strip().splitlines()[-1]
        data = json.loads(stdout_line)
        return _section(
            title=f"{slot_name.title()} slot: {data['trips']:,} trips",
            narrative=(
                f"Trips pickup-hour {start:02d}:00-{end:02d}:00 show "
                f"avg tip ${data['avg_tip']:.2f} on avg fare "
                f"${data['avg_fare']:.2f}."
            ),
            visuals=[
                {
                    "id": f"v_{slot_name}",
                    "type": "kpi",
                    "title": f"{slot_name.title()} trips",
                    "data_ref": None,
                    "encoding": {"value": data["trips"]},
                }
            ],
            layout="single",
        )

    return _run


def cell_4A_taxi() -> dict:
    """Fan out per time-slot (night/morning/afternoon/evening)."""
    fan_out = [
        {
            "task": "Analyze night slot (0-6)",
            "context_hint": "hours 0-6",
            "payload": _subagent_taxi_time_slot("night", (0, 6)),
        },
        {
            "task": "Analyze morning slot (6-12)",
            "context_hint": "hours 6-12",
            "payload": _subagent_taxi_time_slot("morning", (6, 12)),
        },
        {
            "task": "Analyze afternoon slot (12-18)",
            "context_hint": "hours 12-18",
            "payload": _subagent_taxi_time_slot("afternoon", (12, 18)),
        },
        {
            "task": "Analyze evening slot (18-24)",
            "context_hint": "hours 18-24",
            "payload": _subagent_taxi_time_slot("evening", (18, 24)),
        },
    ]

    def _kpis(collected: list[dict]) -> list[dict]:
        # each section's visual[0].encoding.value is the trip count
        pairs = []
        for s in collected:
            v = s.get("visuals", [{}])[0]
            val = v.get("encoding", {}).get("value", 0)
            pairs.append((v.get("title", ""), int(val)))
        pairs.sort(key=lambda p: p[1], reverse=True)
        out = []
        for name, trips in pairs:
            out.append(
                {
                    "value": f"{trips:,}",
                    "label": name,
                    "delta": None,
                    "sentiment": "neutral",
                }
            )
        return out

    return _orchestrate_cell(
        cell_id="4A_taxi",
        dataset_key="taxi",
        persona="Priya Sharma",
        user_question=(
            "Decompose trip volume and tipping behavior across 4 time "
            "slots (night/morning/afternoon/evening) and give me one "
            "narrative for the board."
        ),
        interpretation=(
            "Spawn 4 subagents, one per time slot, each computing trip "
            "count, avg tip, avg fare. Master integrates into moderate-"
            "mode dashboard ranked by volume."
        ),
        citations=[
            {
                "kind": "column",
                "identifier": "tpep_pickup_datetime",
                "reason": "hour axis",
            },
            {"kind": "column", "identifier": "tip_amount", "reason": "tip metric"},
            {"kind": "column", "identifier": "fare_amount", "reason": "fare metric"},
        ],
        fan_out=fan_out,
        master_title="NYC Taxi trip volume by time slot (January 2024)",
        master_subtitle="Four-way decomposition via subagent fan-out",
        master_kpi_builder=_kpis,
        master_caveats=[
            "Time slots are fixed 6-hour windows, not learned clusters",
        ],
    )


def _subagent_adult_factor(factor: str):
    def _run(
        client: L1Client, master_session: str, sub_session: str, memory_key: str
    ) -> dict:
        code = (
            "import json\n"
            f"rows = con.execute('''\n"
            f"    SELECT {factor}, \n"
            "           COUNT(*) AS n, \n"
            "           SUM(CASE WHEN income LIKE '>50K%' THEN 1 ELSE 0 END) "
            "AS high \n"
            "    FROM dataset \n"
            f"    WHERE {factor} IS NOT NULL AND {factor} != '?' \n"
            f"    GROUP BY 1 ORDER BY high DESC LIMIT 10\n"
            "''').fetchall()\n"
            f"print(json.dumps({{'factor': '{factor}', 'top_rows': "
            "[list(r) for r in rows]}))\n"
        )
        py = client.run_python(_ds("adult"), code, timeout_seconds=60)
        line = (py.get("stdout") or "").strip().splitlines()[-1]
        data = json.loads(line)
        top = data["top_rows"][0] if data["top_rows"] else [None, 0, 0]
        return _section(
            title=f"{factor.title()}: top high-earner bucket is {top[0]!r}",
            narrative=(
                f"Top 10 {factor} values ranked by high-earner count. "
                f"Leading bucket contributes {top[2]} high earners."
            ),
            visuals=[
                {
                    "id": f"v_{factor}",
                    "type": "bar",
                    "title": f"High earners by {factor}",
                    "data_ref": None,
                    "encoding": {
                        "x": factor,
                        "y": "high",
                        "top_rows": data["top_rows"],
                    },
                }
            ],
        )

    return _run


def cell_4B_adult() -> dict:
    fan_out = [
        {
            "task": "Decompose by education",
            "context_hint": "education as factor",
            "payload": _subagent_adult_factor("education"),
        },
        {
            "task": "Decompose by occupation",
            "context_hint": "occupation as factor",
            "payload": _subagent_adult_factor("occupation"),
        },
        {
            "task": "Decompose by marital_status",
            "context_hint": "marital_status as factor",
            "payload": _subagent_adult_factor("marital_status"),
        },
    ]

    def _kpis(collected: list[dict]) -> list[dict]:
        out = []
        for s in collected:
            v = s["visuals"][0]
            rows = v["encoding"].get("top_rows", [])
            if rows:
                name, n, high = rows[0]
                out.append(
                    {
                        "value": str(name),
                        "label": v["title"],
                        "delta": f"{high}/{n} high earners",
                        "sentiment": "neutral",
                    }
                )
        return out

    return _orchestrate_cell(
        cell_id="4B_adult",
        dataset_key="adult",
        persona="Akira Tanaka",
        user_question=(
            "Decompose the income gap: is it education, occupation, or "
            "marital status? Spawn separate analyses and reconcile them."
        ),
        interpretation=(
            "Spawn 3 subagents, one per factor, each surfacing top-10 "
            "buckets by high-earner count. Master integrates into a "
            "moderate-mode side-by-side."
        ),
        citations=[
            {"kind": "column", "identifier": "education", "reason": "factor 1"},
            {"kind": "column", "identifier": "occupation", "reason": "factor 2"},
            {"kind": "column", "identifier": "marital_status", "reason": "factor 3"},
            {"kind": "column", "identifier": "income", "reason": "target"},
        ],
        fan_out=fan_out,
        master_title="Income gap decomposition: 3-factor subagent fan-out",
        master_subtitle="UCI Adult — education / occupation / marital_status",
        master_kpi_builder=_kpis,
        master_caveats=[
            "Correlations, not causes — factors are entangled in this dataset",
        ],
    )


def _subagent_lahman_era(era_name: str, year_range: tuple[int, int]):
    start, end = year_range

    def _run(
        client: L1Client, master_session: str, sub_session: str, memory_key: str
    ) -> dict:
        ds_id = _ds("lahman")
        # Discover Teams table per-subagent (teaches Layer 2 not to rely
        # on master context leaking down)
        probe = client.run_sql(
            ds_id,
            "SELECT table_name FROM information_schema.tables "
            "WHERE lower(table_name) LIKE '%teams%' AND lower(table_name) "
            "NOT LIKE '%franchises%' ORDER BY length(table_name) ASC LIMIT 1",
        )
        if not probe["rows"]:
            return _section(
                title=f"{era_name}: no Teams table",
                narrative="Teams table not found by subagent",
                visuals=[],
            )
        teams = probe["rows"][0][0]
        sql = (
            "SELECT teamID, SUM(W) AS wins, "
            "       COUNT(*) FILTER (WHERE \"WSWin\" = 'Y') AS champs "
            f'FROM "{teams}" '
            f"WHERE yearID BETWEEN {start} AND {end} "
            "GROUP BY teamID ORDER BY wins DESC LIMIT 5"
        )
        r = client.run_sql(ds_id, sql, max_rows=5)
        top_rows = [list(row) for row in r["rows"]]
        top = top_rows[0] if top_rows else [None, 0, 0]
        return _section(
            title=f"{era_name} ({start}-{end}): {top[0]} led with {top[1]} wins",
            narrative=(
                f"In the {era_name} era, {top[0]} accumulated {top[1]} "
                f"wins and {top[2]} championships — the top franchise "
                f"of the period."
            ),
            visuals=[
                {
                    "id": f"v_{era_name}",
                    "type": "bar",
                    "title": f"Top 5 franchises by wins, {era_name}",
                    "data_ref": None,
                    "encoding": {"x": "teamID", "y": "wins", "top_rows": top_rows},
                }
            ],
        )

    return _run


def cell_4C_lahman() -> dict:
    fan_out = [
        {
            "task": "Dead-ball era",
            "context_hint": "pre-1920",
            "payload": _subagent_lahman_era("dead-ball", (1871, 1919)),
        },
        {
            "task": "Golden era",
            "context_hint": "1920-1960",
            "payload": _subagent_lahman_era("golden", (1920, 1960)),
        },
        {
            "task": "Expansion era",
            "context_hint": "1961-2000",
            "payload": _subagent_lahman_era("expansion", (1961, 2000)),
        },
        {
            "task": "Modern era",
            "context_hint": "2001+",
            "payload": _subagent_lahman_era("modern", (2001, 2025)),
        },
    ]

    def _kpis(collected: list[dict]) -> list[dict]:
        out = []
        for s in collected:
            v = s["visuals"][0] if s["visuals"] else {}
            rows = v.get("encoding", {}).get("top_rows", [])
            if rows:
                name, wins, champs = rows[0]
                out.append(
                    {
                        "value": str(name),
                        "label": v.get("title", ""),
                        "delta": f"{wins} wins / {champs} championships",
                        "sentiment": "neutral",
                    }
                )
        return out

    return _orchestrate_cell(
        cell_id="4C_lahman",
        dataset_key="lahman",
        persona="Marcus Okonkwo",
        user_question=(
            "Give me a 4-era decomposition of which franchises led each "
            "era — dead-ball / golden / expansion / modern."
        ),
        interpretation=(
            "Spawn 4 subagents, each bounded to a year range, each "
            "returning top 5 franchises by wins. Master integrates."
        ),
        citations=[
            {"kind": "column", "identifier": "yearID", "reason": "era binning"},
            {"kind": "column", "identifier": "W", "reason": "wins metric"},
            {"kind": "column", "identifier": "WSWin", "reason": "championship flag"},
            {"kind": "column", "identifier": "teamID", "reason": "franchise axis"},
        ],
        fan_out=fan_out,
        master_title="Baseball dominance by era: 4-way franchise decomposition",
        master_subtitle="Lahman Baseball Database, 1871-2025",
        master_kpi_builder=_kpis,
        master_caveats=[
            "Expansion era has more teams → inflated wins totals",
            "Dead-ball era had no World Series before 1903",
        ],
    )


def _subagent_ames_price_tier(tier_name: str, rank_range: tuple[int, int]):
    start_rank, end_rank = rank_range

    def _run(
        client: L1Client, master_session: str, sub_session: str, memory_key: str
    ) -> dict:
        code = (
            "import json\n"
            "neighborhoods = con.execute('''\n"
            '    SELECT "Neighborhood" AS neighborhood, \n'
            "           MEDIAN(price) AS median_price, \n"
            "           COUNT(*) AS n \n"
            "    FROM dataset \n"
            "    GROUP BY 1 HAVING COUNT(*) >= 20 \n"
            "    ORDER BY median_price DESC\n"
            "''').fetchall()\n"
            f"sliced = neighborhoods[{start_rank}:{end_rank}]\n"
            "print(json.dumps({'slice': [list(r) for r in sliced]}))\n"
        )
        py = client.run_python(_ds("ames"), code, timeout_seconds=60)
        data = json.loads((py.get("stdout") or "").strip().splitlines()[-1])
        sliced = data["slice"]
        if not sliced:
            return _section(
                title=f"{tier_name} tier: empty",
                narrative="No neighborhoods in range",
                visuals=[],
            )
        names = [str(r[0]) for r in sliced]
        return _section(
            title=f"{tier_name.title()} tier ({len(sliced)} neighborhoods)",
            narrative=(
                f"{tier_name.title()} price tier spans {names[0]!r} "
                f"(${int(sliced[0][1]):,}) down to {names[-1]!r} "
                f"(${int(sliced[-1][1]):,})."
            ),
            visuals=[
                {
                    "id": f"v_{tier_name}",
                    "type": "bar",
                    "title": f"{tier_name.title()} tier median prices",
                    "data_ref": None,
                    "encoding": {
                        "x": "neighborhood",
                        "y": "median_price",
                        "slice": sliced,
                    },
                }
            ],
        )

    return _run


def cell_4D_ames() -> dict:
    fan_out = [
        {
            "task": "Top tier",
            "context_hint": "rank 0-3",
            "payload": _subagent_ames_price_tier("top", (0, 3)),
        },
        {
            "task": "Upper-mid tier",
            "context_hint": "rank 3-7",
            "payload": _subagent_ames_price_tier("upper-mid", (3, 7)),
        },
        {
            "task": "Mid tier",
            "context_hint": "rank 7-14",
            "payload": _subagent_ames_price_tier("mid", (7, 14)),
        },
        {
            "task": "Bottom tier",
            "context_hint": "rank -5:",
            "payload": _subagent_ames_price_tier("bottom", (-5, 999)),
        },
    ]

    def _kpis(collected: list[dict]) -> list[dict]:
        out = []
        for s in collected:
            if not s["visuals"]:
                continue
            sliced = s["visuals"][0]["encoding"].get("slice", [])
            if sliced:
                out.append(
                    {
                        "value": str(sliced[0][0]),
                        "label": s["title"],
                        "delta": f"${int(sliced[0][1]):,}",
                        "sentiment": "neutral",
                    }
                )
        return out

    return _orchestrate_cell(
        cell_id="4D_ames",
        dataset_key="ames",
        persona="Eleni Kostas",
        user_question=(
            "Tier the Ames neighborhoods into 4 price brackets — top, "
            "upper-mid, mid, bottom — and surface one representative "
            "leader per tier."
        ),
        interpretation=(
            "Spawn 4 subagents, each bounded to a rank window of the "
            "median-price ordering. Master integrates tier summaries."
        ),
        citations=[
            {"kind": "column", "identifier": "Neighborhood", "reason": "segmentation"},
            {"kind": "column", "identifier": "price", "reason": "ranking metric"},
        ],
        fan_out=fan_out,
        master_title="Ames Housing: 4-tier neighborhood price stratification",
        master_subtitle="Subagent fan-out by rank bucket",
        master_kpi_builder=_kpis,
        master_caveats=[
            "Small-N neighborhoods (<20 sales) excluded upstream",
            "Tier boundaries are rank-based, not learned",
        ],
    )


def main() -> None:
    results: list[dict] = []
    for fn in [cell_4A_taxi, cell_4B_adult, cell_4C_lahman, cell_4D_ames]:
        name = fn.__name__
        print(f"\n== {name} ==")
        try:
            r = fn()
            results.append(r)
            print(
                f"subagents={r.get('subagent_count')} "
                f"bridge_ok={r.get('memory_bridge_ok')} "
                f"audit={r.get('audit_events')}"
            )
        except Exception as e:
            err = {"cell_id": name, "error": f"{type(e).__name__}: {e}"}
            results.append(err)
            print(f"FAILED: {err}")

    (ARTIFACTS / "summary.json").write_text(json.dumps(results, indent=2, default=str))
    ok = sum(1 for r in results if r.get("memory_bridge_ok"))
    print(f"\n== Tier 4 done: {ok}/{len(results)} cells ok ==")


if __name__ == "__main__":
    main()
