"""Organization membership: link-based invitations, role changes and removal (FR-02).

There is no email provider yet, so the owner shares the invite link themselves. The link only
works for the account whose email it was issued to, and expires after INVITE_TTL.
"""
from __future__ import annotations

from datetime import timedelta

from flask import jsonify
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Organization, OrganizationInvitation, OrganizationMember, Role, User, utcnow
from ..services.audit import log_action
from ..services.email import app_link, invitation_email, send_email
from ..services.permissions import ORG_ADMIN_ROLES, get_membership, require_role
from ..services.tokens import aware as _aware, hash_token as _hash, new_token
from . import api_bp
from .auth import EMAIL_RE, current_user
from .organizations import org_to_dict
from .validation import get_json_body, parse_enum, require_str

INVITE_TTL = timedelta(days=7)
# System administrators are not invited through the app.
INVITABLE_ROLES = (Role.OWNER, Role.PROJECT_MANAGER, Role.CONTRIBUTOR, Role.VIEWER)
ROLE_LABELS = {
    Role.OWNER: "an owner",
    Role.PROJECT_MANAGER: "a project manager",
    Role.CONTRIBUTOR: "a contributor",
    Role.VIEWER: "a viewer",
}


def _state(inv: OrganizationInvitation) -> str:
    if inv.status == "pending" and _aware(inv.expires_at) <= utcnow():
        return "expired"
    return inv.status


def invitation_to_dict(inv: OrganizationInvitation) -> dict:
    return {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role.value,
        "state": _state(inv),
        "created_at": _aware(inv.created_at).isoformat(),
        "expires_at": _aware(inv.expires_at).isoformat(),
    }


def _parse_role(data: dict) -> Role:
    role = parse_enum(data, "role", Role)
    if role is None or role not in INVITABLE_ROLES:
        allowed = ", ".join(r.value for r in INVITABLE_ROLES)
        raise ApiError("validation_error", f"Role must be one of: {allowed}.", 400, {"field": "role"})
    return role


def _active_owner_count(org_id: int) -> int:
    return OrganizationMember.query.filter_by(organization_id=org_id, role=Role.OWNER, status="active").count()


def _target_member(org_id: int, user_id: int) -> OrganizationMember:
    member = OrganizationMember.query.filter_by(organization_id=org_id, user_id=user_id, status="active").first()
    if member is None:
        raise ApiError("not_found", "Member not found.", 404)
    return member


def _guard_last_owner(member: OrganizationMember) -> None:
    if member.role == Role.OWNER and _active_owner_count(member.organization_id) <= 1:
        raise ApiError(
            "last_owner", "Every organization needs an owner. Make someone else an owner first.", 409
        )


# ---------- members ----------


@api_bp.get("/organizations/<int:org_id>/members")
@jwt_required()
def list_members(org_id: int):
    """Active members. Emails are shown only to people who manage members."""
    user = current_user()
    membership = get_membership(org_id, user.id)
    show_email = membership.role in ORG_ADMIN_ROLES
    rows = (
        db.session.query(User, OrganizationMember)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(OrganizationMember.organization_id == org_id, OrganizationMember.status == "active")
        .order_by(User.first_name, User.last_name, User.id)
        .all()
    )
    members = []
    for u, m in rows:
        row = {"user_id": u.id, "name": f"{u.first_name} {u.last_name}", "role": m.role.value}
        if show_email:
            row["email"] = u.email
        members.append(row)
    return jsonify(members=members)


@api_bp.patch("/organizations/<int:org_id>/members/<int:user_id>")
@jwt_required()
def change_member_role(org_id: int, user_id: int):
    user = current_user()
    require_role(get_membership(org_id, user.id), *ORG_ADMIN_ROLES)
    member = _target_member(org_id, user_id)
    role = _parse_role(get_json_body())

    if role != member.role:
        if role != Role.OWNER:
            _guard_last_owner(member)
        old = member.role
        member.role = role
        log_action(
            organization_id=org_id,
            actor_id=user.id,
            action="member.role_changed",
            entity_type="organization_member",
            entity_id=member.id,
            meta={"user_id": user_id, "role": [old.value, role.value]},
        )
        db.session.commit()
    return jsonify(member={"user_id": user_id, "role": member.role.value})


@api_bp.post("/organizations/<int:org_id>/members/<int:user_id>/remove")
@jwt_required()
def remove_member(org_id: int, user_id: int):
    """Owners remove anyone; everyone else may only leave. The membership row is kept, marked removed."""
    user = current_user()
    membership = get_membership(org_id, user.id)
    if user_id != user.id:
        require_role(membership, *ORG_ADMIN_ROLES)
    member = _target_member(org_id, user_id)
    _guard_last_owner(member)

    member.status = "removed"
    log_action(
        organization_id=org_id,
        actor_id=user.id,
        action="member.left" if user_id == user.id else "member.removed",
        entity_type="organization_member",
        entity_id=member.id,
        meta={"user_id": user_id, "role": member.role.value},
    )
    db.session.commit()
    return jsonify(ok=True)


# ---------- invitations (owner side) ----------


@api_bp.post("/organizations/<int:org_id>/invitations")
@jwt_required()
def create_invitation(org_id: int):
    user = current_user()
    require_role(get_membership(org_id, user.id), *ORG_ADMIN_ROLES)
    data = get_json_body()
    email = require_str(data, "email").lower()
    if not EMAIL_RE.match(email):
        raise ApiError("validation_error", "Invalid email address.", 400, {"field": "email"})
    role = _parse_role(data)

    already = (
        db.session.query(OrganizationMember.id)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(OrganizationMember.organization_id == org_id, OrganizationMember.status == "active", User.email == email)
        .first()
    )
    if already:
        raise ApiError("already_member", "This person is already a member.", 409, {"field": "email"})

    # A new invite replaces any earlier pending one for the same address.
    OrganizationInvitation.query.filter_by(organization_id=org_id, email=email, status="pending").update(
        {"status": "revoked"}
    )
    token = new_token()
    inv = OrganizationInvitation(
        organization_id=org_id,
        email=email,
        role=role,
        token_hash=_hash(token),
        invited_by=user.id,
        status="pending",
        expires_at=utcnow() + INVITE_TTL,
    )
    db.session.add(inv)
    db.session.flush()
    log_action(
        organization_id=org_id,
        actor_id=user.id,
        action="member.invited",
        entity_type="organization_invitation",
        entity_id=inv.id,
        meta={"email": email, "role": role.value},
    )
    db.session.commit()
    org = db.session.get(Organization, org_id)
    emailed = send_email(
        invitation_email(email, user.first_name, org.name, ROLE_LABELS[role], app_link(f"/invite/{token}")),
        idempotency_key=f"invitation/{inv.id}",
    )
    # The token is returned this once (so the owner can also share the link); only its hash is stored.
    return jsonify(invitation=invitation_to_dict(inv), token=token, emailed=emailed), 201


@api_bp.get("/organizations/<int:org_id>/invitations")
@jwt_required()
def list_invitations(org_id: int):
    user = current_user()
    require_role(get_membership(org_id, user.id), *ORG_ADMIN_ROLES)
    invs = (
        OrganizationInvitation.query.filter_by(organization_id=org_id, status="pending")
        .order_by(OrganizationInvitation.created_at.desc(), OrganizationInvitation.id.desc())
        .all()
    )
    return jsonify(invitations=[invitation_to_dict(i) for i in invs])


@api_bp.post("/organizations/<int:org_id>/invitations/<int:invitation_id>/revoke")
@jwt_required()
def revoke_invitation(org_id: int, invitation_id: int):
    user = current_user()
    require_role(get_membership(org_id, user.id), *ORG_ADMIN_ROLES)
    inv = OrganizationInvitation.query.filter_by(id=invitation_id, organization_id=org_id).first()
    if inv is None:
        raise ApiError("not_found", "Invitation not found.", 404)
    if inv.status == "pending":
        inv.status = "revoked"
        log_action(
            organization_id=org_id,
            actor_id=user.id,
            action="invitation.revoked",
            entity_type="organization_invitation",
            entity_id=inv.id,
            meta={"email": inv.email},
        )
        db.session.commit()
    return jsonify(invitation=invitation_to_dict(inv))


# ---------- invitations (invitee side) ----------


def _by_token(token: str) -> OrganizationInvitation:
    inv = OrganizationInvitation.query.filter_by(token_hash=_hash(token)).first()
    if inv is None:
        raise ApiError("not_found", "This invite link isn't valid.", 404)
    return inv


@api_bp.get("/invitations/<token>")
def preview_invitation(token: str):
    """Public, so the sign-up page can say what the link is for. The token itself is the secret."""
    inv = _by_token(token)
    org = db.session.get(Organization, inv.organization_id)
    inviter = db.session.get(User, inv.invited_by)
    return jsonify(
        invitation={
            "organization_name": org.name,
            "role": inv.role.value,
            "email": inv.email,
            "invited_by": inviter.first_name if inviter else None,
            "state": _state(inv),
        }
    )


@api_bp.post("/invitations/<token>/accept")
@jwt_required()
def accept_invitation(token: str):
    user = current_user()
    inv = _by_token(token)
    state = _state(inv)
    if state != "pending":
        messages = {
            "expired": "This invite has expired. Ask for a new one.",
            "revoked": "This invite was cancelled. Ask for a new one.",
            "accepted": "This invite has already been used.",
        }
        raise ApiError(f"invitation_{state}", messages[state], 409)
    if user.email.lower() != inv.email:
        raise ApiError(
            "invitation_email_mismatch",
            f"This invite is for {inv.email}. Log in with that account to accept it.",
            403,
        )

    member = OrganizationMember.query.filter_by(organization_id=inv.organization_id, user_id=user.id).first()
    if member is None:
        member = OrganizationMember(organization_id=inv.organization_id, user_id=user.id, role=inv.role)
        db.session.add(member)
    elif member.status != "active":
        member.status = "active"
        member.role = inv.role
        member.joined_at = utcnow()
    # An active member keeps their current role.
    inv.status = "accepted"
    inv.accepted_at = utcnow()
    db.session.flush()
    log_action(
        organization_id=inv.organization_id,
        actor_id=user.id,
        action="invitation.accepted",
        entity_type="organization_member",
        entity_id=member.id,
        meta={"invitation_id": inv.id, "role": member.role.value},
    )
    db.session.commit()
    org = db.session.get(Organization, inv.organization_id)
    return jsonify(organization=org_to_dict(org, member.role))
