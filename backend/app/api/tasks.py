from __future__ import annotations

from datetime import date

from flask import jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import OrganizationMember, Project, Role, Task, TaskPriority, TaskStatus, User, utcnow
from ..services import metrics
from ..services import projects as svc
from ..services.audit import log_action
from ..services.notifications import human_date, notify
from ..services.permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES, require_role
from . import api_bp
from .auth import current_user
from .milestones import check_milestone
from .projects import project_payload
from .validation import (
    get_json_body,
    optional_str,
    parse_date,
    parse_enum,
    parse_optional_id,
    require_str,
)

AUDITED_VALUE_FIELDS = ("status", "priority", "due_date", "assignee_id", "milestone_id")
# What a contributor may change on a task assigned to them.
ASSIGNEE_EDITABLE_FIELDS = {"status"}


def task_to_dict(t: Task, today: date, assignee_names: dict[int, str]) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "title": t.title,
        "description": t.description,
        "status": t.status.value,
        "priority": t.priority.value,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "assignee_id": t.assignee_id,
        "milestone_id": t.milestone_id,
        "assignee_name": assignee_names.get(t.assignee_id) if t.assignee_id else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "is_overdue": metrics.is_overdue(t, today),
    }


def _names(assignee_ids: set[int]) -> dict[int, str]:
    ids = {i for i in assignee_ids if i}
    if not ids:
        return {}
    users = User.query.filter(User.id.in_(ids)).all()
    return {u.id: f"{u.first_name} {u.last_name}" for u in users}


def _one(task: Task, project: Project) -> dict:
    from ..models import Organization

    org = db.session.get(Organization, project.organization_id)
    return task_to_dict(task, svc.org_today(org.timezone), _names({task.assignee_id}))


def _check_assignee(project: Project, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    member = OrganizationMember.query.filter_by(
        organization_id=project.organization_id, user_id=assignee_id, status="active"
    ).first()
    if member is None:
        raise ApiError(
            "validation_error",
            "Assignee must be a member of this organization.",
            400,
            {"field": "assignee_id"},
        )


def _audit(user_id: int, project: Project, action: str, task: Task, meta: dict) -> None:
    log_action(
        organization_id=project.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="task",
        entity_id=task.id,
        meta={"project_id": project.id, **meta},
    )


def _audit_value(v):
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _notify_assignee(task: Task, project: Project, actor_id: int) -> None:
    notify(
        organization_id=project.organization_id,
        user_ids=[task.assignee_id],
        actor_id=actor_id,
        kind="task_assigned",
        title=f"New task for you: {task.title}",
        body=f"In {project.name}. Due {human_date(task.due_date)}." if task.due_date else f"In {project.name}.",
        link=f"/app/projects/{project.id}",
    )


def _set_status(task: Task, status: TaskStatus) -> None:
    task.status = status
    # completed_at follows the status so "done" dates stay trustworthy.
    task.completed_at = utcnow() if status == TaskStatus.DONE else None


@api_bp.post("/projects/<int:project_id>/tasks")
@jwt_required()
def create_task(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *CONTRIBUTE_ROLES)
    svc.require_active_project(project)
    data = get_json_body()

    assignee_id = parse_optional_id(data, "assignee_id")
    _check_assignee(project, assignee_id)
    milestone_id = parse_optional_id(data, "milestone_id")
    check_milestone(project, milestone_id)
    task = Task(
        project_id=project.id,
        title=require_str(data, "title", max_len=200),
        description=optional_str(data, "description", max_len=5000),
        priority=parse_enum(data, "priority", TaskPriority, TaskPriority.MEDIUM),
        due_date=parse_date(data, "due_date"),
        assignee_id=assignee_id,
        milestone_id=milestone_id,
    )
    _set_status(task, parse_enum(data, "status", TaskStatus, TaskStatus.TODO))
    db.session.add(task)
    db.session.flush()
    _audit(
        user.id,
        project,
        "task.created",
        task,
        {"priority": task.priority.value, "assignee_id": task.assignee_id},
    )
    _notify_assignee(task, project, user.id)
    db.session.commit()
    return jsonify(task=_one(task, project), project=project_payload(project)), 201


@api_bp.get("/projects/<int:project_id>/tasks")
@jwt_required()
def list_tasks(project_id: int):
    from ..models import Organization

    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    org = db.session.get(Organization, project.organization_id)
    today = svc.org_today(org.timezone)

    query = Task.query.filter_by(project_id=project.id)
    status = request.args.get("status")
    if status:
        query = query.filter(Task.status == parse_enum({"status": status}, "status", TaskStatus))
    assignee = request.args.get("assignee_id")
    if assignee:
        if not assignee.isdigit():
            raise ApiError("validation_error", "Assignee is not valid.", 400, {"field": "assignee_id"})
        query = query.filter(Task.assignee_id == int(assignee))

    # Dated tasks first (soonest due first), undated last.
    tasks = query.order_by(Task.due_date.is_(None), Task.due_date, Task.id).all()
    if request.args.get("overdue") == "true":
        tasks = metrics.overdue_tasks(tasks, today)
    names = _names({t.assignee_id for t in tasks})
    return jsonify(tasks=[task_to_dict(t, today, names) for t in tasks])


@api_bp.patch("/tasks/<int:task_id>")
@jwt_required()
def update_task(task_id: int):
    user = current_user()
    task = db.session.get(Task, task_id)
    if task is None:
        raise ApiError("not_found", "Task not found.", 404)
    try:
        project, membership = svc.get_project_for_user(task.project_id, user.id)
    except ApiError:
        raise ApiError("not_found", "Task not found.", 404)

    data = get_json_body()
    if membership.role not in PROJECT_WRITE_ROLES:
        is_assignee = membership.role == Role.CONTRIBUTOR and task.assignee_id == user.id
        if not is_assignee or not set(data) <= ASSIGNEE_EDITABLE_FIELDS:
            raise ApiError("forbidden", "You do not have permission to do this.", 403)
    svc.require_active_project(project)

    changes: dict = {}
    if "title" in data:
        changes["title"] = require_str(data, "title", max_len=200)
    if "description" in data:
        changes["description"] = optional_str(data, "description", max_len=5000)
    if "priority" in data:
        priority = parse_enum(data, "priority", TaskPriority)
        if priority is None:
            raise ApiError("validation_error", "Priority can't be empty.", 400, {"field": "priority"})
        changes["priority"] = priority
    if "status" in data:
        status = parse_enum(data, "status", TaskStatus)
        if status is None:
            raise ApiError("validation_error", "Status can't be empty.", 400, {"field": "status"})
        changes["status"] = status
    if "due_date" in data:
        changes["due_date"] = parse_date(data, "due_date")
    if "assignee_id" in data:
        assignee_id = parse_optional_id(data, "assignee_id")
        _check_assignee(project, assignee_id)
        changes["assignee_id"] = assignee_id
    if "milestone_id" in data:
        milestone_id = parse_optional_id(data, "milestone_id")
        check_milestone(project, milestone_id)
        changes["milestone_id"] = milestone_id

    audit_meta = {}
    for field, new in changes.items():
        old = getattr(task, field)
        if old == new:
            continue
        if field == "status":
            _set_status(task, new)
        else:
            setattr(task, field, new)
        audit_meta[field] = (
            [_audit_value(old), _audit_value(new)] if field in AUDITED_VALUE_FIELDS else "changed"
        )

    if audit_meta:
        _audit(user.id, project, "task.updated", task, audit_meta)
        if "assignee_id" in audit_meta:
            _notify_assignee(task, project, user.id)
        db.session.commit()
    return jsonify(task=_one(task, project), project=project_payload(project))
