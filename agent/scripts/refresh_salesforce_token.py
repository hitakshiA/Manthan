"""Refresh Salesforce access token from the sf CLI's stored auth and
write the fresh values into agent/.env.

Salesforce access tokens expire (default 2h, configurable up to 24h via
Setup → Session Settings → Timeout Value). The sf CLI stores a long-
lived refresh-style auth under ~/.sf and can mint a fresh access token
on demand via `sf org display --json`.

Coral's salesforce manifest takes a static Bearer (no refresh), so we
run this helper before each bake / seed run to keep the token current.

Usage:
    .venv/bin/python scripts/refresh_salesforce_token.py
    .venv/bin/python scripts/refresh_salesforce_token.py --alias manthan-dev

Exit 0 on success; 1 if sf CLI auth is missing or stale (re-run
`sf org login web --alias manthan-dev` in that case).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def fetch_creds(alias: str) -> dict:
    """Call sf CLI to fetch current access token + instance URL."""
    proc = subprocess.run(
        ["sf", "org", "display", "--target-org", alias, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            f"sf CLI returned {proc.returncode}.\n"
            f"stderr: {proc.stderr.strip()}\n"
            f"Re-auth with: sf org login web --alias {alias}\n"
        )
        sys.exit(1)
    payload = json.loads(proc.stdout)
    if payload.get("status") != 0:
        sys.stderr.write(f"sf CLI status != 0: {payload}\n")
        sys.exit(1)
    result = payload["result"]
    if not result.get("accessToken") or not result.get("instanceUrl"):
        sys.stderr.write(
            f"sf CLI didn't return accessToken/instanceUrl. Got: {result}\n"
        )
        sys.exit(1)
    return result


def update_env(instance_url: str, access_token: str) -> None:
    """Rewrite SALESFORCE_API_URL and SALESFORCE_ACCESS_TOKEN lines in .env.

    Fails ONLY if the lines don't exist at all (caller needs to add them).
    Successfully writes the values even if they're unchanged from prior run.
    """
    text = ENV_PATH.read_text()

    if not re.search(r"^SALESFORCE_API_URL=", text, flags=re.MULTILINE):
        sys.stderr.write(
            "SALESFORCE_API_URL= line missing from .env. Add it (empty value "
            "is fine) and rerun.\n"
        )
        sys.exit(1)
    if not re.search(r"^SALESFORCE_ACCESS_TOKEN=", text, flags=re.MULTILINE):
        sys.stderr.write(
            "SALESFORCE_ACCESS_TOKEN= line missing from .env. Add it (empty "
            "value is fine) and rerun.\n"
        )
        sys.exit(1)

    new_text = re.sub(
        r"^SALESFORCE_API_URL=.*$",
        f"SALESFORCE_API_URL={instance_url}",
        text,
        flags=re.MULTILINE,
    )
    new_text = re.sub(
        r"^SALESFORCE_ACCESS_TOKEN=.*$",
        f"SALESFORCE_ACCESS_TOKEN={access_token}",
        new_text,
        flags=re.MULTILINE,
    )
    ENV_PATH.write_text(new_text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alias", default="manthan-dev")
    args = parser.parse_args()

    creds = fetch_creds(args.alias)
    update_env(creds["instanceUrl"], creds["accessToken"])

    print(
        f"Refreshed Salesforce auth for alias={args.alias}\n"
        f"  username    : {creds.get('username')}\n"
        f"  org id      : {creds.get('id')}\n"
        f"  instance url: {creds['instanceUrl']}\n"
        f"  token prefix: {creds['accessToken'][:24]}...\n"
        f"  written to  : {ENV_PATH}"
    )


if __name__ == "__main__":
    main()
