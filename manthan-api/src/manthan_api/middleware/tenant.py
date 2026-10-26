"""Multi-tenant request context.

Resolves the (member, org) pair on every authenticated request.
Two modes:
  - Clerk JWT in `Authorization: Bearer ...` (production).
  - Dev bypass header `X-Manthan-Dev-Org: <org_slug>` (local development).

The resolved context lives in `request.state.ctx` so endpoint handlers
can access it via `Depends(get_ctx)`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request, status

from manthan_api.config import get_settings
from manthan_api.db import get_conn


def _personal_org_slug(email: str) -> str:
    """Deterministic per-user org slug. Stable across logins, doesn't
    leak the email into URLs. e.g. 'usr-a1b2c3d4e5'."""
    h = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    return f"usr-{h[:10]}"


def _derive_name_from_email(email: str) -> str:
    """Pretty display name from email local-part.
    'alice.smith+work@x.com' → 'Alice Smith'."""
    local = email.split("@", 1)[0]
    derived = (
        local.split("+", 1)[0]
        .replace(".", " ")
        .replace("_", " ")
        .replace("-", " ")
        .title()
        .strip()
    )
    return derived or local


@dataclass(slots=True, frozen=True)
class TenantCtx:
    org_id: UUID
    org_slug: str
    member_id: UUID
    member_email: str
    member_role: str


async def resolve_tenant(request: Request) -> TenantCtx:
    """Pull the tenant context off the request, raising 401 if absent."""
    settings = get_settings()

    # Dev bypass: header or ?dev_org= query string sets the org by slug.
    # Query string allowed because EventSource (SSE) can't send headers.
    dev_slug = request.headers.get("x-manthan-dev-org") or request.query_params.get("dev_org")
    if dev_slug and settings.is_dev:
        # Per-request identity override: the frontend forwards the
        # signed-in Clerk user's email via `X-Manthan-Dev-Email` (or
        # `dev_email` query param for SSE EventSource, which can't set
        # headers). When present, we route the user to their OWN
        # personal org (created on first sign-in, addressed by a
        # deterministic email-hash slug), giving each Clerk user a
        # fully-isolated workspace. The shared `acme` org is only used
        # as a fallback for requests that arrive before Clerk has
        # resolved (e.g. SSE during initial page load).
        dev_email = (
            request.headers.get("x-manthan-dev-email")
            or request.query_params.get("dev_email")
        )
        async with get_conn() as conn:
            row = None
            if dev_email:
                personal_slug = _personal_org_slug(dev_email)
                derived_name = _derive_name_from_email(dev_email)
                workspace_name = f"{derived_name}'s workspace"
                async with conn.transaction():
                    # Find-or-create the personal org. Slug is
                    # deterministic per email, so the INSERT collides
                    # cleanly on the slug UNIQUE constraint on repeat
                    # logins (DO NOTHING keeps the first-write
                    # workspace name).
                    await conn.execute(
                        """
                        INSERT INTO orgs (slug, name, plan)
                        VALUES ($1, $2, 'workspace')
                        ON CONFLICT (slug) DO NOTHING
                        """,
                        personal_slug, workspace_name,
                    )
                    org_row = await conn.fetchrow(
                        "SELECT id FROM orgs WHERE slug=$1", personal_slug,
                    )
                    # Find-or-create the admin member for this user.
                    if org_row is not None:
                        await conn.execute(
                            """
                            INSERT INTO members (org_id, email, name, role, approval_limit_minor)
                            VALUES ($1, $2, $3, 'admin', 100000000)
                            ON CONFLICT (org_id, email) DO NOTHING
                            """,
                            org_row["id"], dev_email, derived_name,
                        )
                row = await conn.fetchrow(
                    """
                    SELECT o.id AS org_id, o.slug AS org_slug,
                           m.id AS member_id, m.email AS member_email, m.role AS member_role
                    FROM orgs o
                    JOIN members m ON m.org_id = o.id
                    WHERE o.slug = $1 AND lower(m.email) = lower($2)
                    LIMIT 1
                    """,
                    personal_slug, dev_email,
                )
            if row is None:
                # Fallback: no dev_email provided (e.g. unauthenticated
                # SSE during initial page load) - fall back to the
                # seeded oldest admin in the requested dev_slug org so
                # the request still succeeds. Unauthenticated requests
                # land in the shared seed org; once Clerk loads + the
                # frontend reconnects with the identity header, the
                # user gets routed to their personal org.
                row = await conn.fetchrow(
                    """
                    SELECT o.id AS org_id, o.slug AS org_slug,
                           m.id AS member_id, m.email AS member_email, m.role AS member_role
                    FROM orgs o
                    JOIN members m ON m.org_id = o.id AND m.role = 'admin'
                    WHERE o.slug = $1
                    ORDER BY m.created_at ASC
                    LIMIT 1
                    """,
                    dev_slug,
                )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"dev org not found: {dev_slug}",
            )
        return TenantCtx(
            org_id=row["org_id"],
            org_slug=row["org_slug"],
            member_id=row["member_id"],
            member_email=row["member_email"],
            member_role=row["member_role"],
        )

    # Production path: Clerk JWT.
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization bearer token",
        )

    # TODO: verify Clerk JWT, extract clerk_user_id, lookup member by clerk_user_id.
    # For now we raise a clear "not implemented" so the integration path is obvious.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Clerk verification not wired yet - use X-Manthan-Dev-Org for local dev",
    )


async def get_ctx(request: Request) -> TenantCtx:
    """FastAPI dependency: returns the resolved tenant context."""
    ctx = getattr(request.state, "ctx", None)
    if ctx is None:
        ctx = await resolve_tenant(request)
        request.state.ctx = ctx
    return ctx
