"""Bootstrap a dev org + admin member so the API has something to serve.

Run once after `docker compose up postgres`:

    uv run python -m manthan_api.scripts.bootstrap_dev_org

Idempotent - re-running detects the existing org and skips.
"""

from __future__ import annotations

import asyncio
import json

from manthan_api.db import close_pool, get_conn, init_pool


DEV_ORG_SLUG = "acme"
DEV_ORG_NAME = "Acme (dev)"
DEV_ADMIN_EMAIL = "you@miny-labs.com"
DEV_ADMIN_NAME = "Dev Admin"


async def main() -> None:
    await init_pool()
    try:
        async with get_conn() as conn:
            org_row = await conn.fetchrow(
                "SELECT id FROM orgs WHERE slug = $1",
                DEV_ORG_SLUG,
            )
            if org_row:
                print(f"org already exists: {DEV_ORG_SLUG} ({org_row['id']})")
                org_id = org_row["id"]
            else:
                org_row = await conn.fetchrow(
                    """
                    INSERT INTO orgs (slug, name, plan)
                    VALUES ($1, $2, 'design_partner')
                    RETURNING id
                    """,
                    DEV_ORG_SLUG,
                    DEV_ORG_NAME,
                )
                org_id = org_row["id"]
                print(f"created org: {DEV_ORG_SLUG} ({org_id})")

            member_row = await conn.fetchrow(
                "SELECT id FROM members WHERE org_id = $1 AND email = $2",
                org_id,
                DEV_ADMIN_EMAIL,
            )
            if member_row:
                print(f"member already exists: {DEV_ADMIN_EMAIL} ({member_row['id']})")
            else:
                member_row = await conn.fetchrow(
                    """
                    INSERT INTO members (org_id, email, name, role, approval_limit_minor)
                    VALUES ($1, $2, $3, 'admin', 100000000)
                    RETURNING id
                    """,
                    org_id,
                    DEV_ADMIN_EMAIL,
                    DEV_ADMIN_NAME,
                )
                print(f"created admin member: {DEV_ADMIN_EMAIL} ({member_row['id']})")

            # Optional: insert one sample case so the UI has something to render.
            existing_case = await conn.fetchval(
                "SELECT COUNT(*) FROM cases WHERE org_id = $1",
                org_id,
            )
            if existing_case == 0:
                import uuid

                thread_id = uuid.uuid4()
                case_row = await conn.fetchrow(
                    """
                    INSERT INTO cases (
                        org_id, thread_id, short_id, status, trigger_surface,
                        trigger_payload, case_type, customer_ref,
                        amount_minor, currency,
                        decision_action, decision_amount_minor, decision_confidence
                    )
                    VALUES ($1, $2, 'CASE-4821', 'awaiting_approval', 'stripe_webhook',
                            $3, 'chargeback', 'TechCorp Industries',
                            120000, 'usd',
                            'refund', 120000, 0.92)
                    RETURNING id
                    """,
                    org_id,
                    thread_id,
                    json.dumps({"sample": True}),
                )
                await conn.execute(
                    """
                    INSERT INTO events (org_id, thread_id, seq, type, actor, data)
                    VALUES ($1, $2, 1, 'case_opened', 'system', $3)
                    """,
                    org_id,
                    thread_id,
                    json.dumps({"sample": True, "short_id": "CASE-4821"}),
                )
                await conn.execute(
                    """
                    INSERT INTO findings (org_id, case_id, seq, text, confidence, citations)
                    VALUES
                      ($1, $2, 1,
                       'TechCorp account healthy: NPS 9, plan Growth Annual, no prior disputes in 14 months.',
                       0.95, $3::jsonb),
                      ($1, $2, 2,
                       'Last support conversation 14 days ago - unrelated onboarding question, resolved.',
                       0.88, $4::jsonb),
                      ($1, $2, 3,
                       'Amount $1,200 exceeds $500 auto-refund threshold per refunds.yaml - held for approval.',
                       0.99, $5::jsonb)
                    """,
                    org_id,
                    case_row["id"],
                    json.dumps([
                        {"source": "salesforce", "table": "accounts", "ref": "001xxx", "field": "Health__c"},
                        {"source": "stripe", "table": "customers", "ref": "cus_xxx", "field": "metadata.disputes_14mo"},
                    ]),
                    json.dumps([
                        {"source": "zendesk", "table": "tickets", "ref": "8412", "field": "status"},
                    ]),
                    json.dumps([
                        {"source": "notion", "table": "pages", "ref": "refunds.yaml", "field": "threshold"},
                    ]),
                )
                print(f"seeded sample case: CASE-4821 ({case_row['id']})")
            else:
                print(f"dev org already has {existing_case} case(s) - skipping sample seed")

        print()
        print("done. start the API with:")
        print("  uv run uvicorn manthan_api.main:app --reload --port 8000")
        print()
        print("then test:")
        print(f"  curl -H 'X-Manthan-Dev-Org: {DEV_ORG_SLUG}' http://localhost:8000/api/cases")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
