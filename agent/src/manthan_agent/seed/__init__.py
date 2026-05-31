"""Seed module: realistic scenarios + per-source seeders.

Layout:
- identity.py    - CompanyIdentity dataclass. One canonical company-identity
                   that every seeder uses so the same "Northstar Logistics"
                   is identifiable across Stripe + HubSpot + Slack + ...
- scenarios.py   - Scenario dataclass + ~5 fully-specified scenarios from
                   research/billing_ops_cases.md.
- base.py        - common helpers: idempotency markers, console output,
                   phase timing.
- stripe.py, hubspot.py, ... - per-source seeders. Written as keys land.

Every scenario maps to exactly one case in
`research/billing_ops_cases.md`. Each is grounded in a public source.
"""

from .identity import CompanyIdentity
from .scenarios import SCENARIOS, Scenario, scenario_by_id, scenarios_for_source

__all__ = [
    "SCENARIOS",
    "CompanyIdentity",
    "Scenario",
    "scenario_by_id",
    "scenarios_for_source",
]
