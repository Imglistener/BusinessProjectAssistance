from flask import current_app, jsonify
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import Organization, OrganizationMember, Role
from ..services.audit import log_action
from ..services.permissions import get_membership
from . import api_bp
from .auth import current_user
from .validation import get_json_body, require_str


def org_to_dict(org: Organization, role: Role) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "description": org.description,
        "default_currency": org.default_currency,
        "timezone": org.timezone,
        "role": role.value,
    }


@api_bp.post("/organizations")
@jwt_required()
def create_organization():
    user = current_user()
    data = get_json_body()
    name = require_str(data, "name", max_len=200)
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        description = None

    currency = data.get("default_currency") or current_app.config["DEFAULT_CURRENCY"]
    currency = require_str({"default_currency": currency}, "default_currency", max_len=3, min_len=3).upper()
    tz = data.get("timezone") or "Africa/Casablanca"
    tz = require_str({"timezone": tz}, "timezone", max_len=64)

    org = Organization(name=name, description=description, default_currency=currency, timezone=tz)
    db.session.add(org)
    db.session.flush()  # assigns org.id

    # The creator becomes the Owner.
    db.session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=Role.OWNER))
    log_action(
        organization_id=org.id,
        actor_id=user.id,
        action="organization.created",
        entity_type="organization",
        entity_id=org.id,
        meta={"name": name},
    )
    db.session.commit()
    return jsonify(organization=org_to_dict(org, Role.OWNER)), 201


@api_bp.get("/organizations")
@jwt_required()
def list_organizations():
    user = current_user()
    rows = (
        db.session.query(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
        .order_by(Organization.name)
        .all()
    )
    return jsonify(organizations=[org_to_dict(o, role) for o, role in rows])


@api_bp.get("/organizations/<int:org_id>")
@jwt_required()
def get_organization(org_id: int):
    user = current_user()
    membership = get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    return jsonify(organization=org_to_dict(org, membership.role))
