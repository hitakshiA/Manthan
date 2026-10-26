"""Seed Stripe TEST MODE for the Manthan billing-dispute investigation agent.

Creates real Stripe test-mode records: customers, products, prices,
subscriptions, charges, refunds, and disputes - including the three
target workflow signals (W1/W2/W3) baked into Acme Genomics,
Northwind Logistics, and Mockingbird Media respectively.

Volume targets (revised after first pass undershot ~5x):
  * Customers     : 35   (one per COMPANIES entry)
  * Products      : 8-10 (Trial, Standard/Pro/Enterprise * Monthly/Annual,
                          Premium Support add-on, API Boost add-on)
  * Prices        : 20-25 (current + legacy pricing per product)
  * Subscriptions : 70-100 (multi-sub history per customer)
  * Charges       : 300-500 (renewal cycles across tenure)
  * Invoices      : 60-100
  * Refunds       : 20-30
  * Disputes      : 25-35 (3 W1, 1 W2, 1 W3, plus 20-30 noise)

Idempotent on idempotency_key. Re-runs are near-no-ops.

Stripe test-mode constraints
----------------------------
* Dispute.reason is not user-editable. Only three are reachable via
  test cards: fraudulent (pm_card_createDispute), product_not_received
  (pm_card_createDisputeProductNotReceived), warning_needs_response
  (pm_card_createDisputeInquiry). For workflows that semantically need
  subscription_canceled / duplicate we use the closest test reason and
  encode the true semantic in metadata.semantic_reason.

* Charge.created reflects wall-clock; we can't rewind. Historical
  dates go into metadata.simulated_created_at + the description string.

* "Won by customer + refunded" is expressed by creating a real Refund
  + tagging the dispute with metadata.outcome = refunded_to_customer.
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
AGENT = HERE.parent
sys.path.insert(0, str(HERE))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(AGENT / ".env")

import stripe  # noqa: E402

from seed_world import COMPANIES, WORKFLOWS, Company  # noqa: E402

stripe.api_key = os.getenv("STRIPE_API_KEY")
if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
    raise SystemExit("STRIPE_API_KEY must be a sk_test_... key in agent/.env")

random.seed(20260527)


def idem(*parts: str) -> str:
    return "stripe-" + "-".join(str(p) for p in parts) + "-v1"


def log(msg: str = "") -> None:
    print(msg, flush=True)


def md_dict(obj) -> dict:
    if not obj or not getattr(obj, "metadata", None):
        return {}
    try:
        return obj.metadata.to_dict()
    except Exception:
        return {}


def safe_create(fn, *, idem_key: str, label: str, **kwargs):
    try:
        return fn(idempotency_key=idem_key, **kwargs)
    except stripe.error.StripeError as e:
        log(f"  ! {label} idem={idem_key} err={type(e).__name__}: "
            f"{e.user_message or str(e)[:300]}")
        raise


@dataclass
class PlanSpec:
    key: str
    product_name: str
    description: str
    amount_minor: int
    interval: str
    product_id: str | None = None
    price_id: str | None = None
    legacy_amount_minor: int | None = None
    legacy_price_id: str | None = None
    is_addon: bool = False


PLAN_CATALOG: dict[str, PlanSpec] = {
    "trial": PlanSpec(
        key="trial", product_name="Trial (14-day)",
        description="Time-bounded trial of Pro Annual features.",
        amount_minor=0, interval="year",
    ),
    "standard_monthly": PlanSpec(
        key="standard_monthly", product_name="Standard Monthly",
        description="Standard plan - month-to-month.",
        amount_minor=20000, legacy_amount_minor=15000, interval="month",
    ),
    "standard_annual": PlanSpec(
        key="standard_annual", product_name="Standard Annual",
        description="Standard plan - annual billing.",
        amount_minor=200000, legacy_amount_minor=150000, interval="year",
    ),
    "pro_monthly": PlanSpec(
        key="pro_monthly", product_name="Pro Monthly",
        description="Pro plan - monthly.",
        amount_minor=42000, legacy_amount_minor=35000, interval="month",
    ),
    "pro_annual": PlanSpec(
        key="pro_annual", product_name="Pro Annual",
        description="Pro plan - annual billing. Includes priority support.",
        amount_minor=420000, legacy_amount_minor=360000, interval="year",
    ),
    "enterprise_monthly": PlanSpec(
        key="enterprise_monthly", product_name="Enterprise Monthly",
        description="Enterprise - monthly. SSO, audit logs, SLA.",
        amount_minor=90000, legacy_amount_minor=75000, interval="month",
    ),
    "enterprise_annual": PlanSpec(
        key="enterprise_annual", product_name="Enterprise Annual",
        description="Enterprise - annual. SSO, audit logs, SLA.",
        amount_minor=900000, legacy_amount_minor=750000, interval="year",
    ),
    "addon_premium_support": PlanSpec(
        key="addon_premium_support", product_name="Premium Support (Add-on)",
        description="24x7 premium support add-on.",
        amount_minor=120000, legacy_amount_minor=90000, interval="year",
        is_addon=True,
    ),
    "addon_api_boost": PlanSpec(
        key="addon_api_boost", product_name="API Boost (Add-on)",
        description="10x API rate limits + custom integration.",
        amount_minor=60000, legacy_amount_minor=48000, interval="year",
        is_addon=True,
    ),
}

COMPANY_PLAN_TO_KEY = {
    "Pro Annual": "pro_annual",
    "Enterprise Annual": "enterprise_annual",
    "Standard Monthly": "standard_monthly",
    "Trial": "trial",
}


def ensure_products_and_prices() -> None:
    log("\n== Products + Prices ==")

    existing_prods_by_key = {}
    legacy_prods_by_name = {}
    for p in stripe.Product.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(p)
        if md.get("seeded_by") == "manthan_seed_stripe":
            if md.get("plan_key"):
                existing_prods_by_key[md["plan_key"]] = p
            elif md.get("plan"):
                legacy_prods_by_name[md["plan"]] = p

    existing_prices_by_key = {}
    for pr in stripe.Price.list(limit=100, active=None).auto_paging_iter():
        md = md_dict(pr)
        if md.get("seeded_by") == "manthan_seed_stripe" and md.get("price_key"):
            existing_prices_by_key[md["price_key"]] = pr

    for spec in PLAN_CATALOG.values():
        prod = None
        if spec.key in existing_prods_by_key:
            prod = existing_prods_by_key[spec.key]
        elif spec.product_name in legacy_prods_by_name:
            prod = legacy_prods_by_name[spec.product_name]
            try:
                prod = stripe.Product.modify(prod.id, metadata={
                    "plan_key": spec.key,
                    "plan_name": spec.product_name,
                    "is_addon": "true" if spec.is_addon else "false",
                    "seeded_by": "manthan_seed_stripe",
                })
            except stripe.error.StripeError:
                pass

        if prod:
            log(f"  [reuse] product {spec.product_name:30s} -> {prod.id}")
        else:
            prod = safe_create(
                stripe.Product.create,
                idem_key=idem("product", spec.key),
                label=f"Product[{spec.product_name}]",
                name=spec.product_name,
                description=spec.description,
                metadata={
                    "plan_key": spec.key,
                    "plan_name": spec.product_name,
                    "is_addon": "true" if spec.is_addon else "false",
                    "seeded_by": "manthan_seed_stripe",
                },
            )
            log(f"  [new]   product {spec.product_name:30s} -> {prod.id}")
        spec.product_id = prod.id

        cur_key = f"{spec.key}_current"
        if cur_key in existing_prices_by_key:
            spec.price_id = existing_prices_by_key[cur_key].id
        else:
            unit = max(spec.amount_minor, 1)
            recurring = {"interval": spec.interval if spec.amount_minor > 0 else "year"}
            price = safe_create(
                stripe.Price.create,
                idem_key=idem("price", spec.key, "current"),
                label=f"Price[{spec.product_name}/current]",
                product=prod.id, unit_amount=unit, currency="usd",
                recurring=recurring,
                metadata={
                    "plan_key": spec.key,
                    "price_key": cur_key,
                    "vintage": "current_2026",
                    "seeded_by": "manthan_seed_stripe",
                },
            )
            spec.price_id = price.id
            log(f"            current price {price.id} @ ${unit / 100:.2f}/{spec.interval}")

        if spec.legacy_amount_minor:
            leg_key = f"{spec.key}_legacy"
            if leg_key in existing_prices_by_key:
                spec.legacy_price_id = existing_prices_by_key[leg_key].id
            else:
                legacy = safe_create(
                    stripe.Price.create,
                    idem_key=idem("price", spec.key, "legacy"),
                    label=f"Price[{spec.product_name}/legacy]",
                    product=prod.id, unit_amount=spec.legacy_amount_minor,
                    currency="usd",
                    recurring={"interval": spec.interval},
                    metadata={
                        "plan_key": spec.key,
                        "price_key": leg_key,
                        "vintage": "legacy_2023_2024",
                        "seeded_by": "manthan_seed_stripe",
                    },
                )
                spec.legacy_price_id = legacy.id
                log(f"            legacy  price {legacy.id} @ ${spec.legacy_amount_minor / 100:.2f}/{spec.interval}")


@dataclass
class SeededCustomer:
    slug: str
    company: Company
    customer_id: str
    default_pm_id: str | None


def ensure_customer(c: Company) -> SeededCustomer:
    cust = safe_create(
        stripe.Customer.create,
        idem_key=idem("cust", c.slug),
        label=f"Customer[{c.slug}]",
        email=c.email, name=c.name,
        description=c.notes or f"{c.industry} / {c.country}",
        metadata={
            "slug": c.slug, "industry": c.industry, "country": c.country,
            "arr_usd": str(c.arr_usd), "signup_year": str(c.signup_year),
            "plan": c.plan, "health": c.health,
            "seeded_by": "manthan_seed_stripe",
        },
    )
    cust = stripe.Customer.retrieve(cust.id)
    settings = cust.invoice_settings
    default_pm = settings.default_payment_method if settings else None
    if default_pm and not isinstance(default_pm, str):
        default_pm = default_pm.id
    if not default_pm:
        pm = stripe.PaymentMethod.attach(
            "pm_card_visa", customer=cust.id,
            idempotency_key=idem("pm_attach", c.slug),
        )
        stripe.Customer.modify(cust.id,
            invoice_settings={"default_payment_method": pm.id})
        default_pm = pm.id
    return SeededCustomer(slug=c.slug, company=c, customer_id=cust.id,
                          default_pm_id=default_pm)


TRIAL_SLUGS = {"quantum-synth", "alchemy-foods"}
CANCELLED_SLUGS = {"acme-logistics", "helix-bio", "saga-foods"}
ADDON_SLUGS_PREMIUM_SUPPORT = {
    "northwind-logi", "stellar-ai", "phoenix-fund", "solstice-care",
    "zephyr-ventures", "helio-energy", "nexus-data",
}
ADDON_SLUGS_API_BOOST = {
    "stellar-ai", "quantum-synth", "cascade-cloud", "summit-payments",
    "cobra-cybersec", "delta-payments",
}
LEGACY_CHURN_SLUGS = {
    "phoenix-fund", "solstice-care", "globex-software", "mockingbird-media",
    "helix-bio", "cascade-cloud", "horizon-genomics", "zephyr-ventures",
    "voyager-shipping",
}

# Additional historical subs to bump volume into the 70-100 range.
# Each slug -> list of (history_role, plan_key) tuples.
EXTRA_HISTORY_SUBS: dict[str, list[tuple[str, str]]] = {
    # Old monthly -> annual conversion history
    "delta-payments": [("y1_pro_monthly", "pro_monthly")],
    "summit-payments": [("y1_pro_monthly", "pro_monthly")],
    "meridian-tech": [("y1_standard_monthly", "standard_monthly")],
    "ember-design": [("y1_pro_monthly", "pro_monthly")],
    "titan-marine": [("y1_pro_monthly", "pro_monthly")],
    "alchemy-foods": [("y1_pro_monthly", "pro_monthly")],
    # Enterprise upsell history (was Pro, upgraded)
    "stellar-ai": [("y1_pro_annual", "pro_annual")],
    "nexus-data": [("y1_pro_annual", "pro_annual")],
    # Two-year history of trials before paid
    "orion-labs": [("y0_trial", "trial")],
    "apex-software": [("y0_trial", "trial")],
    "polaris-pay": [("y0_trial", "trial")],
    "hydra-finance": [("y0_trial", "trial")],
    "bottega-romano": [("y0_trial", "trial")],
    "vertex-mining": [("y0_trial", "trial")],
    "hyperion-labs": [("y0_trial", "trial")],
    "oracle-realty": [("y0_trial", "trial")],
    # Acme-genomics already has signals; give it a trial + addon history
    "acme-genomics": [("y0_trial", "trial")],
    # Northwind: was Standard before Enterprise
    "northwind-logi": [("y1_standard_annual", "standard_annual")],
    # Helio: had Pro before Enterprise
    "helio-energy": [("y1_pro_annual", "pro_annual")],
    # Acme-consulting: was on trial then standard monthly
    "acme-consulting": [("y0_trial", "trial")],
    # Acme-logistics: trial -> standard monthly (already cancelled)
    "acme-logistics": [("y0_trial", "trial")],
    # Globex-polymers: y0 trial
    "globex-polymers": [("y0_trial", "trial")],
    # Saga-foods: y0 trial (later cancelled)
    "saga-foods": [("y0_trial", "trial")],
    # Helios-bio: y0 trial
    "helios-bio": [("y0_trial", "trial")],
    # Cobra Cybersec: y1 pro_annual before pro_annual current (legacy pricing)
    "cobra-cybersec": [("y1_pro_annual_legacy_priced", "pro_annual")],
    # Mockingbird already has w3 legacy
}


# Global cache: slug -> [list of existing sub roles]
_EXISTING_SUBS_BY_SLUG: dict[str, dict] = {}


def prefetch_existing_subs() -> None:
    """Pre-fetch all subs to avoid IdempotencyError on re-runs.
    Index by (slug, sub_role)."""
    log("\n  [prefetch] subs...")
    count = 0
    for s in stripe.Subscription.list(limit=100, status="all").auto_paging_iter():
        md = md_dict(s)
        if md.get("seeded_by") != "manthan_seed_stripe":
            continue
        slug = md.get("slug")
        role = md.get("sub_role", "primary")
        plan_key = md.get("plan_key", "")
        history_role = md.get("history_role", "")
        if not slug:
            continue
        _EXISTING_SUBS_BY_SLUG.setdefault(slug, {})
        # Identify by (role, plan_key) combo or history_role
        key = history_role or f"{role}:{plan_key}"
        _EXISTING_SUBS_BY_SLUG[slug][key] = s.id
        count += 1
    log(f"  [prefetch] {count} seed subs already exist across "
        f"{len(_EXISTING_SUBS_BY_SLUG)} customers")


def existing_sub(slug: str, key: str) -> str | None:
    return _EXISTING_SUBS_BY_SLUG.get(slug, {}).get(key)


def ensure_subscriptions(sc: SeededCustomer) -> list[str]:
    plan = sc.company.plan
    plan_key = COMPANY_PLAN_TO_KEY.get(plan, "pro_annual")
    primary_spec = PLAN_CATALOG[plan_key]
    is_trial = sc.slug in TRIAL_SLUGS
    is_cancelled = sc.slug in CANCELLED_SLUGS

    created = []
    primary_key = f"primary:{plan_key}"
    existing = existing_sub(sc.slug, primary_key)
    # Also check generic "primary:" or legacy keys
    if not existing:
        for cached_key, cached_id in _EXISTING_SUBS_BY_SLUG.get(sc.slug, {}).items():
            if cached_key.startswith("primary:"):
                existing = cached_id
                break

    if existing:
        sub = stripe.Subscription.retrieve(existing)
        created.append(sub.id)
    else:
        sub_kwargs: dict = {
            "customer": sc.customer_id,
            "items": [{"price": primary_spec.price_id}],
            "metadata": {
                "slug": sc.slug, "plan": plan, "plan_key": plan_key,
                "seeded_by": "manthan_seed_stripe",
                "billing_source": "stripe_primary",
                "sub_role": "primary",
                "signup_year": str(sc.company.signup_year),
            },
            "default_payment_method": sc.default_pm_id,
        }
        if is_trial:
            sub_kwargs["trial_period_days"] = 14
            sub_kwargs["metadata"]["lifecycle_stage"] = "trial"

        sub = safe_create(
            stripe.Subscription.create,
            idem_key=idem("sub", sc.slug, "primary-v2"),  # v2 to escape stale
            label=f"Subscription[{sc.slug}/primary]",
            **sub_kwargs,
        )
        created.append(sub.id)

    if is_cancelled:
        try:
            stripe.Subscription.cancel(sub.id)
        except stripe.error.StripeError as e:
            log(f"    [cancel-skip] {sc.slug}: {e.user_message or str(e)[:80]}")

    if sc.slug in ADDON_SLUGS_PREMIUM_SUPPORT:
        existing = existing_sub(sc.slug, "addon:addon_premium_support")
        if existing:
            created.append(existing)
        else:
            spec_addon = PLAN_CATALOG["addon_premium_support"]
            try:
                addon = safe_create(
                    stripe.Subscription.create,
                    idem_key=idem("sub", sc.slug, "addon-prem-support-v2"),
                    label=f"Subscription[{sc.slug}/addon-prem]",
                    customer=sc.customer_id,
                    items=[{"price": spec_addon.price_id}],
                    default_payment_method=sc.default_pm_id,
                    metadata={
                        "slug": sc.slug, "plan": "Premium Support",
                        "plan_key": "addon_premium_support",
                        "seeded_by": "manthan_seed_stripe",
                        "billing_source": "stripe_primary",
                        "sub_role": "addon",
                        "addon_attached_to": "primary",
                    },
                )
                created.append(addon.id)
            except stripe.error.StripeError as e:
                log(f"    [addon-prem-skip] {sc.slug}: {str(e)[:120]}")

    if sc.slug in ADDON_SLUGS_API_BOOST:
        existing = existing_sub(sc.slug, "addon:addon_api_boost")
        if existing:
            created.append(existing)
        else:
            spec_addon = PLAN_CATALOG["addon_api_boost"]
            try:
                addon = safe_create(
                    stripe.Subscription.create,
                    idem_key=idem("sub", sc.slug, "addon-api-boost-v2"),
                    label=f"Subscription[{sc.slug}/addon-api]",
                    customer=sc.customer_id,
                    items=[{"price": spec_addon.price_id}],
                    default_payment_method=sc.default_pm_id,
                    metadata={
                        "slug": sc.slug, "plan": "API Boost",
                        "plan_key": "addon_api_boost",
                        "seeded_by": "manthan_seed_stripe",
                        "billing_source": "stripe_primary",
                        "sub_role": "addon",
                        "addon_attached_to": "primary",
                    },
                )
                created.append(addon.id)
            except stripe.error.StripeError as e:
                log(f"    [addon-api-skip] {sc.slug}: {str(e)[:120]}")

    if sc.slug in LEGACY_CHURN_SLUGS:
        legacy_plans = {
            "phoenix-fund": "standard_annual",
            "solstice-care": "pro_annual",
            "globex-software": "trial",
            "mockingbird-media": "pro_annual",
            "helix-bio": "pro_annual",
            "cascade-cloud": "trial",
            "horizon-genomics": "standard_monthly",
            "zephyr-ventures": "pro_annual",
            "voyager-shipping": "standard_monthly",
        }
        prev_key = legacy_plans[sc.slug]
        existing = existing_sub(sc.slug, f"history_predecessor:{prev_key}")
        if existing:
            created.append(existing)
        else:
            prev_spec = PLAN_CATALOG[prev_key]
            price_id = prev_spec.legacy_price_id or prev_spec.price_id
            try:
                legacy = safe_create(
                    stripe.Subscription.create,
                    idem_key=idem("sub", sc.slug, "legacy-history-v2"),
                    label=f"Subscription[{sc.slug}/legacy-history]",
                    customer=sc.customer_id,
                    items=[{"price": price_id}],
                    default_payment_method=sc.default_pm_id,
                    metadata={
                        "slug": sc.slug, "plan": prev_spec.product_name,
                        "plan_key": prev_key,
                        "seeded_by": "manthan_seed_stripe",
                        "billing_source": "stripe_primary",
                        "sub_role": "history_predecessor",
                        "lifecycle_note": (
                            f"Customer's previous plan before migrating to {plan}. "
                            f"Cancelled at upgrade time."
                        ),
                        "simulated_cancelled_at": (
                            "2024-08-15" if prev_key == "trial" else "2024-12-31"
                        ),
                    },
                )
                try:
                    stripe.Subscription.cancel(legacy.id)
                except stripe.error.StripeError:
                    pass
                created.append(legacy.id)
            except stripe.error.StripeError as e:
                log(f"    [legacy-skip] {sc.slug}: {str(e)[:120]}")

    # ── Extra history subs (volume bump) ──
    if sc.slug in EXTRA_HISTORY_SUBS:
        for hist_role, hist_plan_key in EXTRA_HISTORY_SUBS[sc.slug]:
            existing = existing_sub(sc.slug, hist_role)
            if existing:
                created.append(existing)
                continue
            hist_spec = PLAN_CATALOG[hist_plan_key]
            price_id = hist_spec.legacy_price_id or hist_spec.price_id
            try:
                hist_sub = safe_create(
                    stripe.Subscription.create,
                    idem_key=idem("sub", sc.slug, hist_role, "v2"),
                    label=f"Subscription[{sc.slug}/{hist_role}]",
                    customer=sc.customer_id,
                    items=[{"price": price_id}],
                    default_payment_method=sc.default_pm_id,
                    metadata={
                        "slug": sc.slug,
                        "plan": hist_spec.product_name,
                        "plan_key": hist_plan_key,
                        "seeded_by": "manthan_seed_stripe",
                        "billing_source": "stripe_primary",
                        "sub_role": "extra_history",
                        "history_role": hist_role,
                        "lifecycle_note": (
                            f"Historical sub: customer was on "
                            f"{hist_spec.product_name} before current plan."
                        ),
                        "simulated_cancelled_at": "2024-06-30",
                    },
                )
                try:
                    stripe.Subscription.cancel(hist_sub.id)
                except stripe.error.StripeError:
                    pass
                created.append(hist_sub.id)
            except stripe.error.StripeError as e:
                log(f"    [extra-history-skip] {sc.slug}/{hist_role}: "
                    f"{str(e)[:120]}")

    if sc.slug == "mockingbird-media":
        existing = existing_sub(sc.slug, "w3_legacy_entity:pro_annual")
        if existing:
            created.append(existing)
            log(f"    [reuse] W3 legacy sub: {existing}")
        else:
            try:
                legacy_w3 = safe_create(
                    stripe.Subscription.create,
                    idem_key=idem("sub", sc.slug, "w3-legacy-v2"),
                    label=f"Subscription[{sc.slug}/w3-legacy]",
                    customer=sc.customer_id,
                    items=[{"price": PLAN_CATALOG["pro_annual"].price_id}],
                    default_payment_method=sc.default_pm_id,
                    metadata={
                        "slug": sc.slug, "plan": "Pro Annual",
                        "billing_source": "legacy",
                        "sub_role": "w3_legacy_entity",
                        "should_have_terminated": "2026-03-31",
                        "post_acquisition_migration_runbook": "RB-2026-MIG-08",
                        "seeded_by": "manthan_seed_stripe",
                        "workflow": "W3",
                        "semantic_note": (
                            "Legacy billing entity sub. Should have been cancelled "
                            "end of March 2026 (acquisition migration); wasn't. "
                            "Customer double-billed Apr/May 2026."
                        ),
                    },
                )
                created.append(legacy_w3.id)
                log(f"    W3 legacy sub: {legacy_w3.id}")
            except stripe.error.StripeError as e:
                log(f"    [w3-legacy-skip] {sc.slug}: {str(e)[:120]}")

        # Always tag the primary sub with W3 markers (idempotent modify)
        try:
            stripe.Subscription.modify(
                sub.id,
                metadata={
                    "slug": sc.slug, "plan": plan, "plan_key": plan_key,
                    "seeded_by": "manthan_seed_stripe",
                    "billing_source": "stripe_post_migration",
                    "sub_role": "primary",
                    "migration_date": "2026-03-15",
                    "workflow": "W3",
                },
            )
        except stripe.error.StripeError as e:
            log(f"    [w3-modify-skip] {e.user_message or str(e)[:80]}")

    return created


def create_charge(*, customer_id: str, slug: str, amount_minor: int,
                  description: str, metadata: dict,
                  payment_method: str = "pm_card_visa",
                  idem_suffix: str) -> stripe.Charge:
    pi = safe_create(
        stripe.PaymentIntent.create,
        idem_key=idem("pi", slug, idem_suffix),
        label=f"PI[{slug}/{idem_suffix}]",
        amount=amount_minor, currency="usd",
        payment_method=payment_method, confirm=True,
        customer=customer_id, off_session=True,
        description=description,
        metadata={**metadata, "slug": slug, "seeded_by": "manthan_seed_stripe"},
    )
    if not pi.latest_charge:
        for _ in range(5):
            time.sleep(0.4)
            pi = stripe.PaymentIntent.retrieve(pi.id)
            if pi.latest_charge:
                break
        if not pi.latest_charge:
            raise RuntimeError(f"PI {pi.id} has no latest_charge")
    try:
        stripe.Charge.modify(
            pi.latest_charge, description=description,
            metadata={**metadata, "slug": slug, "seeded_by": "manthan_seed_stripe"},
        )
    except stripe.error.StripeError as e:
        log(f"    [charge-modify-skip] {pi.latest_charge}: {str(e)[:80]}")
    return stripe.Charge.retrieve(pi.latest_charge)


def create_failed_charge(*, customer_id: str, slug: str, amount_minor: int,
                          description: str, metadata: dict, idem_suffix: str):
    try:
        return stripe.PaymentIntent.create(
            idempotency_key=idem("pi-fail", slug, idem_suffix),
            amount=amount_minor, currency="usd",
            payment_method="pm_card_chargeDeclined",
            confirm=True, customer=customer_id, off_session=True,
            description=description,
            metadata={**metadata, "slug": slug, "seeded_by": "manthan_seed_stripe",
                      "failed_card_test": "true"},
        )
    except stripe.error.CardError as e:
        pi_id = (e.error.payment_intent.id
                 if e.error and getattr(e.error, "payment_intent", None)
                 else None)
        if pi_id:
            return stripe.PaymentIntent.retrieve(pi_id)
        return None
    except stripe.error.StripeError as e:
        log(f"    [failed-charge-err] {slug}/{idem_suffix}: {str(e)[:100]}")
        return None


def years_of_history(signup_year: int, now_year: int = 2026) -> int:
    return max(1, now_year - signup_year)


def generate_charge_history_for(sc: SeededCustomer) -> int:
    plan = sc.company.plan
    plan_key = COMPANY_PLAN_TO_KEY.get(plan, "pro_annual")
    spec = PLAN_CATALOG[plan_key]
    yrs = years_of_history(sc.company.signup_year)

    is_monthly = spec.interval == "month"
    is_trial = sc.slug in TRIAL_SLUGS
    is_cancelled = sc.slug in CANCELLED_SLUGS

    if is_trial:
        try:
            create_charge(
                customer_id=sc.customer_id, slug=sc.slug, amount_minor=1,
                description=f"{sc.company.name} - Trial start (14-day free)",
                metadata={
                    "simulated_created_at": f"{sc.company.signup_year}-08-01",
                    "charge_category": "trial_start",
                    "lifecycle_stage": "trial",
                },
                idem_suffix="hist-trial-start",
            )
            return 1
        except (stripe.error.StripeError, RuntimeError):
            return 0

    if is_monthly:
        n_charges = min(18, yrs * 12)
    else:
        n_charges = yrs

    if is_cancelled:
        n_charges = min(n_charges, 4 if is_monthly else 1)

    base_year = sc.company.signup_year
    if is_monthly:
        dates = []
        for i in range(n_charges):
            year = base_year + (i // 12)
            month = (i % 12) + 1
            dates.append(f"{year}-{month:02d}-15")
    else:
        dates = [f"{base_year + i}-05-15" for i in range(n_charges)]

    current_amount = spec.amount_minor
    legacy_amount = spec.legacy_amount_minor or current_amount
    legacy_cutoff_year = 2025

    created = 0
    for i, sim_date in enumerate(dates):
        year = int(sim_date[:4])
        amount = legacy_amount if year < legacy_cutoff_year else current_amount
        amount += random.randint(-25, 25) * 100
        amount = max(amount, 100)

        renewal_label = "renewal" if i > 0 else "initial signup"
        period_label = sim_date if is_monthly else f"Y{i + 1} ({sim_date})"
        description = (
            f"{sc.company.name} - {spec.product_name} {renewal_label} - {period_label}"
        )

        if random.random() < 0.05 and i > 0:
            create_failed_charge(
                customer_id=sc.customer_id, slug=sc.slug,
                amount_minor=amount,
                description=description + " [FAILED PAYMENT]",
                metadata={
                    "simulated_created_at": sim_date,
                    "charge_category": "failed_payment",
                    "retry_attempted": "true",
                    "billing_period_label": period_label,
                },
                idem_suffix=f"hist-{i + 1}-fail",
            )
            try:
                create_charge(
                    customer_id=sc.customer_id, slug=sc.slug,
                    amount_minor=amount,
                    description=description + " [auto-retry SUCCEEDED]",
                    metadata={
                        "simulated_created_at": sim_date,
                        "charge_category": "failed_then_retried",
                        "billing_period_label": period_label,
                    },
                    idem_suffix=f"hist-{i + 1}-retry",
                )
                created += 1
            except (stripe.error.StripeError, RuntimeError) as e:
                log(f"    [retry-skip] {sc.slug}/hist-{i + 1}: {str(e)[:80]}")
        else:
            try:
                create_charge(
                    customer_id=sc.customer_id, slug=sc.slug,
                    amount_minor=amount,
                    description=description,
                    metadata={
                        "simulated_created_at": sim_date,
                        "charge_category": (
                            "subscription_renewal" if i > 0 else "initial_signup"
                        ),
                        "billing_period_label": period_label,
                        "vintage": "current" if year >= legacy_cutoff_year else "legacy",
                    },
                    idem_suffix=f"hist-{i + 1}",
                )
                created += 1
            except (stripe.error.StripeError, RuntimeError) as e:
                log(f"    [charge-skip] {sc.slug}/hist-{i + 1}: {str(e)[:80]}")

    if sc.slug in ADDON_SLUGS_PREMIUM_SUPPORT:
        for y_idx in range(min(yrs, 2)):
            year = base_year + y_idx
            try:
                create_charge(
                    customer_id=sc.customer_id, slug=sc.slug,
                    amount_minor=120000 if year >= 2025 else 90000,
                    description=(
                        f"{sc.company.name} - Premium Support add-on "
                        f"Y{y_idx + 1} ({year}-08-01)"
                    ),
                    metadata={
                        "simulated_created_at": f"{year}-08-01",
                        "charge_category": "addon_renewal",
                        "addon_kind": "premium_support",
                        "billing_period_label": f"Premium Support Y{y_idx + 1}",
                    },
                    idem_suffix=f"addon-prem-y{y_idx + 1}",
                )
                created += 1
            except (stripe.error.StripeError, RuntimeError) as e:
                log(f"    [addon-prem-charge-skip] {sc.slug}: {str(e)[:80]}")

    if sc.slug in ADDON_SLUGS_API_BOOST:
        for y_idx in range(min(yrs, 2)):
            year = base_year + y_idx
            try:
                create_charge(
                    customer_id=sc.customer_id, slug=sc.slug,
                    amount_minor=60000 if year >= 2025 else 48000,
                    description=(
                        f"{sc.company.name} - API Boost add-on "
                        f"Y{y_idx + 1} ({year}-09-12)"
                    ),
                    metadata={
                        "simulated_created_at": f"{year}-09-12",
                        "charge_category": "addon_renewal",
                        "addon_kind": "api_boost",
                        "billing_period_label": f"API Boost Y{y_idx + 1}",
                    },
                    idem_suffix=f"addon-api-y{y_idx + 1}",
                )
                created += 1
            except (stripe.error.StripeError, RuntimeError) as e:
                log(f"    [addon-api-charge-skip] {sc.slug}: {str(e)[:80]}")

    return created


REFUND_PLAN = [
    ("vertex-mining", "requested_by_customer", "rf-vertex-1",
     "Customer requested partial refund for unused Q4 period."),
    ("bottega-romano", "requested_by_customer", "rf-bottega-1",
     "Goodwill refund - extended outage compensation."),
    ("orion-labs", "duplicate", "rf-orion-1",
     "Duplicate annual charge - refunded second one."),
    ("polaris-pay", "requested_by_customer", "rf-polaris-1",
     "Customer downgraded mid-cycle, prorated refund."),
    ("hyperion-labs", "duplicate", "rf-hyper-1",
     "Accidentally double-billed during API integration."),
    ("ember-design", "requested_by_customer", "rf-ember-1",
     "Trial converted accidentally; refunded."),
    ("oracle-realty", "requested_by_customer", "rf-oracle-1",
     "Goodwill - onboarding delay compensation."),
    ("apex-software", "requested_by_customer", "rf-apex-1",
     "Plan downgrade mid-cycle, prorated refund."),
    ("delta-payments", "duplicate", "rf-delta-1",
     "Duplicate charge during card update."),
    ("alchemy-foods", "requested_by_customer", "rf-alchemy-1",
     "Customer-requested early termination refund."),
    ("titan-marine", "requested_by_customer", "rf-titan-1",
     "Service outage compensation."),
    ("voyager-shipping", "duplicate", "rf-voyager-1",
     "Webhook retry double-charged; refunded."),
    ("meridian-tech", "requested_by_customer", "rf-meridian-1",
     "Customer-requested partial refund."),
    ("cobra-cybersec", "requested_by_customer", "rf-cobra-1",
     "Goodwill - security incident remediation."),
    ("globex-polymers", "requested_by_customer", "rf-globex-poly-1",
     "Mistaken upgrade - restored Standard tier."),
    ("hydra-finance", "requested_by_customer", "rf-hydra-1",
     "Customer error during plan selection."),
    ("nexus-data", "requested_by_customer", "rf-nexus-1",
     "Annual contract amendment - partial refund."),
    ("helio-energy", "requested_by_customer", "rf-helio-1",
     "Service-level shortfall - SLA credit refund."),
    ("phoenix-fund", "requested_by_customer", "rf-phoenix-1",
     "Customer requested prorated refund on Y2 renewal."),
    ("solstice-care", "duplicate", "rf-solstice-1",
     "Duplicate charge on Premium Support add-on."),
    ("acme-consulting", "requested_by_customer", "rf-acme-cons-1",
     "Goodwill refund - feature gap apology."),
    ("globex-software", "requested_by_customer", "rf-globex-sw-1",
     "Prorated refund on annual renewal mid-cycle."),
    ("horizon-genomics", "requested_by_customer", "rf-horizon-1",
     "Customer cancelled within grace period."),
    ("zephyr-ventures", "requested_by_customer", "rf-zephyr-1",
     "Customer-negotiated discount applied retroactively."),
    ("summit-payments", "fraudulent", "rf-summit-1",
     "Fraudulent charge - refunded after investigation."),
    ("stellar-ai", "requested_by_customer", "rf-stellar-1",
     "AE-approved discount applied via refund."),
]


def seed_refunds(sc_by_slug: dict[str, SeededCustomer]) -> list:
    log("\n== Refunds ==")
    refunds_made = []
    # Pre-fetch existing refunds keyed by (slug, refund_kind:noise_refund)
    existing_by_slug: dict[str, list] = {}
    for r in stripe.Refund.list(limit=100).auto_paging_iter():
        md = md_dict(r)
        if md.get("seeded_by") == "manthan_seed_stripe" and md.get("slug"):
            existing_by_slug.setdefault(md["slug"], []).append(r)

    for slug, reason, idem_suffix, descr in REFUND_PLAN:
        sc = sc_by_slug.get(slug)
        if not sc:
            continue

        # If a refund already exists for this slug, reuse it
        if slug in existing_by_slug and existing_by_slug[slug]:
            ref = existing_by_slug[slug][0]
            refunds_made.append(ref)
            log(f"  [reuse] refund {slug:25s} ${ref.amount / 100:7.2f} -> {ref.id}")
            continue

        chs = list(stripe.Charge.list(customer=sc.customer_id, limit=20).data)
        candidates = [
            c for c in chs
            if c.status == "succeeded" and not c.refunded
            and (c.amount_refunded or 0) == 0 and not c.disputed
        ]
        if not candidates:
            log(f"  [skip] no refundable charge for {slug}")
            continue
        ch = candidates[0]
        full = random.random() > 0.7
        amount_to_refund = (
            ch.amount if full
            else max(1000, int(ch.amount * random.uniform(0.2, 0.5)))
        )
        try:
            ref = safe_create(
                stripe.Refund.create,
                idem_key=idem("refund", slug, idem_suffix, "v2"),
                label=f"Refund[{slug}/{idem_suffix}]",
                charge=ch.id, amount=amount_to_refund, reason=reason,
                metadata={
                    "slug": slug, "seeded_by": "manthan_seed_stripe",
                    "refund_reason_note": descr,
                    "refund_type": "full" if full else "partial",
                    "refund_kind": "noise_refund",
                },
            )
            refunds_made.append(ref)
            log(f"  refund {slug:25s} ${amount_to_refund / 100:7.2f} "
                f"({reason}) -> {ref.id}")
        except stripe.error.StripeError as e:
            log(f"  ! refund {slug}/{idem_suffix} failed: "
                f"{e.user_message or str(e)[:120]}")
    return refunds_made


def submit_dispute_evidence(dispute_id: str, *, evidence: dict,
                              metadata: dict, submit: bool = False):
    kwargs: dict = {"evidence": evidence, "metadata": metadata}
    if submit:
        kwargs["submit"] = True
    return stripe.Dispute.modify(dispute_id, **kwargs)


# Global cache for already-seeded disputes (workflow + noise).
_EXISTING_W_DISPUTES: dict[str, list[dict]] = {}  # workflow -> [{disp_id, renewal_number, ...}]
_EXISTING_NOISE_DISPUTES: dict[str, str] = {}     # noise_label -> disp_id


def prefetch_existing_disputes() -> None:
    """Pre-fetch existing workflow + noise disputes so re-runs can skip
    re-creation (avoiding stale idempotency_key collisions)."""
    log("\n  [prefetch] disputes...")
    for d in stripe.Dispute.list(limit=100).auto_paging_iter():
        md = md_dict(d)
        wf = md.get("workflow")
        if wf in ("W1", "W2", "W3"):
            _EXISTING_W_DISPUTES.setdefault(wf, []).append({
                "id": d.id, "charge": d.charge,
                "renewal_number": md.get("renewal_number"),
                "metadata": md,
            })
        elif md.get("noise") == "true":
            label = md.get("noise_label", "")
            if label and label not in _EXISTING_NOISE_DISPUTES:
                _EXISTING_NOISE_DISPUTES[label] = d.id
    log(f"  [prefetch] W1={len(_EXISTING_W_DISPUTES.get('W1', []))} "
        f"W2={len(_EXISTING_W_DISPUTES.get('W2', []))} "
        f"W3={len(_EXISTING_W_DISPUTES.get('W3', []))} "
        f"noise={len(_EXISTING_NOISE_DISPUTES)}")


def make_disputed_charge(*, sc: SeededCustomer, amount_minor: int,
                          description: str, metadata: dict,
                          dispute_test_card: str, idem_suffix: str):
    ch = create_charge(
        customer_id=sc.customer_id, slug=sc.slug,
        amount_minor=amount_minor, description=description,
        metadata=metadata, payment_method=dispute_test_card,
        idem_suffix=idem_suffix,
    )
    dispute_id = ch.dispute
    if not dispute_id:
        for _ in range(8):
            time.sleep(0.6)
            ch = stripe.Charge.retrieve(ch.id)
            if ch.dispute:
                dispute_id = ch.dispute
                break
        if not dispute_id:
            raise RuntimeError(
                f"No dispute on charge {ch.id} (card={dispute_test_card})"
            )
    disp = stripe.Dispute.retrieve(dispute_id)
    return ch, disp


def seed_w1_acme_genomics(sc: SeededCustomer) -> dict:
    log(f"\n  W1: Acme Genomics ({sc.customer_id}) - 3 daisy-chained disputes")
    PRICE = 4_200_00
    out = {"charges": [], "disputes": []}
    # v2 idem keys to escape stale probe collisions from earlier runs.
    targets = [
        {"sim_date": "2025-08-12", "outcome": "refunded_to_customer",
         "label": "Aug 2025 renewal", "idem": "w1-disp-1-v2"},
        {"sim_date": "2026-01-09", "outcome": "refunded_to_customer",
         "label": "Jan 2026 renewal", "idem": "w1-disp-2-v2"},
        {"sim_date": "2026-05-15", "outcome": "open_needs_response",
         "label": "May 2026 renewal", "idem": "w1-disp-3-v2"},
    ]
    # Check cache first - skip if W1 disputes already exist
    existing_w1 = _EXISTING_W_DISPUTES.get("W1", [])
    by_renewal = {e.get("renewal_number"): e for e in existing_w1}

    for n, t in enumerate(targets, start=1):
        renewal_key = str(n)
        if renewal_key in by_renewal:
            cached = by_renewal[renewal_key]
            disp = stripe.Dispute.retrieve(cached["id"])
            ch = stripe.Charge.retrieve(disp.charge) if disp.charge else None
            if ch:
                log(f"    [reuse] W1 disp #{n}: {disp.id} (status={disp.status})")
                out["charges"].append(ch.id)
                out["disputes"].append(disp.id)
                continue

        # Build with a fresh unique idem (timestamp-suffix) to avoid stale collisions
        import time as _time
        unique_suffix = t["idem"] + f"-{int(_time.time())}"
        ch, disp = make_disputed_charge(
            sc=sc, amount_minor=PRICE,
            description=(
                f"Acme Genomics - Pro Annual renewal #{n} ({t['sim_date']}). "
                f"Customer claim: 'I cancelled' (no formal cancel exists)."
            ),
            metadata={
                "simulated_created_at": t["sim_date"],
                "workflow": "W1",
                "workflow_label": "daisy_chained_chargebacks",
                "semantic_reason": "subscription_canceled",
                "customer_claim": "I cancelled this subscription",
                "renewal_number": str(n),
                "outcome_expected": t["outcome"],
            },
            dispute_test_card="pm_card_createDispute",
            idem_suffix=unique_suffix,
        )
        evidence_payload = {
            "cancellation_policy_disclosure": (
                "Acme Genomics signed Pro Annual 2023-04-18 with auto-renew. "
                "Cancellation requires 30-day written notice (ToS s. 8.2). "
                "No notice in Intercom, Zendesk, or email logs. Product usage "
                "continued post-charge per PostHog activity."
            ),
            "customer_communication": (
                "Customer claimed cancellation via dispute; no formal cancel "
                "in any system. Pattern: 3rd 'cancelled' claim in 8 months."
            ),
            "service_documentation": "Pro Annual SaaS plan, auto-renewed per ToS",
            "uncategorized_text": (
                f"Workflow W1 dispute #{n}. Outcome marker: {t['outcome']}. "
                f"Simulated dispute date: {t['sim_date']}."
            ),
        }
        meta_payload = {
            "workflow": "W1",
            "workflow_label": "daisy_chained_chargebacks",
            "semantic_reason": "subscription_canceled",
            "simulated_created_at": t["sim_date"],
            "renewal_number": str(n),
            "outcome": t["outcome"],
            "seeded_by": "manthan_seed_stripe",
        }
        if t["outcome"] == "refunded_to_customer":
            # Submit evidence + metadata then CLOSE the dispute as lost
            # (concedes = funds returned to customer). Stripe blocks
            # Refund.create on disputed charges, so the concession via
            # Dispute.close is the right "we refunded them" signal.
            disp = submit_dispute_evidence(
                disp.id, evidence=evidence_payload,
                metadata={**meta_payload,
                          "outcome_realized": "conceded_funds_returned"},
                submit=False,
            )
            try:
                stripe.Dispute.close(disp.id)
                disp = stripe.Dispute.retrieve(disp.id)
                log(f"    #{n} ch={ch.id} disp={disp.id} status={disp.status} "
                    f"(won-by-customer / conceded)")
            except stripe.error.StripeError as e:
                log(f"    dispute close failed: {e.user_message or str(e)[:120]}")
        else:
            disp = stripe.Dispute.modify(disp.id, metadata=meta_payload)
            log(f"    #{n} ch={ch.id} disp={disp.id} (open)")
        out["charges"].append(ch.id)
        out["disputes"].append(disp.id)
    return out


def seed_w2_northwind(sc: SeededCustomer) -> dict:
    log(f"\n  W2: Northwind Logistics ({sc.customer_id}) - $9,000 ghost-paid upgrade")
    out: dict = {"charges": [], "disputes": []}

    existing_w2 = _EXISTING_W_DISPUTES.get("W2", [])
    if existing_w2:
        cached = existing_w2[0]
        disp = stripe.Dispute.retrieve(cached["id"])
        ch = stripe.Charge.retrieve(disp.charge) if disp.charge else None
        if ch:
            log(f"    [reuse] W2 dispute: {disp.id} (status={disp.status})")
            out["charges"].append(ch.id)
            out["disputes"].append(disp.id)
            return out

    import time as _time
    unique_suffix = "w2-disp" + f"-{int(_time.time())}"
    ch, disp = make_disputed_charge(
        sc=sc, amount_minor=9_000_00,
        description=(
            "Northwind Logistics - Enterprise upgrade (May 2026). "
            "Payment captured; entitlement was NOT flipped (webhook handler "
            "for invoice.payment_succeeded crashed - see Sentry + Datadog). "
            "Customer remained on Standard tier despite paying upgrade fee."
        ),
        metadata={
            "simulated_created_at": "2026-05-13",
            "workflow": "W2",
            "workflow_label": "failed_webhook_ghost_paid",
            "semantic_reason": "product_not_received",
            "charge_category": "upgrade",
            "from_plan": "Standard", "to_plan": "Enterprise",
            "webhook_event_id": "evt_seed_w2_failed_2026_05_13",
            "entitlement_flipped": "false",
            "expected_decision": "refund_full_plus_apology_plus_manual_upgrade",
        },
        dispute_test_card="pm_card_createDisputeProductNotReceived",
        idem_suffix=unique_suffix,
    )
    disp = stripe.Dispute.modify(
        disp.id,
        metadata={
            "workflow": "W2",
            "workflow_label": "failed_webhook_ghost_paid",
            "semantic_reason": "product_not_received",
            "simulated_created_at": "2026-05-13",
            "vendor_failure": "true",
            "outcome_expected": "refund",
            "seeded_by": "manthan_seed_stripe",
        },
    )
    log(f"    ch={ch.id} disp={disp.id} status={disp.status} reason={disp.reason}")
    out["charges"].append(ch.id)
    out["disputes"].append(disp.id)
    return out


def seed_w3_mockingbird(sc: SeededCustomer) -> dict:
    log(f"\n  W3: Mockingbird Media ({sc.customer_id}) - $5,500 Stripe-side double-billing")
    out: dict = {"charges": [], "disputes": []}

    existing_w3 = _EXISTING_W_DISPUTES.get("W3", [])
    if existing_w3:
        cached = existing_w3[0]
        disp = stripe.Dispute.retrieve(cached["id"])
        ch = stripe.Charge.retrieve(disp.charge) if disp.charge else None
        if ch:
            log(f"    [reuse] W3 dispute: {disp.id} (status={disp.status})")
            out["charges"].append(ch.id)
            out["disputes"].append(disp.id)
            return out

    import time as _time
    unique_suffix = "w3-disp" + f"-{int(_time.time())}"
    ch, disp = make_disputed_charge(
        sc=sc, amount_minor=5_500_00,
        description=(
            "Mockingbird Media - Pro Annual prorated charge (May 2026). "
            "Customer is also being billed $5,500 by our LEGACY billing "
            "entity for the same service (legacy sub should have terminated "
            "2026-03-31 per migration runbook RB-2026-MIG-08). Customer is "
            "paying twice for the same coverage period."
        ),
        metadata={
            "simulated_created_at": "2026-05-08",
            "workflow": "W3",
            "workflow_label": "post_acquisition_double_billing",
            "semantic_reason": "duplicate",
            "charge_category": "duplicate_period_billing",
            "migration_runbook": "RB-2026-MIG-08",
            "legacy_entity_should_have_terminated": "2026-03-31",
            "this_side": "stripe_post_migration",
            "duplicate_period": "2026-04-01 to 2026-04-30",
        },
        dispute_test_card="pm_card_createDispute",
        idem_suffix=unique_suffix,
    )
    disp = stripe.Dispute.modify(
        disp.id,
        evidence={
            "duplicate_charge_explanation": (
                "Customer disputes duplicate billing post-acquisition migration. "
                "Stripe side ($5,500) is the legitimate post-migration charge; "
                "the LEGACY entity also charged $5,500 for the same April 2026 "
                "coverage. Per runbook RB-2026-MIG-08 legacy was scheduled to "
                "terminate 2026-03-31; that termination was never executed."
            ),
            "duplicate_charge_documentation": (
                "Migration runbook RB-2026-MIG-08, section 4.3: legacy "
                "subscriptions cancel end of March 2026. Mockingbird's legacy "
                "sub (id in Notion ledger) remained active."
            ),
            "uncategorized_text": (
                "Workflow W3. Semantic dispute reason is DUPLICATE (test mode "
                "lacks a duplicate test card; reason shows 'fraudulent' as "
                "best-available proxy). Outcome expected: refund the "
                "legacy-side charge per runbook."
            ),
        },
        metadata={
            "workflow": "W3",
            "workflow_label": "post_acquisition_double_billing",
            "semantic_reason": "duplicate",
            "simulated_created_at": "2026-05-08",
            "migration_runbook": "RB-2026-MIG-08",
            "this_side": "stripe_post_migration",
            "outcome_expected": "refund_legacy_side",
            "seeded_by": "manthan_seed_stripe",
        },
    )
    log(f"    ch={ch.id} disp={disp.id} status={disp.status}")
    out["charges"].append(ch.id)
    out["disputes"].append(disp.id)
    return out


NOISE_DISPUTE_PLAN: list[dict] = [
    {"slug": "helio-energy", "amount": 750000, "card": "pm_card_createDispute",
     "sim_date": "2024-04-18", "label": "Old fraud claim, customer wrong card",
     "outcome": "submit_won"},
    {"slug": "phoenix-fund", "amount": 168000, "card": "pm_card_createDispute",
     "sim_date": "2024-08-25", "label": "Misattributed payment by CFO",
     "outcome": "submit_won"},
    {"slug": "globex-software", "amount": 40000, "card": "pm_card_createDispute",
     "sim_date": "2024-07-12", "label": "Customer card-not-recognised",
     "outcome": "submit_lost"},
    {"slug": "voyager-shipping", "amount": 72000, "card": "pm_card_createDisputeInquiry",
     "sim_date": "2025-01-22", "label": "Pre-arbitration inquiry, resolved",
     "outcome": "warning_only"},
    {"slug": "stellar-ai", "amount": 132000, "card": "pm_card_createDispute",
     "sim_date": "2025-03-14", "label": "Misattributed enterprise payment",
     "outcome": "refunded"},
    {"slug": "phoenix-fund", "amount": 168000, "card": "pm_card_createDisputeProductNotReceived",
     "sim_date": "2025-05-19", "label": "Onboarding delay claim",
     "outcome": "refunded"},
    {"slug": "delta-payments", "amount": 42000, "card": "pm_card_createDispute",
     "sim_date": "2025-06-02", "label": "Card-not-recognised (CFO travel)",
     "outcome": "submit_won"},
    {"slug": "summit-payments", "amount": 42000, "card": "pm_card_createDisputeInquiry",
     "sim_date": "2025-07-17", "label": "Acquirer inquiry, resolved",
     "outcome": "warning_only"},
    {"slug": "horizon-genomics", "amount": 48000, "card": "pm_card_createDispute",
     "sim_date": "2025-08-04", "label": "Customer disputed initial signup",
     "outcome": "submit_lost"},
    {"slug": "globex-software", "amount": 40000, "card": "pm_card_createDispute",
     "sim_date": "2025-09-29", "label": "Auto-renewal not noticed by AP",
     "outcome": "submit_won"},
    {"slug": "helio-energy", "amount": 90000, "card": "pm_card_createDispute",
     "sim_date": "2025-11-04", "label": "Suspected fraud, turned out legit",
     "outcome": "submit_won"},
    {"slug": "stellar-ai", "amount": 132000, "card": "pm_card_createDispute",
     "sim_date": "2025-12-11", "label": "Misattributed payment, AE traveling",
     "outcome": "refunded"},
    {"slug": "titan-marine", "amount": 33000, "card": "pm_card_createDisputeProductNotReceived",
     "sim_date": "2025-09-30", "label": "Delivery delay claim (logistics)",
     "outcome": "refunded"},
    {"slug": "meridian-tech", "amount": 26400, "card": "pm_card_createDispute",
     "sim_date": "2025-10-15", "label": "Standard plan card change issue",
     "outcome": "submit_won"},
    {"slug": "voyager-shipping", "amount": 72000, "card": "pm_card_createDisputeInquiry",
     "sim_date": "2026-02-22", "label": "Inquiry only, warning",
     "outcome": "warning_only"},
    {"slug": "delta-payments", "amount": 42000, "card": "pm_card_createDispute",
     "sim_date": "2026-03-02", "label": "Card-not-recognised dispute (CFO)",
     "outcome": "needs_response"},
    {"slug": "summit-payments", "amount": 42000, "card": "pm_card_createDisputeInquiry",
     "sim_date": "2026-04-17", "label": "Pre-arbitration inquiry",
     "outcome": "warning_only"},
    {"slug": "vertex-mining", "amount": 24000, "card": "pm_card_createDispute",
     "sim_date": "2026-04-30", "label": "Unauthorised transaction claim",
     "outcome": "needs_response"},
    {"slug": "globex-software", "amount": 40000, "card": "pm_card_createDispute",
     "sim_date": "2026-05-08", "label": "Card-not-recognised, AP team out",
     "outcome": "needs_response"},
    {"slug": "cascade-cloud", "amount": 78000, "card": "pm_card_createDisputeProductNotReceived",
     "sim_date": "2026-03-19", "label": "Service delivery delay",
     "outcome": "refunded"},
    {"slug": "cobra-cybersec", "amount": 60000, "card": "pm_card_createDispute",
     "sim_date": "2026-04-02", "label": "Auto-renew not noticed",
     "outcome": "submit_won"},
    {"slug": "hydra-finance", "amount": 54000, "card": "pm_card_createDispute",
     "sim_date": "2026-04-22", "label": "Fraud claim by APAC team",
     "outcome": "needs_response"},
    {"slug": "nexus-data", "amount": 96000, "card": "pm_card_createDisputeProductNotReceived",
     "sim_date": "2026-05-04", "label": "Migration outage compensation claim",
     "outcome": "refunded"},
    {"slug": "polaris-pay", "amount": 30000, "card": "pm_card_createDispute",
     "sim_date": "2026-05-12", "label": "CFO didn't recognise charge",
     "outcome": "needs_response"},
    {"slug": "bottega-romano", "amount": 14400, "card": "pm_card_createDispute",
     "sim_date": "2026-05-18", "label": "EU customer card-not-recognised",
     "outcome": "needs_response"},
    {"slug": "alchemy-foods", "amount": 18000, "card": "pm_card_createDisputeInquiry",
     "sim_date": "2026-04-05", "label": "Inquiry, customer didn't recall sub",
     "outcome": "warning_only"},
    {"slug": "orion-labs", "amount": 36000, "card": "pm_card_createDispute",
     "sim_date": "2026-03-08", "label": "Card update mid-cycle confusion",
     "outcome": "submit_won"},
    {"slug": "apex-software", "amount": 22000, "card": "pm_card_createDispute",
     "sim_date": "2026-02-19", "label": "Customer disputed Y2 renewal",
     "outcome": "submit_won"},
]


def seed_noise_disputes(sc_by_slug: dict[str, SeededCustomer]) -> list:
    log("\n== Noise disputes ==")
    out: list[dict] = []
    import time as _time
    for n, plan in enumerate(NOISE_DISPUTE_PLAN, start=1):
        sc = sc_by_slug.get(plan["slug"])
        if not sc:
            log(f"  ! skipping {plan['slug']}")
            continue

        # Skip if already seeded (by noise_label)
        if plan["label"] in _EXISTING_NOISE_DISPUTES:
            existing_id = _EXISTING_NOISE_DISPUTES[plan["label"]]
            try:
                disp = stripe.Dispute.retrieve(existing_id)
                log(f"  [reuse] noise#{n:2d} {sc.slug:20s} {plan['label']:40s} "
                    f"-> {disp.id} (status={disp.status})")
                out.append({"slug": sc.slug, "charge": disp.charge,
                            "dispute": disp.id,
                            "outcome": plan["outcome"]})
                continue
            except stripe.error.StripeError:
                pass

        try:
            unique_suffix = f"noise-disp-{n}-{int(_time.time())}"
            ch, disp = make_disputed_charge(
                sc=sc, amount_minor=plan["amount"],
                description=(
                    f"{sc.company.name} - {plan['label']} (sim {plan['sim_date']})."
                ),
                metadata={
                    "simulated_created_at": plan["sim_date"],
                    "charge_category": "noise_dispute",
                    "noise_label": plan["label"],
                    "expected_outcome": plan["outcome"],
                },
                dispute_test_card=plan["card"],
                idem_suffix=unique_suffix,
            )
        except Exception as e:
            log(f"  ! noise#{n} {plan['slug']}: {type(e).__name__}: {str(e)[:200]}")
            continue

        try:
            stripe.Dispute.modify(
                disp.id,
                metadata={
                    "noise": "true", "noise_label": plan["label"],
                    "simulated_created_at": plan["sim_date"],
                    "seeded_by": "manthan_seed_stripe",
                    "expected_outcome": plan["outcome"],
                },
            )
        except stripe.error.StripeError as e:
            log(f"    [modify-skip] {disp.id}: {str(e)[:80]}")

        outcome = plan["outcome"]
        try:
            if outcome == "refunded":
                # Stripe doesn't allow Refund.create on already-disputed
                # charges (the dispute funds-returned mechanism handles that).
                # Express "won-by-customer / refunded" via dispute metadata
                # plus closing the dispute as lost (concedes).
                stripe.Dispute.modify(
                    disp.id,
                    metadata={
                        "outcome": "refunded_via_dispute_concession",
                        "noise": "true",
                        "noise_label": plan["label"],
                        "simulated_created_at": plan["sim_date"],
                        "seeded_by": "manthan_seed_stripe",
                        "expected_outcome": "refunded",
                        "semantic_outcome": (
                            "Customer disputed and we conceded; funds returned."
                        ),
                    },
                )
                if plan["card"] != "pm_card_createDisputeInquiry":
                    try:
                        stripe.Dispute.close(disp.id)
                    except stripe.error.StripeError:
                        pass
            elif outcome == "submit_won":
                # NOTE: service_documentation / customer_communication / etc.
                # are file_upload fields in Stripe - don't pass strings there.
                # Only the *_text variants accept strings.
                stripe.Dispute.modify(
                    disp.id,
                    evidence={
                        "uncategorized_text": (
                            f"Noise dispute #{n}. Evidence submitted: valid "
                            f"charge, customer in error. Plan: "
                            f"{sc.company.plan}. Outreach attempted before "
                            f"chargeback; no response. Address-on-file matches "
                            f"charge. Auto-submitted for seed."
                        ),
                        "product_description": (
                            f"{sc.company.plan} subscription for "
                            f"{sc.company.name}"
                        ),
                        "billing_address": "Address on file matches charge",
                    },
                    submit=True,
                )
            elif outcome == "submit_lost":
                if plan["card"] != "pm_card_createDisputeInquiry":
                    stripe.Dispute.close(disp.id)
        except stripe.error.StripeError as e:
            log(f"    [outcome-branch] {sc.slug}/noise-{n} {outcome}: {str(e)[:120]}")

        try:
            d_final = stripe.Dispute.retrieve(disp.id)
            status_str = d_final.status
        except stripe.error.StripeError:
            status_str = "?"

        log(f"  noise#{n:2d} {sc.slug:20s} ${plan['amount'] / 100:7.2f} "
            f"-> {status_str:25s} (outcome={outcome})")
        out.append({"slug": sc.slug, "charge": ch.id, "dispute": disp.id,
                    "outcome": outcome})
    return out


INVOICE_PLAN = [
    ("stellar-ai", "Custom integration consulting (Q3 2025)", 1500000, "inv-stellar-1"),
    ("phoenix-fund", "Enterprise security review", 800000, "inv-phoenix-1"),
    ("solstice-care", "HIPAA compliance audit add-on", 600000, "inv-solstice-1"),
    ("zephyr-ventures", "White-glove onboarding service", 1200000, "inv-zephyr-1"),
    ("northwind-logi", "Custom data migration (one-time)", 750000, "inv-northwind-1"),
    ("helix-bio", "Migration assistance from legacy CRM", 450000, "inv-helix-1"),
    ("nexus-data", "Custom API webhook development", 950000, "inv-nexus-1"),
    ("helio-energy", "Custom dashboard build", 350000, "inv-helio-1"),
    ("cascade-cloud", "Performance optimization engagement", 500000, "inv-cascade-1"),
    ("voyager-shipping", "Custom report engineering", 280000, "inv-voyager-1"),
    ("cobra-cybersec", "SOC 2 evidence package", 420000, "inv-cobra-1"),
    ("hydra-finance", "Regional data residency setup", 380000, "inv-hydra-1"),
    ("summit-payments", "PCI compliance walkthrough", 250000, "inv-summit-1"),
    ("acme-genomics", "Data export tooling (March 2026 ask)", 180000, "inv-acme-gen-1"),
    ("mockingbird-media", "Post-acquisition migration audit", 320000, "inv-mockbird-1"),
    ("globex-software", "Multi-tenant rollout consulting", 280000, "inv-globex-sw-1"),
    ("delta-payments", "Custom invoice template", 120000, "inv-delta-1"),
    ("orion-labs", "Sandbox environment setup", 80000, "inv-orion-1"),
    ("apex-software", "Migration from competitor", 140000, "inv-apex-1"),
    ("horizon-genomics", "Pilot extension fee", 90000, "inv-horizon-1"),
]


def seed_one_off_invoices(sc_by_slug: dict[str, SeededCustomer]) -> list:
    log("\n== One-off invoices ==")
    out = []
    for slug, descr, amount, idem_suffix in INVOICE_PLAN:
        sc = sc_by_slug.get(slug)
        if not sc:
            continue
        try:
            safe_create(
                stripe.InvoiceItem.create,
                idem_key=idem("invitem", slug, idem_suffix),
                label=f"InvoiceItem[{slug}/{idem_suffix}]",
                customer=sc.customer_id, amount=amount, currency="usd",
                description=descr,
                metadata={
                    "slug": slug, "seeded_by": "manthan_seed_stripe",
                    "invoice_kind": "one_off_services",
                },
            )
            inv = safe_create(
                stripe.Invoice.create,
                idem_key=idem("inv", slug, idem_suffix),
                label=f"Invoice[{slug}/{idem_suffix}]",
                customer=sc.customer_id,
                collection_method="charge_automatically",
                description=descr,
                metadata={
                    "slug": slug, "seeded_by": "manthan_seed_stripe",
                    "invoice_kind": "one_off_services",
                    "billing_period_label": "one-off services",
                },
                auto_advance=True,
            )
            try:
                inv = stripe.Invoice.finalize_invoice(inv.id)
                if inv.status == "open":
                    try:
                        inv = stripe.Invoice.pay(inv.id)
                    except stripe.error.StripeError:
                        pass
            except stripe.error.StripeError as e:
                log(f"    [finalize-skip] {inv.id}: {str(e)[:80]}")
            out.append(inv.id)
            log(f"  invoice {slug:25s} ${amount / 100:8.2f} "
                f"status={inv.status} -> {inv.id}")
        except stripe.error.StripeError as e:
            log(f"  ! invoice {slug}/{idem_suffix} failed: "
                f"{e.user_message or str(e)[:120]}")
    return out


def main() -> None:
    log("== Manthan Stripe seeder ==")
    log(f"API key: {stripe.api_key[:14]}... (test mode)")
    log(f"Companies: {len(COMPANIES)}")

    ensure_products_and_prices()

    log("\n== Customers ==")
    sc_by_slug: dict[str, SeededCustomer] = {}
    for c in COMPANIES:
        sc = ensure_customer(c)
        sc_by_slug[c.slug] = sc
    log(f"  {len(sc_by_slug)} customers ensured")

    log("\n== Subscriptions ==")
    prefetch_existing_subs()
    sub_total = 0
    for c in COMPANIES:
        sc = sc_by_slug[c.slug]
        try:
            subs = ensure_subscriptions(sc)
            sub_total += len(subs)
            log(f"  {c.slug:24s} -> {len(subs)} sub(s)")
        except stripe.error.StripeError as e:
            log(f"  ! sub for {c.slug} failed: "
                f"{type(e).__name__}: {e.user_message or str(e)[:200]}")
    log(f"\n  total subs created/ensured: {sub_total}")

    log("\n== Historical charges ==")
    total_charges_created = 0
    for c in COMPANIES:
        sc = sc_by_slug[c.slug]
        try:
            n = generate_charge_history_for(sc)
            total_charges_created += n
            log(f"  {c.slug:24s} -> {n} charges")
        except stripe.error.StripeError as e:
            log(f"  ! charges for {c.slug} failed: "
                f"{type(e).__name__}: {e.user_message or str(e)[:200]}")
        except RuntimeError as e:
            log(f"  ! charges for {c.slug} runtime: {str(e)[:200]}")
    log(f"\n  total charges created: {total_charges_created}")

    refunds = seed_refunds(sc_by_slug)
    log(f"\n  total refunds: {len(refunds)}")

    invoices = seed_one_off_invoices(sc_by_slug)
    log(f"\n  total one-off invoices: {len(invoices)}")

    log("\n== Workflow signals ==")
    prefetch_existing_disputes()
    try:
        w1 = seed_w1_acme_genomics(sc_by_slug["acme-genomics"])
    except Exception as e:
        log(f"  ! W1 failed: {type(e).__name__}: {str(e)[:200]}")
        w1 = {"charges": [], "disputes": []}
    try:
        w2 = seed_w2_northwind(sc_by_slug["northwind-logi"])
    except Exception as e:
        log(f"  ! W2 failed: {type(e).__name__}: {str(e)[:200]}")
        w2 = {"charges": [], "disputes": []}
    try:
        w3 = seed_w3_mockingbird(sc_by_slug["mockingbird-media"])
    except Exception as e:
        log(f"  ! W3 failed: {type(e).__name__}: {str(e)[:200]}")
        w3 = {"charges": [], "disputes": []}

    noise_disp = seed_noise_disputes(sc_by_slug)
    print_summary(w1, w2, w3, noise_disp, sc_by_slug)


def print_summary(w1, w2, w3, noise_disp, sc_by_slug) -> None:
    log("\n" + "=" * 70)
    log("FINAL STRIPE TEST-MODE SUMMARY")
    log("=" * 70)

    all_custs = list(stripe.Customer.list(limit=100).auto_paging_iter())
    all_prods = list(stripe.Product.list(limit=100, active=None).auto_paging_iter())
    all_prices = list(stripe.Price.list(limit=100, active=None).auto_paging_iter())
    all_subs = list(stripe.Subscription.list(limit=100, status="all").auto_paging_iter())
    all_charges = list(stripe.Charge.list(limit=100).auto_paging_iter())
    all_invoices = list(stripe.Invoice.list(limit=100).auto_paging_iter())
    all_disputes = list(stripe.Dispute.list(limit=100).auto_paging_iter())
    all_refunds = list(stripe.Refund.list(limit=100).auto_paging_iter())

    seed_custs = [c for c in all_custs
                  if md_dict(c).get("seeded_by") == "manthan_seed_stripe"]
    seed_subs = [s for s in all_subs
                 if md_dict(s).get("seeded_by") == "manthan_seed_stripe"]

    sub_status = {}
    for s in seed_subs:
        sub_status[s.status] = sub_status.get(s.status, 0) + 1

    ch_status = {}
    disputed_ct = 0
    refunded_ct = 0
    for ch in all_charges:
        ch_status[ch.status] = ch_status.get(ch.status, 0) + 1
        if ch.disputed:
            disputed_ct += 1
        if ch.refunded or ch.amount_refunded:
            refunded_ct += 1
    ch_status["+disputed"] = disputed_ct
    ch_status["+refunded"] = refunded_ct

    disp_status = {}
    disp_reason = {}
    for d in all_disputes:
        disp_status[d.status] = disp_status.get(d.status, 0) + 1
        disp_reason[d.reason] = disp_reason.get(d.reason, 0) + 1

    log(f"\nCustomers     : {len(all_custs):4d}   (seed: {len(seed_custs)})")
    log(f"Products      : {len(all_prods):4d}")
    log(f"Prices        : {len(all_prices):4d}")
    log(f"Subscriptions : {len(all_subs):4d}   (seed: {len(seed_subs)})")
    log(f"  by status   : {sub_status}")
    log(f"Charges       : {len(all_charges):4d}")
    log(f"  by status   : {ch_status}")
    log(f"Invoices      : {len(all_invoices):4d}")
    log(f"Disputes      : {len(all_disputes):4d}")
    log(f"  by status   : {disp_status}")
    log(f"  by reason   : {disp_reason}")
    log(f"Refunds       : {len(all_refunds):4d}")

    log("\n--- WORKFLOW SIGNAL VERIFICATION ---")
    for wf, payload, target_slug in [
        ("W1", w1, "acme-genomics"),
        ("W2", w2, "northwind-logi"),
        ("W3", w3, "mockingbird-media"),
    ]:
        log(f"\n{wf}: target_slug={target_slug}")
        log(f"   charges : {payload['charges']}")
        log(f"   disputes: {payload['disputes']}")
        for disp_id in payload["disputes"]:
            try:
                d = stripe.Dispute.retrieve(disp_id)
                md = md_dict(d)
                log(f"     - {d.id} | reason={d.reason:25s} | "
                    f"status={d.status:25s} | amount={d.amount}")
                log(f"         workflow={md.get('workflow')} "
                    f"semantic={md.get('semantic_reason')}")
            except stripe.error.StripeError as e:
                log(f"     - {disp_id}: ERR {str(e)[:80]}")

    log(f"\n--- NOISE DISPUTES ({len(noise_disp)}) ---")
    by_outcome = {}
    for n in noise_disp:
        by_outcome[n["outcome"]] = by_outcome.get(n["outcome"], 0) + 1
    log(f"  outcome breakdown: {by_outcome}")
    log(f"  spread across {len({n['slug'] for n in noise_disp})} customers")
    log("\nSeeder done.")


if __name__ == "__main__":
    main()
