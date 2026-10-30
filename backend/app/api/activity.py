"""Project activity (FR-17): the audit trail for one project, newest first, for anyone who can see the project."""
from __future__ import annotations

from decimal import Decimal

from flask import jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..models import AuditLog, Expense, Milestone, Task, User
from ..services import projects as svc
from ..services.tokens import aware
from . import api_bp
from .auth import current_user

DEFAULT_PAGE = 20
MAX_PAGE = 100


def _ids(entries, entity_type: str) -> set[int]:
    return {e.entity_id for e in entries if e.entity_type == entity_type and e.entity_id}


def _labels(entries) -> dict[tuple[str, int], str]:
    """Current names of the records the entries point at (deleted records have none)."""
    labels: dict[tuple[str, int], str] = {}
    if ids := _ids(entries, "task"):
        labels.update({("task", t.id): t.title for t in Task.query.filter(Task.id.in_(ids))})
    if ids := _ids(entries, "milestone"):
        labels.update({("milestone", m.id): m.title for m in Milestone.query.filter(Milestone.id.in_(ids))})
    if ids := _ids(entries, "expense"):
        labels.update(
            {
                ("expense", e.id): f"{e.category}, {Decimal(e.amount):.2f} {e.currency}"
                for e in Expense.query.filter(Expense.id.in_(ids))
            }
        )
    return labels


def _people(entries) -> dict[int, str]:
    """Names for actors and for user IDs mentioned in changes (e.g. assignee)."""
    ids = {e.actor_id for e in entries if e.actor_id}
    for e in entries:
        change = (e.meta or {}).get("assignee_id")
        if isinstance(change, list):
            ids.update(v for v in change if isinstance(v, int))
        elif isinstance(change, int):
            ids.add(change)
    if not ids:
        return {}
    return {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(ids))}


@api_bp.get("/projects/<int:project_id>/activity")
@jwt_required()
def project_activity(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    try:
        limit = min(max(int(request.args.get("limit", DEFAULT_PAGE)), 1), MAX_PAGE)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError("validation_error", "limit and offset must be whole numbers.", 400)

    query = AuditLog.query.filter_by(project_id=project.id)
    total = query.count()
    entries = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).offset(offset).all()
    labels, people = _labels(entries), _people(entries)
    return jsonify(
        entries=[
            {
                "id": e.id,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "label": labels.get((e.entity_type, e.entity_id)),
                "actor": people.get(e.actor_id),
                "at": aware(e.timestamp).isoformat(),
                "meta": {k: v for k, v in (e.meta or {}).items() if k != "project_id"},
            }
            for e in entries
        ],
        people={str(k): v for k, v in people.items()},
        total=total,
        limit=limit,
        offset=offset,
    )
