"""Identity - current member + org context.

Used by the UI to render the sidebar user widget, Settings page, and
Workspace owner field. Reads from the resolved TenantCtx (Clerk JWT in
prod, X-Manthan-Dev-Org bypass in dev).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from manthan_api.db import get_conn
from manthan_api.middleware.tenant import TenantCtx, get_ctx

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def me(ctx: TenantCtx = Depends(get_ctx)) -> dict:
    """Return the current member + org context."""
    async with get_conn() as conn:
        org = await conn.fetchrow(
            "SELECT id, slug, name, created_at, plan FROM orgs WHERE id=$1",
            ctx.org_id,
        )
        member_count = await conn.fetchval(
            "SELECT count(*) FROM members WHERE org_id=$1",
            ctx.org_id,
        )

    return {
        "org": {
            "id": str(ctx.org_id),
            "slug": ctx.org_slug,
            "name": (org["name"] if org else ctx.org_slug.title()),
            "plan": (org["plan"] if org else "demo"),
            "created_at": org["created_at"].isoformat() if org else None,
            "member_count": member_count or 1,
        },
        "member": {
            "id": str(ctx.member_id),
            "email": ctx.member_email,
            "role": ctx.member_role,
            # Derive a 2-letter display avatar from the email.
            "initials": _initials_for(ctx.member_email),
            "display_name": _display_for(ctx.member_email),
        },
    }


def _initials_for(email: str) -> str:
    local = email.split("@", 1)[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (local[:2] or "??").upper()


def _display_for(email: str) -> str:
    local = email.split("@", 1)[0]
    parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return email
    return " ".join(p.capitalize() for p in parts)
