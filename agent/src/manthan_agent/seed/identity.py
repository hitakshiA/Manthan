"""Canonical company identity used across every source.

The same `slug` resolves to the same identifiable company in Stripe
metadata, HubSpot company records, Slack channel names, Intercom contact
attributes, Notion page titles, etc. The seeders embed
`manthan:<slug>` in whatever metadata field the source provides so
re-running a seeder is idempotent - the seeder finds the existing record
by marker rather than creating a duplicate.

Slugs are kebab-case and stable across runs. Don't rename them once a
scenario references them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompanyIdentity:
    """A seeded company. One per scenario, sometimes shared across scenarios.

    `domain` is used as the .example email-domain for all generated emails
    (RFC-2606 .example is reserved for documentation/seeding and won't
    accidentally hit a real inbox).
    """

    slug: str               # kebab-case, stable
    name: str               # display name
    domain: str             # base email/web domain (use .example tld)
    industry: str           # short label, free-form
    size: str               # "smb" | "mid-market" | "enterprise"
    arr_usd: int            # current ARR in USD (integer for simplicity)
    signup_date: str        # ISO YYYY-MM-DD
    primary_billing_name: str = field(default="Billing Contact")
    csm_email: str = field(default="")  # empty = CSM-less

    def __post_init__(self) -> None:
        # Light defensive checks. Loud rather than silent.
        if "/" in self.slug or " " in self.slug:
            raise ValueError(f"slug must be kebab-case, got {self.slug!r}")
        if not self.domain.endswith(".example"):
            # We *insist* on .example so seeding never sends mail to a
            # real human, even if a misconfigured webhook fires.
            raise ValueError(
                f"domain must end in .example (RFC 2606), got {self.domain!r}"
            )

    # ------------------------------------------------------------ helpers

    @property
    def primary_billing_email(self) -> str:
        return f"billing@{self.domain}"

    @property
    def csm_handoff_email(self) -> str:
        return f"cs@{self.domain}"

    @property
    def slack_channel(self) -> str:
        """Convention: every seeded company has a #acct-<slug> channel."""
        return f"acct-{self.slug}"

    @property
    def manthan_marker(self) -> str:
        """Idempotency marker embedded in every record this identity touches.

        Seeders that support metadata (Stripe, HubSpot, Intercom, Linear,
        Notion props) write this into `metadata.manthan_scenario_company`
        (or the source's nearest equivalent). On re-run, the seeder
        looks up by this marker and updates instead of duplicating.
        """
        return f"manthan:{self.slug}"
