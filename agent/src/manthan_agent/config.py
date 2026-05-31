"""Runtime config loaded from environment variables.

Single source of truth. Other modules accept a Config and never read
os.environ directly. Tests pass a hand-built Config.

Source coverage: 30 sources across payments, CRM, support, comms, docs,
email (transactional + marketing), SMS, auth, meetings, analytics,
engineering, incidents, observability, infrastructure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the agent root if present.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


@dataclass(frozen=True, slots=True)
class Config:
    # ── LLM ─────────────────────────────────────────────────────────
    openrouter_api_key: str | None
    model: str

    # ── Coral ───────────────────────────────────────────────────────
    coral_binary: str

    # ── Payments ────────────────────────────────────────────────────
    stripe_api_key: str | None
    chargebee_site: str | None
    chargebee_api_key: str | None
    razorpay_key_id: str | None
    razorpay_key_secret: str | None

    # ── CRM ─────────────────────────────────────────────────────────
    hubspot_access_token: str | None
    salesforce_instance_url: str | None
    salesforce_access_token: str | None

    # ── Support ─────────────────────────────────────────────────────
    intercom_access_token: str | None
    zendesk_subdomain: str | None
    zendesk_user_email_with_token: str | None
    zendesk_api_token: str | None

    # ── Internal comms / docs ───────────────────────────────────────
    slack_bot_token: str | None
    notion_api_key: str | None
    confluence_base_url: str | None
    confluence_email: str | None
    confluence_api_token: str | None

    # ── Google OAuth (one app powers gmail + drive) ─────────────────
    google_oauth_client_id: str | None
    google_oauth_client_secret: str | None
    gmail_access_token: str | None
    gmail_refresh_token: str | None
    google_drive_access_token: str | None
    google_drive_refresh_token: str | None

    # ── Transactional email ─────────────────────────────────────────
    postmark_server_token: str | None
    resend_api_key: str | None

    # ── Marketing email ─────────────────────────────────────────────
    mailchimp_api_key: str | None
    mailchimp_server_prefix: str | None
    loops_api_key: str | None

    # ── SMS ─────────────────────────────────────────────────────────
    twilio_account_sid: str | None
    twilio_api_key: str | None
    twilio_api_key_secret: str | None

    # ── Auth / identity ─────────────────────────────────────────────
    clerk_secret_key: str | None

    # ── Meetings ────────────────────────────────────────────────────
    cal_api_key: str | None
    cal_base_url: str

    # ── Product analytics ───────────────────────────────────────────
    posthog_api_key: str | None
    posthog_host: str
    mixpanel_project_id: str | None
    mixpanel_service_account_username: str | None
    mixpanel_service_account_secret: str | None
    mixpanel_base_url: str

    # ── Engineering ─────────────────────────────────────────────────
    linear_api_key: str | None
    github_token: str | None
    sentry_auth_token: str | None
    sentry_org: str | None
    launchdarkly_token: str | None
    launchdarkly_api_base: str

    # ── Incidents / status / observability ──────────────────────────
    pagerduty_api_token: str | None
    statusgator_api_token: str | None
    dd_site: str
    dd_api_key: str | None
    dd_application_key: str | None
    grafana_url: str | None
    grafana_token: str | None

    # ── Infrastructure ──────────────────────────────────────────────
    k8s_base_url: str | None


def _env(name: str) -> str | None:
    """Read an env var, treating empty string as missing."""
    value = os.environ.get(name)
    return value if value else None


def load() -> Config:
    """Read env vars once. Reuse the returned Config across the process."""
    return Config(
        openrouter_api_key=_env("OPENROUTER_API_KEY"),
        model=_env("MANTHAN_MODEL") or "deepseek/deepseek-v4-pro:exacto",
        coral_binary=_env("CORAL_BINARY") or "coral",
        # Payments
        stripe_api_key=_env("STRIPE_API_KEY"),
        chargebee_site=_env("CHARGEBEE_SITE"),
        chargebee_api_key=_env("CHARGEBEE_API_KEY"),
        razorpay_key_id=_env("RAZORPAY_KEY_ID"),
        razorpay_key_secret=_env("RAZORPAY_KEY_SECRET"),
        # CRM
        hubspot_access_token=_env("HUBSPOT_ACCESS_TOKEN"),
        salesforce_instance_url=_env("SALESFORCE_INSTANCE_URL"),
        salesforce_access_token=_env("SALESFORCE_ACCESS_TOKEN"),
        # Support
        intercom_access_token=_env("INTERCOM_ACCESS_TOKEN"),
        zendesk_subdomain=_env("ZENDESK_SUBDOMAIN"),
        zendesk_user_email_with_token=_env("ZENDESK_USER_EMAIL_WITH_TOKEN"),
        zendesk_api_token=_env("ZENDESK_API_TOKEN"),
        # Internal comms / docs
        slack_bot_token=_env("SLACK_BOT_TOKEN"),
        notion_api_key=_env("NOTION_API_KEY"),
        confluence_base_url=_env("CONFLUENCE_BASE_URL"),
        confluence_email=_env("CONFLUENCE_EMAIL"),
        confluence_api_token=_env("CONFLUENCE_API_TOKEN"),
        # Google OAuth
        google_oauth_client_id=_env("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        gmail_access_token=_env("GMAIL_ACCESS_TOKEN"),
        gmail_refresh_token=_env("GMAIL_REFRESH_TOKEN"),
        google_drive_access_token=_env("GOOGLE_DRIVE_ACCESS_TOKEN"),
        google_drive_refresh_token=_env("GOOGLE_DRIVE_REFRESH_TOKEN"),
        # Transactional email
        postmark_server_token=_env("POSTMARK_SERVER_TOKEN"),
        resend_api_key=_env("RESEND_API_KEY"),
        # Marketing email
        mailchimp_api_key=_env("MAILCHIMP_API_KEY"),
        mailchimp_server_prefix=_env("MAILCHIMP_SERVER_PREFIX"),
        loops_api_key=_env("LOOPS_API_KEY"),
        # SMS
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
        twilio_api_key=_env("TWILIO_API_KEY"),
        twilio_api_key_secret=_env("TWILIO_API_KEY_SECRET"),
        # Auth
        clerk_secret_key=_env("CLERK_SECRET_KEY"),
        # Meetings
        cal_api_key=_env("CAL_API_KEY"),
        cal_base_url=_env("CAL_BASE_URL") or "https://api.cal.com/v2",
        # Product analytics
        posthog_api_key=_env("POSTHOG_API_KEY"),
        posthog_host=_env("POSTHOG_HOST") or "https://us.posthog.com",
        mixpanel_project_id=_env("MIXPANEL_PROJECT_ID"),
        mixpanel_service_account_username=_env("MIXPANEL_SERVICE_ACCOUNT_USERNAME"),
        mixpanel_service_account_secret=_env("MIXPANEL_SERVICE_ACCOUNT_SECRET"),
        mixpanel_base_url=_env("MIXPANEL_BASE_URL") or "https://mixpanel.com/api",
        # Engineering
        linear_api_key=_env("LINEAR_API_KEY"),
        github_token=_env("GITHUB_TOKEN"),
        sentry_auth_token=_env("SENTRY_AUTH_TOKEN"),
        sentry_org=_env("SENTRY_ORG"),
        launchdarkly_token=_env("LAUNCHDARKLY_TOKEN"),
        launchdarkly_api_base=_env("LAUNCHDARKLY_API_BASE") or "https://app.launchdarkly.com/api/v2",
        # Incidents / status / observability
        pagerduty_api_token=_env("PAGERDUTY_API_TOKEN"),
        statusgator_api_token=_env("STATUSGATOR_API_TOKEN"),
        dd_site=_env("DD_SITE") or "datadoghq.com",
        dd_api_key=_env("DD_API_KEY"),
        dd_application_key=_env("DD_APPLICATION_KEY"),
        grafana_url=_env("GRAFANA_URL"),
        grafana_token=_env("GRAFANA_TOKEN"),
        # Infrastructure
        k8s_base_url=_env("K8S_BASE_URL"),
    )


def configured_sources(cfg: Config) -> list[str]:
    """Return the list of source names that have all required credentials.

    A source is "configured" when its minimum-required env vars are all
    present. We don't try to ping the source - that's the seeder's job.
    """
    checks: dict[str, bool] = {
        # Payments
        "stripe": bool(cfg.stripe_api_key),
        "chargebee": bool(cfg.chargebee_site and cfg.chargebee_api_key),
        "razorpay": bool(cfg.razorpay_key_id and cfg.razorpay_key_secret),
        # CRM
        "hubspot": bool(cfg.hubspot_access_token),
        "salesforce": bool(
            cfg.salesforce_instance_url and cfg.salesforce_access_token
        ),
        # Support
        "intercom": bool(cfg.intercom_access_token),
        "zendesk": bool(
            cfg.zendesk_subdomain
            and cfg.zendesk_user_email_with_token
            and cfg.zendesk_api_token
        ),
        # Internal / docs
        "slack": bool(cfg.slack_bot_token),
        "notion": bool(cfg.notion_api_key),
        "confluence": bool(
            cfg.confluence_base_url and cfg.confluence_email and cfg.confluence_api_token
        ),
        # Google
        "gmail": bool(cfg.gmail_access_token),
        "google_drive": bool(cfg.google_drive_access_token),
        # Email
        "postmark": bool(cfg.postmark_server_token),
        "resend": bool(cfg.resend_api_key),
        "mailchimp": bool(cfg.mailchimp_api_key and cfg.mailchimp_server_prefix),
        "loops": bool(cfg.loops_api_key),
        # SMS
        "twilio": bool(
            cfg.twilio_account_sid
            and cfg.twilio_api_key
            and cfg.twilio_api_key_secret
        ),
        # Auth
        "clerk": bool(cfg.clerk_secret_key),
        # Meetings
        "cal": bool(cfg.cal_api_key),
        # Analytics
        "posthog": bool(cfg.posthog_api_key),
        "mixpanel": bool(
            cfg.mixpanel_project_id
            and cfg.mixpanel_service_account_username
            and cfg.mixpanel_service_account_secret
        ),
        # Engineering
        "linear": bool(cfg.linear_api_key),
        "github": bool(cfg.github_token),
        "sentry": bool(cfg.sentry_auth_token and cfg.sentry_org),
        "launchdarkly": bool(cfg.launchdarkly_token),
        # Incidents / observability
        "pagerduty": bool(cfg.pagerduty_api_token),
        "statusgator": bool(cfg.statusgator_api_token),
        "datadog": bool(cfg.dd_api_key and cfg.dd_application_key),
        "grafana": bool(cfg.grafana_url and cfg.grafana_token),
        # Infrastructure
        "k8s": bool(cfg.k8s_base_url),
    }
    return [name for name, ok in checks.items() if ok]
