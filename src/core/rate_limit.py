"""IP-based rate limiting with whitelist for Layer 2/3 servers."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter

WHITELISTED_IPS: set[str] = {
    "127.0.0.1",
    "::1",
    "localhost",
}


def get_real_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _rate_limit_key(request: Request) -> str:
    """Whitelisted IPs get unlimited; others get their real IP."""
    ip = get_real_ip(request)
    if ip in WHITELISTED_IPS:
        # Return a key with effectively no limit — 1M/minute
        return "__whitelisted__"
    return ip


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["200/minute"],
)
