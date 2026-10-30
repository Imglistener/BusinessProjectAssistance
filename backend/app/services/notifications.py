"""In-app notifications. Callers stage them in the current session; the request's commit saves them.

Rules: never notify people about their own actions, and only notify active members of the organization.
"""
from __future__ import annotations

from typing import Iterable

from ..extensions import db
from ..models import Notification, OrganizationMember, Role


def notify(
    *,
    organization_id: int,
    user_ids: Iterable[int | None],
    actor_id: int | None,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> int:
    targets = {u for u in user_ids if u and u != actor_id}
    if not targets:
        return 0
    active = {
        m.user_id
        for m in OrganizationMember.query.filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
            OrganizationMember.user_id.in_(targets),
        )
    }
    for user_id in sorted(active):
        db.session.add(
            Notification(
                user_id=user_id,
                organization_id=organization_id,
                kind=kind,
                title=title[:200],
                body=body[:500] if body else None,
                link=link,
            )
        )
    return len(active)


def human_date(d) -> str:
    """8 Nov 2026 (portable: no platform-specific strftime flags)."""
    return f"{d.day} {d.strftime('%b %Y')}"


def members_with_roles(organization_id: int, *roles: Role) -> list[int]:
    return [
        m.user_id
        for m in OrganizationMember.query.filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
            OrganizationMember.role.in_(roles),
        )
    ]
