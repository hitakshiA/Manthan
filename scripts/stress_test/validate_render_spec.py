"""Layer 3 render_spec validator.

Walks every ``render_spec.json`` / ``phase*_report.json`` under
``docs/stress_test_artifacts/tier*/`` and checks mode-specific required
fields. Reports a machine-readable JSON summary plus a text table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARTIFACTS = Path("docs/stress_test_artifacts")


def _validate_simple(spec: dict) -> list[str]:
    errors: list[str] = []
    if spec.get("mode") != "simple":
        errors.append("mode != simple")
    if "headline" not in spec:
        errors.append("missing headline")
    elif not isinstance(spec.get("headline"), dict):
        errors.append("headline is not a dict")
    else:
        hl = spec["headline"]
        if "value" not in hl or "label" not in hl:
            errors.append("headline missing value/label")
    if not isinstance(spec.get("narrative"), str):
        errors.append("narrative missing or not a string")
    visuals = spec.get("visuals") or []
    if not isinstance(visuals, list) or not (1 <= len(visuals) <= 3):
        errors.append(f"visuals count out of 1..3: {len(visuals)}")
    for i, v in enumerate(visuals):
        if not isinstance(v, dict):
            errors.append(f"visual[{i}] not dict")
            continue
        for req in ("id", "type", "title"):
            if req not in v:
                errors.append(f"visual[{i}] missing {req}")
    citations = spec.get("citations") or []
    if not isinstance(citations, list) or len(citations) == 0:
        errors.append("citations missing or empty")
    return errors


def _validate_moderate(spec: dict) -> list[str]:
    errors: list[str] = []
    if spec.get("mode") != "moderate":
        errors.append("mode != moderate")
    for req in ("title", "kpi_row", "sections"):
        if req not in spec:
            errors.append(f"missing {req}")
    kpis = spec.get("kpi_row") or []
    if not isinstance(kpis, list) or len(kpis) < 2:
        errors.append(f"kpi_row must have ≥2 cards, got {len(kpis)}")
    sections = spec.get("sections") or []
    if not isinstance(sections, list) or len(sections) < 3:
        errors.append(f"sections must have ≥3, got {len(sections)}")
    else:
        has_multi_col = False
        for i, section in enumerate(sections):
            if not isinstance(section, dict):
                errors.append(f"section[{i}] not dict")
                continue
            for req in ("title", "narrative", "layout", "visuals"):
                if req not in section:
                    errors.append(f"section[{i}] missing {req}")
            if section.get("layout") in ("two_col", "three_col"):
                has_multi_col = True
            # Placeholder titles like "Section 1" are NOT story-arc titles
            if section.get("title", "").lower().startswith("section "):
                errors.append(f"section[{i}] has placeholder title")
        if not has_multi_col:
            errors.append("no multi-column layout section found")
    citations = spec.get("citations") or []
    if not isinstance(citations, list) or len(citations) == 0:
        errors.append("citations missing or empty")
    if "plan_id" not in spec:
        errors.append("plan_id missing (no plan linkage)")
    return errors


def _validate_complex(spec: dict) -> list[str]:
    errors: list[str] = []
    if spec.get("mode") != "complex":
        errors.append("mode != complex")
    for req in ("report_title", "executive_summary", "pages", "appendix"):
        if req not in spec:
            errors.append(f"missing {req}")
    exec_summary = spec.get("executive_summary") or {}
    if not isinstance(exec_summary, dict):
        errors.append("executive_summary not a dict")
    else:
        key_findings = exec_summary.get("key_findings") or []
        if not isinstance(key_findings, list) or len(key_findings) < 2:
            errors.append(
                f"executive_summary.key_findings must have ≥2, got {len(key_findings)}"
            )
        recs = exec_summary.get("recommendations") or []
        if not isinstance(recs, list) or len(recs) == 0:
            errors.append("executive_summary.recommendations missing or empty")
    pages = spec.get("pages") or []
    if not isinstance(pages, list) or len(pages) < 1:
        errors.append(f"pages must have ≥1, got {len(pages)}")
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            errors.append(f"page[{i}] not dict")
            continue
        for req in ("id", "title", "purpose", "layout", "blocks"):
            if req not in page:
                errors.append(f"page[{i}] missing {req}")
    appendix = spec.get("appendix") or {}
    if not isinstance(appendix, dict):
        errors.append("appendix not a dict")
    else:
        for req in ("methodology", "data_quality_notes", "open_questions"):
            if req not in appendix:
                errors.append(f"appendix missing {req}")
    if "memory_refs" not in spec:
        errors.append("memory_refs missing")
    if spec.get("phase") == 2 and not spec.get("memory_refs"):
        errors.append("phase=2 must cite phase-1 via memory_refs")
    return errors


def _validate_spec(path: Path, spec: dict) -> dict:
    mode = spec.get("mode")
    if mode == "simple":
        errors = _validate_simple(spec)
    elif mode == "moderate":
        errors = _validate_moderate(spec)
    elif mode == "complex":
        errors = _validate_complex(spec)
    else:
        errors = [f"unknown mode: {mode}"]
    return {
        "path": str(path.relative_to(Path.cwd())) if path.is_absolute() else str(path),
        "mode": mode,
        "passed": len(errors) == 0,
        "errors": errors,
    }


def main() -> int:
    results: list[dict] = []
    for tier_dir in sorted(ARTIFACTS.glob("tier*")):
        for files_dir in sorted(tier_dir.glob("*_files")):
            for spec_path in sorted(files_dir.glob("*.json")):
                if spec_path.name not in (
                    "render_spec.json",
                    "phase1_report.json",
                    "phase2_report.json",
                ):
                    continue
                try:
                    spec = json.loads(spec_path.read_text())
                except Exception as exc:
                    results.append(
                        {
                            "path": str(spec_path),
                            "mode": None,
                            "passed": False,
                            "errors": [f"JSON parse error: {exc}"],
                        }
                    )
                    continue
                results.append(_validate_spec(spec_path, spec))

    (ARTIFACTS / "layer3_validation.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    total = len(results)
    ok = sum(1 for r in results if r["passed"])
    print(f"Validated {total} render specs: {ok} passed, {total - ok} failed")
    print()
    print(f"{'PATH':70s} {'MODE':10s} {'STATUS':10s}")
    print("-" * 90)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{r['path'][:70]:70s} {(r['mode'] or '?'):10s} {status}")
        if not r["passed"]:
            for err in r["errors"]:
                print(f"   - {err}")

    return 0 if total == ok else 1


if __name__ == "__main__":
    sys.exit(main())
