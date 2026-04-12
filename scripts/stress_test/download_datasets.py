"""Download the 4 real public datasets for the Layer 1 stress test.

All datasets pulled from unauthenticated public mirrors. Each download is
idempotent — existing non-empty targets are skipped.

Datasets (all probed and confirmed 200 OK before committing):
    A. NYC Yellow Taxi Jan 2024 — Parquet, ~2.9M rows × 19 cols
       Source: cloudfront.net (NYC TLC official)
    B. UCI Adult Census — CSV, ~48k rows × 15 cols
       Source: jbrownlee/Datasets GitHub (archive.ics.uci.edu is 502ing)
    C. Lahman Baseball Database — SQLite → 10 CSVs, multi-file relational
       Source: WebucatorTraining/lahman-baseball-mysql raw SQLite file
       Exports: People, Teams, Batting, Pitching, Fielding, AllstarFull,
                Salaries, Managers, AwardsPlayers, HallOfFame
    D. Ames Housing — CSV, 2930 rows × 82 cols (wide-schema stress)
       Source: openintro.org official CSV host
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
STRESS_DIR = ROOT / "data" / "stress_test"

_ADULT_HEADER = (
    "age,workclass,fnlwgt,education,education_num,marital_status,"
    "occupation,relationship,race,sex,capital_gain,capital_loss,"
    "hours_per_week,native_country,income"
)

_LAHMAN_TABLES = [
    "People",
    "Teams",
    "Batting",
    "Pitching",
    "Fielding",
    "AllstarFull",
    "Salaries",
    "Managers",
    "AwardsPlayers",
    "HallOfFame",
]


@dataclass
class Download:
    name: str
    url: str
    relative_path: str
    note: str = ""


DOWNLOADS: list[Download] = [
    Download(
        name="NYC Yellow Taxi Jan 2024",
        url=(
            "https://d37ci6vzurychx.cloudfront.net/trip-data/"
            "yellow_tripdata_2024-01.parquet"
        ),
        relative_path="taxi/yellow_tripdata_2024-01.parquet",
        note="~50 MB, 2.9M rows, 19 cols (Parquet)",
    ),
    Download(
        name="UCI Adult Census (headerless)",
        url="https://raw.githubusercontent.com/jbrownlee/Datasets/master/adult-all.csv",
        relative_path="adult/adult_raw.csv",
        note="48k rows, 15 cols — header will be prepended",
    ),
    Download(
        name="Lahman Baseball SQLite",
        url=(
            "https://raw.githubusercontent.com/WebucatorTraining/"
            "lahman-baseball-mysql/master/lahmansbaseballdb.sqlite"
        ),
        relative_path="lahman/lahmansbaseballdb.sqlite",
        note="SQLite — will be exploded into 10 CSVs",
    ),
    Download(
        name="Ames Housing",
        url="https://www.openintro.org/data/csv/ames.csv",
        relative_path="ames/ames.csv",
        note="2930 rows × 82 cols — wide-schema stress",
    ),
]


def _download_one(client: httpx.Client, d: Download) -> tuple[bool, str]:
    target = STRESS_DIR / d.relative_path
    if target.exists() and target.stat().st_size > 0:
        return True, f"exists ({target.stat().st_size // 1024} KB)"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = client.get(d.url, follow_redirects=True)
        r.raise_for_status()
        target.write_bytes(r.content)
        return True, f"ok ({len(r.content) // 1024} KB)"
    except httpx.HTTPError as exc:
        return False, f"FAIL: {exc}"


def _postprocess_adult() -> None:
    raw = STRESS_DIR / "adult/adult_raw.csv"
    out = STRESS_DIR / "adult/adult.csv"
    if not raw.exists() or out.exists():
        return
    text = raw.read_text()
    lines = [line.strip().rstrip(".") for line in text.splitlines() if line.strip()]
    # adult-all.csv from jbrownlee is already headerless; prepend header
    with out.open("w") as f:
        f.write(_ADULT_HEADER + "\n")
        f.write("\n".join(lines) + "\n")
    print(f"  [POST] adult/adult.csv ({len(lines)} rows)")


def _postprocess_lahman() -> None:
    sqlite_path = STRESS_DIR / "lahman/lahmansbaseballdb.sqlite"
    if not sqlite_path.exists():
        return
    out_dir = STRESS_DIR / "lahman/csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path))
    try:
        # Discover available tables case-insensitively
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        available = {r[0].lower(): r[0] for r in rows}
        for table in _LAHMAN_TABLES:
            actual = available.get(table.lower())
            if actual is None:
                print(f"  [WARN] Lahman table '{table}' not present in SQLite")
                continue
            csv_path = out_dir / f"{table}.csv"
            if csv_path.exists() and csv_path.stat().st_size > 0:
                continue
            cursor = conn.execute(f'SELECT * FROM "{actual}"')
            cols = [desc[0] for desc in cursor.description]
            import csv

            with csv_path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(cols)
                writer.writerows(cursor)
            print(
                f"  [POST] lahman/csv/{table}.csv "
                f"({csv_path.stat().st_size // 1024} KB)"
            )
    finally:
        conn.close()


def main() -> int:
    print(f"Downloading to {STRESS_DIR}")
    STRESS_DIR.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, bool, str]] = []
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        for d in DOWNLOADS:
            ok, msg = _download_one(client, d)
            results.append((d.name, ok, msg))
            status = "OK" if ok else "FAIL"
            print(f"  [{status:4s}] {d.name:40s} {msg}")

    _postprocess_adult()
    _postprocess_lahman()

    failures = [r for r in results if not r[1]]
    if failures:
        print(f"\n{len(failures)} download(s) failed — aborting")
        return 1

    print(f"\nFiles under {STRESS_DIR}:")
    for path in sorted(STRESS_DIR.rglob("*")):
        if path.is_file():
            size_kb = path.stat().st_size // 1024
            print(f"  {path.relative_to(STRESS_DIR)} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
