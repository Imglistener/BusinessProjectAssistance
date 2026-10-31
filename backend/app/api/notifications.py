from flask import jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..i18n import request_lang, translate
from ..models import Notification, Organization, OrganizationMember, utcnow
from ..services.tokens import aware
from . import api_bp
from .auth import current_user

PAGE = 30


def _visible(query, user_id: int):
    """Only notifications from organizations the user still belongs to."""
    org_ids = [
        m.organization_id for m in OrganizationMember.query.filter_by(user_id=user_id, status="active")
    ]
    return query.filter(Notification.user_id == user_id, Notification.organization_id.in_(org_ids or [-1]))


@api_bp.get("/notifications")
@jwt_required()
def list_notifications():
    user = current_user()
    query = _visible(Notification.query, user.id)
    unread = query.filter(Notification.read_at.is_(None)).count()
    if request.args.get("unread_only") == "true":
        query = query.filter(Notification.read_at.is_(None))
    try:
        limit = min(max(int(request.args.get("limit", PAGE)), 1), 100)
    except ValueError:
        raise ApiError("validation_error", "limit must be a whole number.", 400)
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    lang = request_lang()
    orgs = {o.id: o.name for o in Organization.query.filter(Organization.id.in_({n.organization_id for n in rows}))} if rows else {}
    return jsonify(
        unread_count=unread,
        notifications=[
            {
                "id": n.id,
                "kind": n.kind,
                "title": translate(n.title, lang),
                "body": translate(n.body, lang),
                "link": n.link,
                "organization_id": n.organization_id,
                "organization_name": orgs.get(n.organization_id),
                "created_at": aware(n.created_at).isoformat(),
                "read": n.read_at is not None,
            }
            for n in rows
        ],
    )


@api_bp.post("/notifications/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id: int):
    user = current_user()
    n = _visible(Notification.query, user.id).filter(Notification.id == notification_id).first()
    if n is None:
        raise ApiError("not_found", "Notification not found.", 404)
    if n.read_at is None:
        n.read_at = utcnow()
        db.session.commit()
    return jsonify(ok=True)


@api_bp.post("/notifications/read-all")
@jwt_required()
def mark_all_read():
    user = current_user()
    _visible(Notification.query, user.id).filter(Notification.read_at.is_(None)).update(
        {"read_at": utcnow()}, synchronize_session=False
    )
    db.session.commit()
    return jsonify(ok=True)
