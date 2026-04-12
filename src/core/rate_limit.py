"""IP-based rate limiting with whitelist for Layer 2/3 servers.

Uses slowapi (built on limits + redis/memory backend). Whitelisted IPs
bypass all rate limits — this is where you put your Layer 2 and Layer 3
server IPs so they get full-speed access while unknown clients are
throttled.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter

# IPs that bypass rate limits entirely
WHITELISTED_IPS: set[str] = {
    "127.0.0.1",
    "::1",
    "localhost",
}


def get_real_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _rate_limit_key(request: Request) -> str:
    """Whitelisted IPs get a shared exempt key; others get their real IP."""
    ip = get_real_ip(request)
    if ip in WHITELISTED_IPS:
        return "__whitelisted__"
    return ip


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["60/minute"],
)
