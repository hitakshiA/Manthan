"""Seed a local SQLite database with the synthetic NexaRetail dataset.

Generates the CSV if needed (via :mod:`generate_demo_data`), then
materializes an ``orders`` table in ``data/nexaretail.db`` so you can
exercise the ``/datasets/connect`` endpoint against a real local DB.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from scripts.generate_demo_data import generate as generate_demo


def seed(
    *,
    csv_path: Path,
    db_path: Path,
    rows: int,
    seed: int,
) -> None:
    """Regenerate the demo CSV and seed it into a SQLite ``orders`` table."""
    generate_demo(csv_path, rows=rows, seed=seed)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        with csv_path.open() as fh:
            reader = csv.reader(fh)
            header = next(reader)
            columns_sql = ", ".join(f"{col} TEXT" for col in header)
            con.execute(f"CREATE TABLE orders ({columns_sql})")
            placeholders = ", ".join("?" for _ in header)
            con.executemany(
                f"INSERT INTO orders VALUES ({placeholders})",
                list(reader),
            )
        con.commit()
    finally:
        con.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/nexaretail_sales.csv"))
    parser.add_argument("--db", type=Path, default=Path("data/nexaretail.db"))
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    seed(csv_path=args.csv, db_path=args.db, rows=args.rows, seed=args.seed)
    print(f"Seeded {args.rows} rows into {args.db} (orders table)")


if __name__ == "__main__":
    main()
