"""Generate a synthetic NexaRetail dataset for demos and testing.

Produces ``data/nexaretail_sales.csv`` with 500 rows of fake but
realistic-looking e-commerce transactions. All names, emails, and
product SKUs are synthetic — no real PII — so the file is safe to
check in or share.

Run with: ``python scripts/generate_demo_data.py``
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

_REGIONS = ["North", "South", "East", "West"]
_CHANNELS = ["Online", "Retail Store", "Mobile App", "Partner"]
_CUSTOMER_SEGMENTS = ["Retail", "Wholesale", "Enterprise"]
_PRODUCT_CATEGORIES = [
    "Electronics",
    "Apparel",
    "Home & Kitchen",
    "Books",
    "Toys",
    "Sports",
    "Beauty",
]
_FIRST_NAMES = [
    "Alex",
    "Bailey",
    "Casey",
    "Dana",
    "Eden",
    "Francis",
    "Gray",
    "Harper",
    "Indigo",
    "Jordan",
    "Kai",
    "Lane",
    "Morgan",
    "Nova",
    "Ollie",
]
_LAST_NAMES = [
    "Example",
    "Sample",
    "Testcase",
    "Demo",
    "Placeholder",
    "Synthetic",
    "Fictional",
    "Pseudo",
    "Mock",
    "Dummy",
]


def generate(output: Path, *, rows: int = 500, seed: int = 42) -> None:
    """Write ``rows`` rows of synthetic sales data to ``output``."""
    rng = random.Random(seed)
    start = date(2024, 1, 1)
    end = date(2025, 3, 31)
    day_span = (end - start).days

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "order_id",
                "order_date",
                "region",
                "channel",
                "product_category",
                "product_sku",
                "quantity",
                "unit_price",
                "revenue",
                "customer_segment",
                "customer_name",
                "customer_email",
            ]
        )
        for order_id in range(1, rows + 1):
            order_date = start + timedelta(days=rng.randint(0, day_span))
            region = rng.choice(_REGIONS)
            channel = rng.choice(_CHANNELS)
            category = rng.choice(_PRODUCT_CATEGORIES)
            sku = f"SKU-{category[:3].upper()}-{rng.randint(1000, 9999)}"
            quantity = rng.randint(1, 6)
            unit_price = round(rng.uniform(9.99, 499.99), 2)
            revenue = round(unit_price * quantity, 2)
            segment = rng.choice(_CUSTOMER_SEGMENTS)
            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)
            name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}@example.com"
            writer.writerow(
                [
                    f"ORD-{order_id:06d}",
                    order_date.isoformat(),
                    region,
                    channel,
                    category,
                    sku,
                    quantity,
                    unit_price,
                    revenue,
                    segment,
                    name,
                    email,
                ]
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "nexaretail_sales.csv",
        help="Where to write the CSV.",
    )
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    generate(args.output, rows=args.rows, seed=args.seed)
    print(f"Wrote {args.rows} synthetic rows to {args.output}")


if __name__ == "__main__":
    main()
