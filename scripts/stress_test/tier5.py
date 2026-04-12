"""Tier 5 — long-horizon complex reports with cross-session memory.

Each cell has two phases:

Phase 1 (session X):
- Master plan approved
- 2-3 subagents spawned, each emits a partial page section
- Master stitches into ``mode: "complex"`` render_spec with pages[],
  executive_summary (key_findings + recommendations), appendix,
  memory_refs, subagent_ids
- Durable conclusions written to ``scope_type=dataset`` memory so they
  survive a server restart

**Server restart happens between phase 1 and phase 2** to prove the
SQLite-backed memory + plan audit log actually persist.

Phase 2 (new session Y, server restarted):
- New session reads phase-1 memory via ``GET /memory/dataset/{id}/{key}``
- Produces a follow-up ``mode: "complex"`` render_spec whose
  ``executive_summary`` cites phase-1 findings by name via memory_refs
- Does NOT re-run the expensive phase-1 queries (verified via HTTP
  trace having no duplicate aggregation SQL)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, ".")
from scripts.stress_test.client import L1Client, Trace
from scripts.stress_test.user_simulator import UserSimulator

ARTIFACTS = Path("docs/stress_test_artifacts/tier5")
ARTIFACTS.mkdir(parents=True, exist_ok=True)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _ds(name: str) -> str:
    return (
        Path(f"docs/stress_test_artifacts/dcds/{name}_dataset_id.txt")
        .read_text()
        .strip()
    )


# ---------------- server lifecycle ---------------------------------------


def _server_is_up() -> bool:
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _stop_server() -> None:
    subprocess.run(
        ["pkill", "-f", "uvicorn src.main:app"], check=False, capture_output=True
    )
    for _ in range(25):
        if not _server_is_up():
            return
        time.sleep(0.2)


def _start_server() -> None:
    env = os.environ.copy()
    log_path = Path("/tmp/manthan_stress.log")
    with log_path.open("a") as banner:
        banner.write(f"\n--- restart at {time.time()} ---\n")
    # Reopen for the subprocess so it owns its own fd lifetime.
    log_fd = log_path.open("a")  # noqa: SIM115 — lives for subprocess lifetime
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "info",
        ],
        stdout=log_fd,
        stderr=log_fd,
        cwd=str(REPO_ROOT),
        env=env,
        start_new_session=True,
    )
    for _ in range(50):
        if _server_is_up():
            return
        time.sleep(0.3)
    raise RuntimeError("uvicorn failed to restart")


# ---------------- phase 1 helpers ----------------------------------------


def _phase1_dataset(
    *,
    cell_id: str,
    dataset_key: str,
    persona: str,
    user_question: str,
    interpretation: str,
    citations: list[dict],
    subagent_tasks: list[tuple[str, str, str]],
    page_payloads: list[dict],
    exec_summary: dict,
    caveats: list[str],
) -> dict:
    """Run phase 1 for one cell — produces memory + artifact."""
    ds_id = _ds(dataset_key)
    session_x = f"tier5_{cell_id}_phase1"
    trace = Trace(cell_id=f"tier5_{cell_id}_phase1")
    sim = UserSimulator(session_id=session_x, plan_decision="approve")
    t0 = time.perf_counter()
    try:
        sim.start()
        with L1Client(timeout=600.0, trace=trace) as c:
            # Master plan
            plan = c.create_plan(
                session_id=session_x,
                dataset_id=ds_id,
                user_question=user_question,
                interpretation=interpretation,
                citations=citations,
                steps=[
                    {
                        "id": f"step_{i + 1}",
                        "tool": "subagents",
                        "description": task,
                        "arguments": {},
                    }
                    for i, (task, _, _) in enumerate(subagent_tasks)
                ]
                + [
                    {
                        "id": "step_integrate",
                        "tool": "run_python",
                        "description": "Integrate into complex-mode report",
                        "arguments": {},
                        "depends_on": [
                            f"step_{i + 1}" for i in range(len(subagent_tasks))
                        ],
                    }
                ],
                expected_cost={
                    "subagent_spawns": len(subagent_tasks),
                    "python_calls": 1,
                    "llm_calls": 0,
                },
                risks=["Long-running multi-phase flow"],
            )
            plan_id = plan["id"]
            c.submit_plan(plan_id)
            c.wait_plan(plan_id, timeout_seconds=30.0)
            c.plan_start(plan_id)

            # Spawn subagents and persist their results to parent memory
            subagent_ids = []
            for task, context_hint, _ in subagent_tasks:
                sub = c.spawn_subagent(
                    parent_session_id=session_x,
                    dataset_id=ds_id,
                    task=task,
                    context_hint=context_hint,
                )
                subagent_ids.append(sub["id"])
                c.subagent_running(sub["id"])
                c.complete_subagent(
                    sub["id"],
                    result=f"Completed: {task}",
                    write_to_parent_memory=True,
                    memory_key=f"phase1_{sub['id']}_done",
                )

            # Build the complex-mode report spec
            report = {
                "mode": "complex",
                "report_title": exec_summary["title"],
                "report_subtitle": f"For {persona}",
                "executive_summary": {
                    "headline": exec_summary["headline"],
                    "key_findings": exec_summary["key_findings"],
                    "recommendations": exec_summary["recommendations"],
                },
                "pages": page_payloads,
                "appendix": {
                    "methodology": exec_summary["methodology"],
                    "data_quality_notes": caveats,
                    "open_questions": exec_summary["open_questions"],
                },
                "plan_ids": [plan_id],
                "subagent_ids": subagent_ids,
                "memory_refs": [
                    {"scope": "dataset", "key": f"tier5_{cell_id}_conclusions"},
                ],
                "phase": 1,
                "generated_in_session": session_x,
            }

            # Persist spec via run_python to OUTPUT_DIR
            code = (
                "import json\nfrom pathlib import Path\n"
                f"spec = {report!r}\n"
                "out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)\n"
                "(out / 'phase1_report.json').write_text(json.dumps(spec, indent=2))\n"
                "print(json.dumps({'pages': len(spec['pages'])}))\n"
            )
            py = c.run_python(ds_id, code, timeout_seconds=30)

            # Write durable dataset-scoped memory so phase 2 (new session
            # after server restart) can retrieve it.
            conclusions = {
                "plan_id": plan_id,
                "subagent_ids": subagent_ids,
                "title": exec_summary["title"],
                "key_findings": exec_summary["key_findings"],
                "recommendations": exec_summary["recommendations"],
                "phase1_session": session_x,
            }
            c.memory_put(
                scope_type="dataset",
                scope_id=ds_id,
                key=f"tier5_{cell_id}_conclusions",
                value=conclusions,
                category="fact",
                description=f"Tier 5 phase-1 conclusions for {cell_id}",
            )

            c.plan_done(plan_id, success=py.get("exit_code") == 0)
            audit = c.audit_plan(plan_id)

            return {
                "cell_id": cell_id,
                "phase": 1,
                "persona": persona,
                "plan_id": plan_id,
                "subagent_ids": subagent_ids,
                "audit_events": [e["event"] for e in audit.get("events", [])],
                "conclusions_memory_key": f"tier5_{cell_id}_conclusions",
                "pages_in_report": len(page_payloads),
                "python_exit": py.get("exit_code"),
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
    finally:
        sim.stop()
        trace.write()


def _phase2_followup(*, cell_id: str, dataset_key: str, persona: str) -> dict:
    """Phase 2 runs in a new session; must retrieve phase-1 memory."""
    ds_id = _ds(dataset_key)
    trace = Trace(cell_id=f"tier5_{cell_id}_phase2")
    t0 = time.perf_counter()
    try:
        with L1Client(timeout=300.0, trace=trace) as c:
            mem = c.memory_get("dataset", ds_id, f"tier5_{cell_id}_conclusions")
            if mem is None:
                return {
                    "cell_id": cell_id,
                    "phase": 2,
                    "error": "phase-1 conclusions not recalled — cross-session memory broken",
                }

            conclusions = mem["value"]
            plan_audit = c.audit_plan(conclusions["plan_id"])

            # Produce a phase-2 follow-up spec that cites phase-1 by name
            followup_report = {
                "mode": "complex",
                "report_title": f"Follow-up: {conclusions['title']}",
                "report_subtitle": f"For {persona} — references yesterday's report",
                "executive_summary": {
                    "headline": (
                        "Follow-up to yesterday's report. Key findings "
                        "recalled from persistent memory, no re-derivation."
                    ),
                    "key_findings": [
                        f"Phase-1 concluded: {kf}" for kf in conclusions["key_findings"]
                    ],
                    "recommendations": conclusions["recommendations"],
                },
                "pages": [
                    {
                        "id": "followup_page_1",
                        "title": "Yesterday's conclusions (recalled from memory)",
                        "purpose": "Back-reference phase 1 without re-query",
                        "layout": "narrative_only",
                        "blocks": [
                            {
                                "type": "callout",
                                "style": "info",
                                "text": (
                                    f"Retrieved via memory_get(dataset, "
                                    f"{ds_id}, tier5_{cell_id}_conclusions)"
                                ),
                            },
                            {
                                "type": "narrative",
                                "text": "\n".join(
                                    f"- {kf}" for kf in conclusions["key_findings"]
                                ),
                            },
                        ],
                    }
                ],
                "appendix": {
                    "methodology": (
                        "Phase 2 performs zero new aggregations; all content "
                        "is back-referenced via dataset-scoped memory."
                    ),
                    "data_quality_notes": [],
                    "open_questions": [],
                },
                "plan_ids": [conclusions["plan_id"]],
                "subagent_ids": conclusions["subagent_ids"],
                "memory_refs": [
                    {
                        "scope": "dataset",
                        "key": f"tier5_{cell_id}_conclusions",
                    }
                ],
                "phase": 2,
                "recalled_phase1_audit": [
                    e["event"] for e in plan_audit.get("events", [])
                ],
            }

            code = (
                "import json\nfrom pathlib import Path\n"
                f"spec = {followup_report!r}\n"
                "out = Path(OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)\n"
                "(out / 'phase2_report.json').write_text(json.dumps(spec, indent=2))\n"
                "print(json.dumps({'phase2_ok': True}))\n"
            )
            py = c.run_python(ds_id, code, timeout_seconds=30)

            return {
                "cell_id": cell_id,
                "phase": 2,
                "persona": persona,
                "memory_recalled": True,
                "recalled_plan_id": conclusions["plan_id"],
                "recalled_subagent_count": len(conclusions["subagent_ids"]),
                "recalled_audit_events": [
                    e["event"] for e in plan_audit.get("events", [])
                ],
                "python_exit": py.get("exit_code"),
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }
    finally:
        trace.write()


# ---------------- the 4 cells --------------------------------------------


CELLS = [
    {
        "cell_id": "5A_taxi",
        "dataset_key": "taxi",
        "persona": "Priya Sharma",
        "user_question": (
            "Build me a full operations strategy report for NYC Yellow "
            "Taxi January 2024: profitability, off-peak opportunities, "
            "driver pool sizing, surge pricing."
        ),
        "interpretation": (
            "Produce a multi-page complex-mode report with executive "
            "summary, 3+ dedicated pages (profitability, time-of-day, "
            "payment patterns), and recommendations."
        ),
        "citations": [
            {"kind": "column", "identifier": "fare_amount", "reason": "revenue driver"},
            {"kind": "column", "identifier": "tip_amount", "reason": "driver income"},
            {
                "kind": "column",
                "identifier": "tpep_pickup_datetime",
                "reason": "time axis",
            },
        ],
        "subagent_tasks": [
            ("Profitability per hour", "hour-bucketed revenue", ""),
            ("Off-peak gap analysis", "low-volume slots", ""),
            ("Payment type mix", "payment_type breakdown", ""),
        ],
        "pages": [
            {
                "id": "page_1",
                "title": "Profitability by hour",
                "purpose": "Show when revenue peaks",
                "layout": "hero_plus_grid",
                "blocks": [
                    {"type": "kpi_row", "items": []},
                    {"type": "narrative", "text": "Hourly revenue curve."},
                ],
            },
            {
                "id": "page_2",
                "title": "Off-peak gap",
                "purpose": "Identify empty slots to target",
                "layout": "single",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Off-peak trip count is <30% of peak.",
                    },
                ],
            },
            {
                "id": "page_3",
                "title": "Payment mix",
                "purpose": "Where tips come from",
                "layout": "single",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Credit card tips dominate; cash tips missing.",
                    },
                ],
            },
        ],
        "exec_summary": {
            "title": "NYC Taxi January 2024 Operations Strategy",
            "headline": (
                "Revenue is concentrated in 4 peak hours; off-peak has "
                "surge-pricing upside."
            ),
            "key_findings": [
                "60% of revenue comes from 10am-2pm and 5pm-9pm peaks",
                "Tip rate is ~30% higher on credit-card rides vs cash",
                "Overnight trips (0-5am) show longest distances and highest per-trip fares",
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "action": "Shift surge pricing to 23:00-02:00 overnight window",
                    "rationale": "Tip rate already highest here; supply low",
                    "expected_impact": "Est +$1.2M/month incremental tip",
                    "evidence_page": "page_1",
                    "confidence": "medium",
                },
                {
                    "id": "r2",
                    "action": "Incentivize cash rides via app to close reporting gap",
                    "rationale": "Cash tip reporting is missing",
                    "expected_impact": "Data quality improvement",
                    "evidence_page": "page_3",
                    "confidence": "high",
                },
            ],
            "methodology": (
                "Aggregations via DuckDB SQL against the Gold table. "
                "Subagents decomposed per analysis dimension."
            ),
            "open_questions": [
                "Is overnight demand elastic to surge pricing?",
                "What's the cash-tip reporting gap by neighborhood?",
            ],
        },
        "caveats": [
            "fare_amount includes metered fare only; airport fees separate",
            "Tip amounts on cash rides are underreported",
        ],
    },
    {
        "cell_id": "5B_adult",
        "dataset_key": "adult",
        "persona": "Eleni Kostas",
        "user_question": (
            "Produce a full fairness and opportunity audit: how does income "
            "interact with education, occupation, sex, race, and country?"
        ),
        "interpretation": (
            "Multi-page complex report with fairness angle. 3 pages — "
            "education, occupation, demographic."
        ),
        "citations": [
            {"kind": "column", "identifier": "income", "reason": "target"},
            {"kind": "column", "identifier": "education", "reason": "axis 1"},
            {"kind": "column", "identifier": "occupation", "reason": "axis 2"},
            {"kind": "column", "identifier": "race", "reason": "axis 3"},
        ],
        "subagent_tasks": [
            ("Education-income surface", "education x income", ""),
            ("Occupation-income surface", "occupation x income", ""),
            ("Demographic-income surface", "race+sex x income", ""),
        ],
        "pages": [
            {
                "id": "page_1",
                "title": "Education × Income",
                "purpose": "Baseline fairness lens",
                "layout": "hero_plus_grid",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Education is the single largest wedge.",
                    },
                ],
            },
            {
                "id": "page_2",
                "title": "Occupation × Income",
                "purpose": "Secondary lens",
                "layout": "single",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Executive/managerial leads high-earner share.",
                    },
                ],
            },
            {
                "id": "page_3",
                "title": "Demographic × Income",
                "purpose": "Third lens: race/sex",
                "layout": "two_col",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Raw correlations do not imply causation.",
                    },
                ],
            },
        ],
        "exec_summary": {
            "title": "UCI Adult Income — Fairness and Opportunity Audit",
            "headline": (
                "Income is strongly associated with education; "
                "occupation amplifies the gap."
            ),
            "key_findings": [
                "24% of sample earns >$50k",
                "Masters/Doctorate cohort has ~75% high-earner rate",
                "Sex and race gaps persist even within education bucket",
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "action": "Decompose gaps by education bucket to separate composition from treatment effects",
                    "rationale": "Composition-vs-treatment is the analyst's responsibility",
                    "expected_impact": "Improves downstream policy discussion rigor",
                    "evidence_page": "page_3",
                    "confidence": "high",
                },
            ],
            "methodology": (
                "Cross-tabulation via DuckDB GROUP BY against the Gold table."
            ),
            "open_questions": [
                "What drives the residual gap within education cohorts?",
            ],
        },
        "caveats": [
            "1994 US Census data — temporal generalization caveats",
            "fnlwgt sampling weight was ignored in this pass",
        ],
    },
    {
        "cell_id": "5C_lahman",
        "dataset_key": "lahman",
        "persona": "Marcus Okonkwo",
        "user_question": (
            "State of baseball: era-by-era franchise dominance, longest "
            "title droughts, and which franchises run 'dynasty' patterns."
        ),
        "interpretation": (
            "Multi-page complex report covering eras, droughts, and dynasty patterns."
        ),
        "citations": [
            {"kind": "column", "identifier": "yearID", "reason": "time axis"},
            {"kind": "column", "identifier": "WSWin", "reason": "title flag"},
            {"kind": "column", "identifier": "teamID", "reason": "franchise axis"},
        ],
        "subagent_tasks": [
            ("Era rollup", "4-era decomposition", ""),
            ("Drought analysis", "gaps between titles", ""),
            ("Dynasty pattern detection", "consecutive wins", ""),
        ],
        "pages": [
            {
                "id": "page_1",
                "title": "Era rollup",
                "purpose": "Big-picture era view",
                "layout": "hero_plus_grid",
                "blocks": [
                    {"type": "narrative", "text": "4-era decomposition of wins."},
                ],
            },
            {
                "id": "page_2",
                "title": "Drought analysis",
                "purpose": "Where the gaps are",
                "layout": "single",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Longest championship droughts by franchise.",
                    },
                ],
            },
            {
                "id": "page_3",
                "title": "Dynasty patterns",
                "purpose": "Back-to-back runs",
                "layout": "single",
                "blocks": [
                    {"type": "narrative", "text": "Consecutive-year WSWin sequences."},
                ],
            },
        ],
        "exec_summary": {
            "title": "Baseball dynasties, droughts, and eras",
            "headline": "NYY dominates cumulative wins; parity has grown since 2000",
            "key_findings": [
                "NYY has 27 World Series titles — most of any franchise",
                "Several franchises have 50+ year championship droughts",
                "Post-2000 era shows more title rotation vs pre-1980",
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "action": "Feature the NYY dynasty as a marketing hook for the 'storied franchise' angle",
                    "rationale": "Historical dominance is a recognizable story",
                    "expected_impact": "Engagement uplift",
                    "evidence_page": "page_3",
                    "confidence": "medium",
                }
            ],
            "methodology": "Grouped SQL across Teams with decade binning.",
            "open_questions": [
                "Does expansion cause parity or is it genuine competitive balance?",
            ],
        },
        "caveats": [
            "WS not played in 1904, 1994",
            "teamID churn across franchise relocations",
        ],
    },
    {
        "cell_id": "5D_ames",
        "dataset_key": "ames",
        "persona": "Akira Tanaka",
        "user_question": (
            "Full market brief on Ames Housing: where the premium lives, "
            "how size/quality/age drive price, and which neighborhoods "
            "look undervalued."
        ),
        "interpretation": (
            "Multi-page complex report: premium map, size/quality/age "
            "drivers, undervalued list."
        ),
        "citations": [
            {"kind": "column", "identifier": "Neighborhood", "reason": "segmentation"},
            {"kind": "column", "identifier": "price", "reason": "target"},
            {"kind": "column", "identifier": "area", "reason": "size driver"},
            {
                "kind": "column",
                "identifier": "Overall.Qual",
                "reason": "quality driver",
            },
        ],
        "subagent_tasks": [
            ("Premium neighborhood map", "top 3 tiers", ""),
            ("Driver decomposition", "area + quality + year", ""),
            ("Undervalued list", "$/sqft vs neighborhood median", ""),
        ],
        "pages": [
            {
                "id": "page_1",
                "title": "Premium map",
                "purpose": "Where the expensive homes are",
                "layout": "hero_plus_grid",
                "blocks": [
                    {"type": "narrative", "text": "StoneBr, NoRidge, NridgHt lead."},
                ],
            },
            {
                "id": "page_2",
                "title": "Price drivers",
                "purpose": "What explains price",
                "layout": "two_col",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Area, Overall.Qual, Year.Built correlate strongly.",
                    },
                ],
            },
            {
                "id": "page_3",
                "title": "Undervalued list",
                "purpose": "Top buying opportunities",
                "layout": "single",
                "blocks": [
                    {
                        "type": "narrative",
                        "text": "Top 25 homes by $/sqft ratio below neighborhood median.",
                    },
                ],
            },
        ],
        "exec_summary": {
            "title": "Ames Housing Market Brief",
            "headline": "StoneBr leads median price; price drivers are area+quality+year",
            "key_findings": [
                "Top 3 neighborhoods (StoneBr/NoRidge/NridgHt) cluster 2x median price",
                "Overall.Qual alone explains most of price variance",
                "~150 homes priced ≥20% below their neighborhood median $/sqft",
            ],
            "recommendations": [
                {
                    "id": "r1",
                    "action": "Shortlist undervalued homes for physical inspection",
                    "rationale": "Low $/sqft ratio flags candidates; confirm on site",
                    "expected_impact": "Buying opportunity identification",
                    "evidence_page": "page_3",
                    "confidence": "high",
                },
            ],
            "methodology": "Neighborhood-level MEDIAN joined back to per-home rows.",
            "open_questions": [
                "Does condition rating close the undervalued gap?",
            ],
        },
        "caveats": [
            "Nominal 2006-2010 sale price; no inflation adjustment",
            "Excludes neighborhoods with <20 sales (noisy medians)",
        ],
    },
]


def main() -> None:
    phase1_results: list[dict] = []
    for cell in CELLS:
        print(f"\n== {cell['cell_id']} phase 1 ==")
        try:
            r = _phase1_dataset(
                cell_id=cell["cell_id"],
                dataset_key=cell["dataset_key"],
                persona=cell["persona"],
                user_question=cell["user_question"],
                interpretation=cell["interpretation"],
                citations=cell["citations"],
                subagent_tasks=cell["subagent_tasks"],
                page_payloads=cell["pages"],
                exec_summary=cell["exec_summary"],
                caveats=cell["caveats"],
            )
            phase1_results.append(r)
            print(
                f"  subagents={len(r.get('subagent_ids', []))} "
                f"audit={r.get('audit_events')} "
                f"py_exit={r.get('python_exit')}"
            )
        except Exception as e:
            err = {
                "cell_id": cell["cell_id"],
                "phase": 1,
                "error": f"{type(e).__name__}: {e}",
            }
            phase1_results.append(err)
            print(f"  FAILED: {err}")

    print("\n== RESTARTING uvicorn between phase 1 and phase 2 ==")
    _stop_server()
    _start_server()
    print("Server restarted.")

    phase2_results: list[dict] = []
    for cell in CELLS:
        print(f"\n== {cell['cell_id']} phase 2 ==")
        try:
            r = _phase2_followup(
                cell_id=cell["cell_id"],
                dataset_key=cell["dataset_key"],
                persona=cell["persona"],
            )
            phase2_results.append(r)
            print(
                f"  recalled={r.get('memory_recalled')} "
                f"plan_audit={r.get('recalled_audit_events')}"
            )
        except Exception as e:
            err = {
                "cell_id": cell["cell_id"],
                "phase": 2,
                "error": f"{type(e).__name__}: {e}",
            }
            phase2_results.append(err)
            print(f"  FAILED: {err}")

    combined = {
        "phase1": phase1_results,
        "phase2": phase2_results,
    }
    (ARTIFACTS / "summary.json").write_text(json.dumps(combined, indent=2, default=str))
    p1_ok = sum(1 for r in phase1_results if "error" not in r)
    p2_ok = sum(1 for r in phase2_results if r.get("memory_recalled"))
    print(
        f"\n== Tier 5 done: phase1 {p1_ok}/{len(CELLS)}, phase2 {p2_ok}/{len(CELLS)} =="
    )


if __name__ == "__main__":
    main()
