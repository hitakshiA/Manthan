"""Trigger W1R / W2R / W3R as real cases in the dev org.

Loads the trigger text from agent/scripts/real_workflows.py and inserts
each as a case_opened event. The worker picks them up via PG NOTIFY and
runs the agent against live Coral.

Usage:
    uv run python -m manthan_api.scripts.trigger_demo_cases
    uv run python -m manthan_api.scripts.trigger_demo_cases --only W1R
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Pull the workflows from the agent scripts dir.
AGENT_SCRIPTS = Path(__file__).resolve().parents[4] / "agent" / "scripts"
sys.path.insert(0, str(AGENT_SCRIPTS))

from real_workflows import WORKFLOWS_REAL  # noqa: E402

from manthan_api.db import close_pool, get_conn, init_pool  # noqa: E402


CASE_TYPE_FROM_PATTERN = {
    "daisy_chained_chargebacks_real": "chargeback",
    "failed_webhook_ghost_real": "chargeback",
    "post_acquisition_double_real": "chargeback",
    "zendesk_sla_breach_real": "refund_request",
    "posthog_usage_fraud_real": "refund_request",
    "auth_outage_refund_real": "refund_request",
    "documented_incident_prorata_real": "chargeback",
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="acme")
    parser.add_argument(
        "--only",
        help="comma-separated case_id prefixes (W1R, W2R, …); default all",
    )
    parser.add_argument(
        "--wipe-placeholder",
        action="store_true",
        help="Delete the seeded CASE-4821 placeholder before inserting.",
    )
    args = parser.parse_args()

    await init_pool()
    try:
        async with get_conn() as conn:
            org = await conn.fetchrow(
                "SELECT id FROM orgs WHERE slug = $1",
                args.org,
            )
            if not org:
                print(f"org not found: {args.org}")
                return
            org_id = org["id"]

            if args.wipe_placeholder:
                # Delete the sample seeded case
                deleted = await conn.execute(
                    """
                    DELETE FROM cases
                    WHERE org_id=$1 AND trigger_payload::text LIKE '%"sample": true%'
                    """,
                    org_id,
                )
                print(f"wiped placeholder: {deleted}")

            only_set = (
                {s.strip() for s in args.only.split(",")}
                if args.only
                else None
            )

            for wf in WORKFLOWS_REAL:
                key = wf.case_id.split("-")[0]  # W1R / W2R / ...
                if only_set and key not in only_set:
                    continue

                # Check if a case with this short_id already exists; skip if so
                # (idempotency for repeat runs).
                short_id = wf.case_id.upper()
                existing = await conn.fetchval(
                    "SELECT id FROM cases WHERE org_id=$1 AND short_id=$2",
                    org_id, short_id,
                )
                if existing:
                    print(f"skip (already exists): {short_id}")
                    continue

                thread_id = uuid.uuid4()
                case_type = CASE_TYPE_FROM_PATTERN.get(wf.pattern_name, "chargeback")
                case_row = await conn.fetchrow(
                    """
                    INSERT INTO cases (
                        org_id, thread_id, short_id, status, trigger_surface,
                        trigger_payload, case_type, customer_ref,
                        amount_minor, currency
                    )
                    VALUES ($1, $2, $3, 'investigating', 'api',
                            $4, $5, $6, $7, 'usd')
                    RETURNING id
                    """,
                    org_id, thread_id, short_id,
                    json.dumps({
                        "trigger_text": wf.trigger_text,
                        "case_type": case_type,
                        "pattern_name": wf.pattern_name,
                        "expected_decision": wf.expected_decision,
                    }),
                    case_type,
                    _customer_from_trigger(wf.trigger_text),
                    wf.expected_amount_minor,
                )
                await conn.execute(
                    """
                    INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                    VALUES ($1, $2, 1, 'case_opened', 'human:operator', $3)
                    """,
                    org_id, thread_id,
                    {
                        "case_id": str(case_row["id"]),
                        "short_id": short_id,
                        "trigger_surface": "api",
                        "trigger_text": wf.trigger_text,
                        "case_type": case_type,
                        "pattern_name": wf.pattern_name,
                    },
                )
                print(f"triggered {short_id} → case_id={case_row['id']} thread={thread_id}")

    finally:
        await close_pool()


def _customer_from_trigger(text: str) -> str | None:
    """Pull 'Customer: ...' out of the trigger line, best-effort."""
    for line in text.splitlines():
        if line.startswith("Customer:"):
            tail = line[len("Customer:"):].strip()
            return tail.split("(")[0].strip()
    return None


if __name__ == "__main__":
    asyncio.run(main())
