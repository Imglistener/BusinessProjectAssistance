"""Project milestones (FR-06). Owners and project managers manage them; every member can read them.

Completion is the task completion % of the milestone's linked tasks (same rule as projects).
Deleting a milestone keeps its tasks and just unlinks them.
"""
from __future__ import annotations

from datetime import date

from flask import jsonify
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Milestone, Organization, Project, Task
from ..services import metrics
from ..services import projects as svc
from ..services.audit import log_action
from ..services.permissions import PROJECT_WRITE_ROLES, require_role
from . import api_bp
from .auth import current_user
from .validation import get_json_body, parse_date, require_str

STATUSES = ("open", "done")


def milestone_to_dict(m: Milestone, tasks: list, today: date) -> dict:
    pct = metrics.task_completion_pct(tasks)
    return {
        "id": m.id,
        "project_id": m.project_id,
        "title": m.title,
        "due_date": m.due_date.isoformat() if m.due_date else None,
        "status": m.status,
        "task_count": len(tasks),
        "done_task_count": sum(1 for t in tasks if t.status.value == metrics.DONE),
        "task_completion_pct": None if pct is None else f"{pct:.2f}",
        "is_overdue": metrics.is_milestone_overdue(m, today),
    }


def milestones_for(project: Project, today: date) -> list[dict]:
    milestones = Milestone.query.filter_by(project_id=project.id).order_by(
        Milestone.due_date.is_(None), Milestone.due_date, Milestone.id
    ).all()
    tasks = Task.query.filter(Task.project_id == project.id, Task.milestone_id.isnot(None)).all()
    by_milestone: dict[int, list] = {}
    for t in tasks:
        by_milestone.setdefault(t.milestone_id, []).append(t)
    return [milestone_to_dict(m, by_milestone.get(m.id, []), today) for m in milestones]


def _today(project: Project) -> date:
    return svc.org_today(db.session.get(Organization, project.organization_id).timezone)


def _one(m: Milestone, project: Project) -> dict:
    tasks = Task.query.filter_by(milestone_id=m.id).all()
    return milestone_to_dict(m, tasks, _today(project))


def _get_for_user(milestone_id: int, user_id: int):
    m = db.session.get(Milestone, milestone_id)
    if m is None:
        raise ApiError("not_found", "Milestone not found.", 404)
    try:
        project, membership = svc.get_project_for_user(m.project_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Milestone not found.", 404)
    return m, project, membership


def _audit(user_id: int, project: Project, action: str, m: Milestone, meta: dict) -> None:
    log_action(
        organization_id=project.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="milestone",
        entity_id=m.id,
        meta={"project_id": project.id, **meta},
    )


def _parse_status(data: dict) -> str:
    status = data.get("status")
    if status not in STATUSES:
        raise ApiError("validation_error", "Status must be open or done.", 400, {"field": "status"})
    return status


@api_bp.get("/projects/<int:project_id>/milestones")
@jwt_required()
def list_milestones(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    return jsonify(milestones=milestones_for(project, _today(project)))


@api_bp.post("/projects/<int:project_id>/milestones")
@jwt_required()
def create_milestone(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    svc.require_active_project(project)
    data = get_json_body()
    m = Milestone(
        project_id=project.id,
        title=require_str(data, "title", max_len=200),
        due_date=parse_date(data, "due_date"),
        status="open",
    )
    db.session.add(m)
    db.session.flush()
    _audit(user.id, project, "milestone.created", m, {"due_date": m.due_date.isoformat() if m.due_date else None})
    db.session.commit()
    return jsonify(milestone=_one(m, project)), 201


@api_bp.patch("/milestones/<int:milestone_id>")
@jwt_required()
def update_milestone(milestone_id: int):
    user = current_user()
    m, project, membership = _get_for_user(milestone_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    svc.require_active_project(project)
    data = get_json_body()

    changes: dict = {}
    if "title" in data:
        changes["title"] = require_str(data, "title", max_len=200)
    if "due_date" in data:
        changes["due_date"] = parse_date(data, "due_date")
    if "status" in data:
        changes["status"] = _parse_status(data)

    meta = {}
    for field, new in changes.items():
        old = getattr(m, field)
        if old == new:
            continue
        setattr(m, field, new)
        if field == "title":
            meta[field] = "changed"
        else:
            meta[field] = [v.isoformat() if hasattr(v, "isoformat") else v for v in (old, new)]
    if meta:
        _audit(user.id, project, "milestone.updated", m, meta)
        db.session.commit()
    return jsonify(milestone=_one(m, project))


@api_bp.delete("/milestones/<int:milestone_id>")
@jwt_required()
def delete_milestone(milestone_id: int):
    user = current_user()
    m, project, membership = _get_for_user(milestone_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    svc.require_active_project(project)
    unlinked = Task.query.filter_by(milestone_id=m.id).update({"milestone_id": None})
    _audit(user.id, project, "milestone.deleted", m, {"unlinked_tasks": unlinked})
    db.session.delete(m)
    db.session.commit()
    return jsonify(ok=True)


def check_milestone(project: Project, milestone_id) -> None:
    """For task create/update: the milestone must belong to the same project."""
    if milestone_id is None:
        return
    m = db.session.get(Milestone, milestone_id)
    if m is None or m.project_id != project.id:
        raise ApiError(
            "validation_error", "Milestone must belong to this project.", 400, {"field": "milestone_id"}
        )
