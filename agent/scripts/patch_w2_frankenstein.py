"""Patch W2 - "Frankenstein customer" for the Manthan v2 agent.

Saga Foods has fractured identity:
  * Stripe: 1 legit customer  (legit annual / standard sub)
            + 1 ORPHAN customer "Saga Foods Inc" with 2 monthly $7,000
              charges in April + May 2026 (this patch creates them).
  * HubSpot: 1 legit company "Saga Foods"
             + 1 DUPLICATE company "Saga Foods Inc" (this patch creates).
  * Salesforce: 1 account "Saga Foods" with the Closed-Won opportunity
                (the ground truth - untouched by this patch).

The Manthan v2 agent should reconcile Stripe + HubSpot against
Salesforce-as-ground-truth and recommend refunding the $14,000 of
orphan monthly charges (2 × $7,000).

Idempotent: searches for the orphan before creating. If the orphan
exists, just verifies the April + May charges are present and creates
any that are missing.

Reuses helpers from seed_stripe.py and seed_hubspot.py.

Run:
    .venv/bin/python scripts/patch_w2_frankenstein.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Make seed_stripe / seed_hubspot importable.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv  # noqa: E402

AGENT = SCRIPT_DIR.parent
load_dotenv(AGENT / ".env")

import httpx  # noqa: E402
import stripe  # noqa: E402

from seed_stripe import idem, md_dict, safe_create  # noqa: E402
from seed_hubspot import HEADERS, REQ_SLEEP, TIMEOUT, _request  # noqa: E402

stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")


# ──────────────────────────────────────────────────────────────────────
# Constants - orphan identity + amounts
# ──────────────────────────────────────────────────────────────────────

ORPHAN_NAME = "Saga Foods Inc"          # note the "Inc" - diff from legit
ORPHAN_EMAIL = "signup-noreply@saga-foods.test"
ORPHAN_DESCRIPTION = (
    "Created via marketing landing page signup form. "
    "Possible duplicate - investigate."
)
ORPHAN_METADATA: dict[str, str] = {
    "source": "marketing_form",
    "duplicate_suspect": "true",
    "company_slug": "saga-foods",
    "workflow": "W2_frankenstein",
    "seeded_by": "manthan_patch_w2_frankenstein",
    "ground_truth_source": "salesforce",
    "legit_stripe_customer_hint": "search name='Saga Foods' (no Inc)",
}

ORPHAN_PRODUCT_NAME = "Manthan Demo - Monthly Starter (orphan)"
ORPHAN_PRICE_AMOUNT = 7_000_00  # $7,000 / month in minor units
ORPHAN_PRICE_INTERVAL = "month"

# Monthly orphan charge plan: (label, idem_suffix, sim_date).
ORPHAN_CHARGE_PLAN = [
    ("Monthly subscription - April 2026", "orphan-apr-2026", "2026-04-15"),
    ("Monthly subscription - May 2026",   "orphan-may-2026", "2026-05-15"),
]

ORPHAN_HUBSPOT_DOMAIN = "signup.saga-foods.test"


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────


def log(msg: str = "") -> None:
    print(msg, flush=True)


# ──────────────────────────────────────────────────────────────────────
# Stripe - orphan customer + product/price + subscription + charges
# ──────────────────────────────────────────────────────────────────────


def find_legit_saga_customer() -> stripe.Customer | None:
    """Resolve the legit Saga Foods customer for sanity-check."""
    # Try metadata-slug first (most precise).
    try:
        for c in stripe.Customer.search(
            query="metadata['slug']:'saga-foods'"
        ).data:
            if (c.name or "").strip().lower() == "saga foods":
                return c
    except stripe.error.StripeError:
        pass
    # Fall back to exact-name search.
    try:
        for c in stripe.Customer.search(query="name:'Saga Foods'").data:
            if (c.name or "").strip().lower() == "saga foods":
                return c
    except stripe.error.StripeError:
        pass
    return None


def find_orphan_customer() -> stripe.Customer | None:
    """Idempotency check: did a previous run already create the orphan?"""
    # Match by the exact email since it's unique to the orphan.
    try:
        for c in stripe.Customer.search(
            query=f"email:'{ORPHAN_EMAIL}'"
        ).data:
            if (c.name or "").strip() == ORPHAN_NAME:
                return c
    except stripe.error.StripeError:
        pass
    # Belt-and-braces: try name search too.
    try:
        for c in stripe.Customer.search(
            query=f"name:'{ORPHAN_NAME}'"
        ).data:
            if (c.email or "").strip().lower() == ORPHAN_EMAIL.lower():
                return c
    except stripe.error.StripeError:
        pass
    return None


def ensure_orphan_customer() -> stripe.Customer:
    existing = find_orphan_customer()
    if existing:
        log(f"  [reuse] orphan customer {existing.id} ({existing.email})")
        # Make sure metadata + description match the spec (in case of drift).
        try:
            existing = stripe.Customer.modify(
                existing.id,
                description=ORPHAN_DESCRIPTION,
                metadata=ORPHAN_METADATA,
            )
        except stripe.error.StripeError as e:
            log(f"  ! could not refresh orphan metadata: {str(e)[:140]}")
        return existing

    cust = safe_create(
        stripe.Customer.create,
        idem_key=idem("frankenstein", "orphan-cust", "saga-foods-inc"),
        label="Customer[orphan/saga-foods-inc]",
        name=ORPHAN_NAME,
        email=ORPHAN_EMAIL,
        description=ORPHAN_DESCRIPTION,
        metadata=ORPHAN_METADATA,
    )
    log(f"  [new]   orphan customer {cust.id}")
    return cust


def ensure_orphan_payment_method(cust_id: str) -> str:
    """Attach a test pm_card_visa and set it as default."""
    cust = stripe.Customer.retrieve(cust_id)
    invoice_settings = getattr(cust, "invoice_settings", None)
    default_pm = invoice_settings.default_payment_method if invoice_settings else None
    if default_pm and not isinstance(default_pm, str):
        default_pm = default_pm.id
    if default_pm:
        log(f"  [reuse] default pm {default_pm}")
        return default_pm

    pm = stripe.PaymentMethod.attach(
        "pm_card_visa",
        customer=cust_id,
        idempotency_key=idem("frankenstein", "orphan-pm-attach"),
    )
    stripe.Customer.modify(
        cust_id,
        invoice_settings={"default_payment_method": pm.id},
    )
    log(f"  [new]   default pm {pm.id}")
    return pm.id


def find_orphan_product() -> stripe.Product | None:
    """Find existing orphan product by metadata."""
    for p in stripe.Product.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(p)
        if md.get("seeded_by") == "manthan_patch_w2_frankenstein":
            if md.get("plan_key") == "orphan_monthly_starter":
                return p
    return None


def ensure_orphan_product() -> stripe.Product:
    existing = find_orphan_product()
    if existing:
        log(f"  [reuse] orphan product {existing.id}")
        return existing
    prod = safe_create(
        stripe.Product.create,
        idem_key=idem("frankenstein", "orphan-product"),
        label="Product[orphan-monthly-starter]",
        name=ORPHAN_PRODUCT_NAME,
        description=(
            "Auto-created via marketing signup form. Monthly Starter "
            "tier. ORPHAN - does not match any Salesforce account."
        ),
        metadata={
            "plan_key": "orphan_monthly_starter",
            "plan_name": ORPHAN_PRODUCT_NAME,
            "workflow": "W2_frankenstein",
            "seeded_by": "manthan_patch_w2_frankenstein",
        },
    )
    log(f"  [new]   orphan product {prod.id}")
    return prod


def find_orphan_price(product_id: str) -> stripe.Price | None:
    for pr in stripe.Price.list(
        product=product_id, limit=20, active=None
    ).auto_paging_iter():
        md = md_dict(pr)
        if md.get("seeded_by") == "manthan_patch_w2_frankenstein":
            if md.get("price_key") == "orphan_monthly_starter_current":
                return pr
    return None


def ensure_orphan_price(product_id: str) -> stripe.Price:
    existing = find_orphan_price(product_id)
    if existing:
        log(f"  [reuse] orphan price {existing.id}")
        return existing
    price = safe_create(
        stripe.Price.create,
        idem_key=idem("frankenstein", "orphan-price"),
        label="Price[orphan-monthly-starter/current]",
        product=product_id,
        unit_amount=ORPHAN_PRICE_AMOUNT,
        currency="usd",
        recurring={"interval": ORPHAN_PRICE_INTERVAL},
        metadata={
            "plan_key": "orphan_monthly_starter",
            "price_key": "orphan_monthly_starter_current",
            "workflow": "W2_frankenstein",
            "seeded_by": "manthan_patch_w2_frankenstein",
        },
    )
    log(f"  [new]   orphan price {price.id} @ "
        f"${ORPHAN_PRICE_AMOUNT / 100:.2f}/{ORPHAN_PRICE_INTERVAL}")
    return price


def find_orphan_subscription(cust_id: str) -> stripe.Subscription | None:
    for s in stripe.Subscription.list(
        customer=cust_id, limit=10, status="all"
    ).auto_paging_iter():
        md = md_dict(s)
        if md.get("seeded_by") == "manthan_patch_w2_frankenstein":
            return s
    return None


def ensure_orphan_subscription(
    cust_id: str, price_id: str, pm_id: str
) -> tuple[stripe.Subscription, str]:
    """Create the orphan subscription. Try to backdate; fall back if rejected.

    Returns (sub, note) where `note` is empty on clean backdate, or
    describes the workaround taken.
    """
    existing = find_orphan_subscription(cust_id)
    if existing:
        log(f"  [reuse] orphan subscription {existing.id} "
            f"(status={existing.status})")
        return existing, ""

    # Stripe accepts backdate_start_date for in-test-mode subs but only
    # when the resulting first invoice would be in the past (it generates
    # a "catch-up" invoice). We aim for mid-March 2026.
    backdate_ts = 1742083200  # 2026-03-16 00:00:00 UTC

    base_kwargs: dict = {
        "customer": cust_id,
        "items": [{"price": price_id}],
        "default_payment_method": pm_id,
        "metadata": {
            "workflow": "W2_frankenstein",
            "sub_role": "orphan_marketing_signup",
            "seeded_by": "manthan_patch_w2_frankenstein",
            "company_slug": "saga-foods",
            "duplicate_suspect": "true",
            "expected_action": "cancel_and_refund",
        },
    }

    # Attempt 1: backdate via backdate_start_date.
    note = ""
    try:
        sub = safe_create(
            stripe.Subscription.create,
            idem_key=idem("frankenstein", "orphan-sub-backdated"),
            label="Subscription[orphan/saga-foods-inc/backdated]",
            backdate_start_date=backdate_ts,
            proration_behavior="none",
            **base_kwargs,
        )
        log(f"  [new]   orphan subscription {sub.id} (backdated to 2026-03-16)")
        return sub, note
    except stripe.error.StripeError as e:
        msg = e.user_message or str(e)
        log(f"  [backdate-rejected] {msg[:160]}")
        note = (
            "Stripe rejected backdate_start_date - created sub at current "
            "wall-clock and supplemented with 2 manual PaymentIntent "
            "charges in metadata.simulated_created_at=Apr/May 2026."
        )

    # Attempt 2: vanilla sub at wall-clock time.
    sub = safe_create(
        stripe.Subscription.create,
        idem_key=idem("frankenstein", "orphan-sub"),
        label="Subscription[orphan/saga-foods-inc]",
        **base_kwargs,
    )
    log(f"  [new]   orphan subscription {sub.id} (current time; "
        f"manual charges will fill Apr+May)")
    return sub, note


def existing_orphan_charges(cust_id: str) -> dict[str, stripe.Charge]:
    """Index orphan charges by idem_suffix marker baked into description.

    We can't query by idempotency_key on a Charge, so we tag every charge
    with metadata.orphan_charge_label = <label> and search by that.
    """
    out: dict[str, stripe.Charge] = {}
    charges = list(
        stripe.Charge.list(customer=cust_id, limit=100).auto_paging_iter()
    )
    for ch in charges:
        md = md_dict(ch)
        if md.get("seeded_by") == "manthan_patch_w2_frankenstein":
            label = md.get("orphan_charge_label")
            if label:
                out[label] = ch
    return out


def ensure_orphan_charges(cust_id: str, pm_id: str) -> list[stripe.Charge]:
    """Create the two monthly orphan charges (Apr + May 2026).

    Uses metadata.simulated_created_at to encode the historical month
    (Stripe charge.created is always wall-clock).
    """
    existing = existing_orphan_charges(cust_id)
    created: list[stripe.Charge] = []

    for label, idem_suffix, sim_date in ORPHAN_CHARGE_PLAN:
        ch = existing.get(label)
        if ch:
            log(f"  [reuse] orphan charge {ch.id} ({label}) "
                f"status={ch.status}")
            created.append(ch)
            continue

        try:
            pi = safe_create(
                stripe.PaymentIntent.create,
                idem_key=idem("frankenstein", "orphan-pi", idem_suffix),
                label=f"PI[orphan/{idem_suffix}]",
                amount=ORPHAN_PRICE_AMOUNT,
                currency="usd",
                payment_method=pm_id,
                confirm=True,
                customer=cust_id,
                off_session=True,
                description=f"Saga Foods Inc - {label}",
                metadata={
                    "workflow": "W2_frankenstein",
                    "orphan_charge_label": label,
                    "simulated_created_at": sim_date,
                    "company_slug": "saga-foods",
                    "duplicate_suspect": "true",
                    "billing_period_label": label,
                    "seeded_by": "manthan_patch_w2_frankenstein",
                    "expected_action": "refund",
                },
            )
        except stripe.error.StripeError as e:
            log(f"  ! orphan PI {idem_suffix} failed: {str(e)[:200]}")
            continue

        # Wait briefly for latest_charge to materialize.
        if not pi.latest_charge:
            for _ in range(8):
                time.sleep(0.4)
                pi = stripe.PaymentIntent.retrieve(pi.id)
                if pi.latest_charge:
                    break
        if not pi.latest_charge:
            log(f"  ! orphan PI {pi.id} produced no charge")
            continue

        # Decorate the underlying charge with the same metadata + a
        # description so it surfaces nicely in any search.
        try:
            stripe.Charge.modify(
                pi.latest_charge,
                description=f"Saga Foods Inc - {label}",
                metadata={
                    "workflow": "W2_frankenstein",
                    "orphan_charge_label": label,
                    "simulated_created_at": sim_date,
                    "company_slug": "saga-foods",
                    "duplicate_suspect": "true",
                    "billing_period_label": label,
                    "seeded_by": "manthan_patch_w2_frankenstein",
                    "expected_action": "refund",
                },
            )
        except stripe.error.StripeError as e:
            log(f"  ! charge.modify failed for {pi.latest_charge}: "
                f"{str(e)[:160]}")

        ch = stripe.Charge.retrieve(pi.latest_charge)
        log(f"  [new]   orphan charge {ch.id} ({label}) "
            f"${ch.amount / 100:.2f} status={ch.status} paid={ch.paid}")
        created.append(ch)

    return created


# ──────────────────────────────────────────────────────────────────────
# HubSpot - duplicate company + Note
# ──────────────────────────────────────────────────────────────────────


def hs_find_company_by_domain(
    client: httpx.Client, domain: str
) -> str | None:
    r = _request(
        client, "POST", "/crm/v3/objects/companies/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "domain", "operator": "EQ", "value": domain,
            }]}],
            "properties": ["name", "domain"],
            "limit": 1,
        },
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def hs_find_company_by_name_exact(
    client: httpx.Client, name: str
) -> str | None:
    r = _request(
        client, "POST", "/crm/v3/objects/companies/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "name", "operator": "EQ", "value": name,
            }]}],
            "properties": ["name", "domain"],
            "limit": 5,
        },
    )
    if r.status_code != 200:
        return None
    for rec in r.json().get("results", []):
        if (rec.get("properties", {}).get("name") or "").strip() == name:
            return rec["id"]
    return None


def hs_find_legit_saga(client: httpx.Client) -> str | None:
    """Resolve the legit (non-Inc) Saga Foods company id."""
    r = _request(
        client, "POST", "/crm/v3/objects/companies/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "name", "operator": "EQ", "value": "Saga Foods",
            }]}],
            "properties": ["name", "domain"],
            "limit": 5,
        },
    )
    if r.status_code != 200:
        return None
    for rec in r.json().get("results", []):
        name = (rec.get("properties", {}).get("name") or "").strip()
        if name == "Saga Foods":
            return rec["id"]
    return None


def hs_upsert_duplicate_company(
    client: httpx.Client, legit_id: str | None
) -> tuple[str, str]:
    """Create or update the orphan/duplicate Saga Foods Inc company."""
    # Idempotency: search by exact domain first, then by exact name.
    existing_id = hs_find_company_by_domain(client, ORPHAN_HUBSPOT_DOMAIN)
    if not existing_id:
        existing_id = hs_find_company_by_name_exact(client, ORPHAN_NAME)

    description = (
        "Duplicate/orphan record created by misconfigured signup form. "
        "Flagged for merge - DO NOT contact, primary record is the "
        "original Saga Foods company."
    )
    props: dict[str, str] = {
        "name": ORPHAN_NAME,
        "domain": ORPHAN_HUBSPOT_DOMAIN,
        "description": description,
        "lifecyclestage": "other",
    }
    if legit_id:
        # Best-effort custom hint - HubSpot may ignore unknown props
        # (we'd see a 400 and retry without). Try it; tolerate failure.
        props["duplicate_of_company_id"] = legit_id

    if existing_id:
        r = _request(
            client, "PATCH",
            f"/crm/v3/objects/companies/{existing_id}",
            json={"properties": props},
        )
        if r.status_code in (200, 201):
            return existing_id, "updated"
        # Retry without the unknown custom property if HubSpot rejected it.
        if r.status_code == 400 and "duplicate_of_company_id" in props:
            props2 = {k: v for k, v in props.items()
                      if k != "duplicate_of_company_id"}
            r = _request(
                client, "PATCH",
                f"/crm/v3/objects/companies/{existing_id}",
                json={"properties": props2},
            )
            if r.status_code in (200, 201):
                return existing_id, "updated (without duplicate_of_company_id)"
        log(f"  ! company update fail: {r.status_code} {r.text[:200]}")
        return existing_id, "error"

    # Create
    r = _request(
        client, "POST", "/crm/v3/objects/companies",
        json={"properties": props},
    )
    if r.status_code in (200, 201):
        return r.json()["id"], "created"
    # Retry without custom prop
    if r.status_code == 400 and "duplicate_of_company_id" in props:
        props2 = {k: v for k, v in props.items()
                  if k != "duplicate_of_company_id"}
        r = _request(
            client, "POST", "/crm/v3/objects/companies",
            json={"properties": props2},
        )
        if r.status_code in (200, 201):
            return r.json()["id"], "created (without duplicate_of_company_id)"
    log(f"  ! company create fail: {r.status_code} {r.text[:300]}")
    raise SystemExit("hubspot duplicate company create failed")


def hs_find_existing_note(
    client: httpx.Client, company_id: str, signature: str
) -> str | None:
    """Look for a previously-created Note associated to this company
    whose body starts with our signature.

    HubSpot search on notes is limited; we fetch associated notes via
    associations API and inspect bodies.
    """
    r = _request(
        client, "GET",
        f"/crm/v4/objects/companies/{company_id}/associations/notes",
        params={"limit": 100},
    )
    if r.status_code != 200:
        return None
    note_ids = [
        rec.get("toObjectId") for rec in r.json().get("results", [])
        if rec.get("toObjectId")
    ]
    for nid in note_ids:
        r2 = _request(
            client, "GET", f"/crm/v3/objects/notes/{nid}",
            params={"properties": "hs_note_body"},
        )
        if r2.status_code != 200:
            continue
        body = (r2.json().get("properties", {}).get("hs_note_body") or "")
        if signature in body:
            return str(nid)
    return None


NOTE_SIGNATURE = "[manthan_patch_w2_frankenstein]"
NOTE_BODY = (
    f"{NOTE_SIGNATURE} This is a duplicate company created by mistake "
    "via the marketing form. The Stripe customer attached to this is "
    "generating orphan monthly charges that need to be refunded. "
    "See ticket #BC-2026-04-saga."
)


def hs_attach_note(client: httpx.Client, company_id: str) -> tuple[str, str]:
    existing_note_id = hs_find_existing_note(
        client, company_id, NOTE_SIGNATURE
    )
    if existing_note_id:
        return existing_note_id, "reused"

    # Create the note + association in one call (v3 supports it).
    body = {
        "properties": {
            "hs_note_body": NOTE_BODY,
            "hs_timestamp": str(int(time.time() * 1000)),
        },
        "associations": [{
            "to": {"id": company_id},
            "types": [{
                "associationCategory": "HUBSPOT_DEFINED",
                # Note -> Company primary association type id = 190
                "associationTypeId": 190,
            }],
        }],
    }
    r = _request(client, "POST", "/crm/v3/objects/notes", json=body)
    if r.status_code in (200, 201):
        return r.json()["id"], "created"
    log(f"  ! note create fail: {r.status_code} {r.text[:300]}")
    return "", "error"


# ──────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────


def verify_stripe(
    orphan_id: str, sub_id: str, charges: list[stripe.Charge]
) -> dict[str, object]:
    out: dict[str, object] = {}

    # Customer.list filtered by name should return the orphan.
    listed = list(
        stripe.Customer.search(query=f"name:'{ORPHAN_NAME}'").data
    )
    out["orphan_by_name_count"] = len(listed)
    out["orphan_by_name_ids"] = [c.id for c in listed]

    # Charge.list(customer=orphan)
    ch_list = list(
        stripe.Charge.list(customer=orphan_id, limit=20).data
    )
    ch_seven_k = [c for c in ch_list if c.amount == ORPHAN_PRICE_AMOUNT]
    out["charge_count_total"] = len(ch_list)
    out["charge_count_7k"] = len(ch_seven_k)
    out["charge_ids"] = [c.id for c in ch_seven_k]

    # Subscription status
    if sub_id:
        sub = stripe.Subscription.retrieve(sub_id)
        out["sub_status"] = sub.status
    else:
        out["sub_status"] = "n/a"

    # Confirm legit Saga still intact.
    legit = find_legit_saga_customer()
    out["legit_stripe_id"] = legit.id if legit else None
    out["legit_stripe_name"] = legit.name if legit else None
    out["legit_stripe_email"] = legit.email if legit else None
    return out


def verify_hubspot(
    client: httpx.Client, dup_id: str
) -> dict[str, object]:
    out: dict[str, object] = {}

    # Search by exact name (with "Inc")
    r = _request(
        client, "POST", "/crm/v3/objects/companies/search",
        json={
            "filterGroups": [{"filters": [{
                "propertyName": "name", "operator": "EQ", "value": ORPHAN_NAME,
            }]}],
            "properties": ["name", "domain", "description"],
            "limit": 5,
        },
    )
    if r.status_code == 200:
        results = r.json().get("results", [])
        out["dup_match_count"] = len(results)
        out["dup_ids"] = [rec["id"] for rec in results]
    else:
        out["dup_match_count"] = -1
        out["dup_ids"] = []

    # Legit Saga still intact?
    legit_id = hs_find_legit_saga(client)
    out["legit_hs_id"] = legit_id
    if legit_id:
        r = _request(
            client, "GET", f"/crm/v3/objects/companies/{legit_id}",
            params={"properties": "name,domain,description"},
        )
        if r.status_code == 200:
            p = r.json().get("properties", {})
            out["legit_hs_name"] = p.get("name")
            out["legit_hs_domain"] = p.get("domain")
    return out


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    log("=" * 72)
    log("Manthan patch_w2_frankenstein - Saga Foods orphan/duplicate seed")
    log("=" * 72)

    # ──────────────── 1. Stripe side ────────────────
    log("\n[STRIPE]  sanity-checking legit Saga Foods customer...")
    legit = find_legit_saga_customer()
    if not legit:
        raise SystemExit(
            "ERROR: legit Saga Foods customer not found in Stripe. "
            "Run seed_stripe.py first."
        )
    log(f"  legit Saga Foods: {legit.id} | name={legit.name!r} | "
        f"email={legit.email!r}")

    log("\n[STRIPE]  ensuring orphan customer 'Saga Foods Inc'...")
    orphan_cust = ensure_orphan_customer()

    log("\n[STRIPE]  ensuring orphan payment method...")
    pm_id = ensure_orphan_payment_method(orphan_cust.id)

    log("\n[STRIPE]  ensuring orphan product + price...")
    product = ensure_orphan_product()
    price = ensure_orphan_price(product.id)

    log("\n[STRIPE]  ensuring orphan monthly subscription...")
    sub, sub_note = ensure_orphan_subscription(orphan_cust.id, price.id, pm_id)

    log("\n[STRIPE]  ensuring 2 orphan monthly charges (Apr + May 2026)...")
    charges = ensure_orphan_charges(orphan_cust.id, pm_id)

    # ──────────────── 2. HubSpot side ────────────────
    log("\n[HUBSPOT] ensuring duplicate company 'Saga Foods Inc'...")
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT) as client:
        legit_hs_id = hs_find_legit_saga(client)
        if not legit_hs_id:
            log("  ! legit Saga Foods HubSpot company not found "
                "- continuing without duplicate_of link")
        else:
            log(f"  legit Saga Foods HubSpot id: {legit_hs_id}")
        time.sleep(REQ_SLEEP)

        dup_id, dup_action = hs_upsert_duplicate_company(client, legit_hs_id)
        log(f"  [{dup_action:>10}] duplicate company → {dup_id}")
        time.sleep(REQ_SLEEP)

        log("\n[HUBSPOT] attaching duplicate-flag Note to duplicate company...")
        note_id, note_action = hs_attach_note(client, dup_id)
        log(f"  [{note_action:>10}] note → {note_id}")
        time.sleep(REQ_SLEEP)

        # ──────────────── 3. Verification ────────────────
        log("\n" + "─" * 72)
        log("VERIFICATION")
        log("─" * 72)
        stripe_v = verify_stripe(orphan_cust.id, sub.id, charges)
        hs_v = verify_hubspot(client, dup_id)

    log("\nStripe side:")
    log(f"  orphan customer.search by name='Saga Foods Inc' "
        f"-> count={stripe_v['orphan_by_name_count']} "
        f"ids={stripe_v['orphan_by_name_ids']}")
    log(f"  orphan charges $7,000 each   "
        f"-> count={stripe_v['charge_count_7k']}/2 "
        f"ids={stripe_v['charge_ids']}")
    log(f"  subscription status           "
        f"-> {stripe_v['sub_status']}  id={sub.id}")
    log(f"  legit Saga (untouched)        "
        f"-> id={stripe_v['legit_stripe_id']}  "
        f"name={stripe_v['legit_stripe_name']!r}  "
        f"email={stripe_v['legit_stripe_email']!r}")

    log("\nHubSpot side:")
    log(f"  duplicate company search       "
        f"-> count={hs_v['dup_match_count']} ids={hs_v['dup_ids']}")
    log(f"  legit Saga (untouched)        "
        f"-> id={hs_v['legit_hs_id']}  "
        f"name={hs_v.get('legit_hs_name')!r}  "
        f"domain={hs_v.get('legit_hs_domain')!r}")

    total_orphan_exposure = sum(c.amount for c in charges) / 100
    log("\n" + "═" * 72)
    log("SUMMARY")
    log("═" * 72)
    log(f"  Orphan Stripe customer        : {orphan_cust.id}")
    for c in charges:
        md = md_dict(c)
        log(f"    charge {c.id} | ${c.amount / 100:>8.2f} | "
            f"sim_date={md.get('simulated_created_at'):11s} | "
            f"status={c.status} paid={c.paid}")
    log(f"  Orphan subscription           : {sub.id} (status={sub.status})")
    log(f"  HubSpot duplicate company id  : {dup_id}")
    log(f"  HubSpot duplicate Note id     : {note_id}")
    log(f"  Total orphan exposure         : ${total_orphan_exposure:,.2f} "
        f"(agent must discover this)")
    if sub_note:
        log(f"  Caveat: {sub_note}")
    log(f"  Legit Stripe customer intact  : {stripe_v['legit_stripe_id']}")
    log(f"  Legit HubSpot company intact  : {hs_v['legit_hs_id']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
