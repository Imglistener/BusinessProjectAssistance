from __future__ import annotations

from decimal import Decimal

from flask import jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Organization, Project, ProjectStatus, Role
from ..services import projects as svc
from ..services.audit import log_action
from ..services.permissions import get_membership, require_role
from . import api_bp
from .auth import current_user
from .validation import (
    get_json_body,
    optional_str,
    parse_currency,
    parse_date,
    parse_money,
    require_str,
)

# Roles that may create, edit and archive projects (to confirm with the project owner).
PROJECT_WRITE_ROLES = (Role.OWNER, Role.PROJECT_MANAGER)


def _money(value) -> str | None:
    return None if value is None else f"{Decimal(value):.2f}"


def project_to_dict(project: Project, m: dict) -> dict:
    return {
        "id": project.id,
        "organization_id": project.organization_id,
        "owner_id": project.owner_id,
        "name": project.name,
        "type": project.type,
        "description": project.description,
        "status": project.status.value,
        "currency": project.currency,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "budget": _money(m["budget"]),
        "actual": _money(m["actual"]),
        "remaining": _money(m["remaining"]),
        "variance": _money(m["variance"]),  # actual - budget; positive means over budget
        "consumed_pct": _money(m["consumed_pct"]),  # null when the budget is zero
        "task_completion_pct": _money(m["task_completion_pct"]),
        "overdue_task_count": m["overdue_task_count"],
        "over_budget": m["over_budget"],
    }


AUDITED_VALUE_FIELDS = ("budget", "status", "currency", "start_date", "end_date")


def _audit_value(v):
    if hasattr(v, "value"):  # enums
        return v.value
    if isinstance(v, Decimal):
        return _money(v)
    if hasattr(v, "isoformat"):  # dates
        return v.isoformat()
    return v


def _check_dates(start, end):
    if start and end and end < start:
        raise ApiError(
            "validation_error", "End date can't be before the start date.", 400, {"field": "end_date"}
        )


def _parse_status(data: dict) -> ProjectStatus | None:
    raw = data.get("status")
    if raw is None:
        return None
    try:
        return ProjectStatus(raw)
    except ValueError:
        allowed = ", ".join(s.value for s in ProjectStatus)
        raise ApiError("validation_error", f"Status must be one of: {allowed}.", 400, {"field": "status"})


def _one_project_dict(project: Project, org: Organization) -> dict:
    expenses = svc.load_expenses([project.id])
    tasks = svc.load_tasks([project.id])
    m = svc.project_metrics(project, expenses.get(project.id, []), tasks.get(project.id, []), svc.org_today(org.timezone))
    return project_to_dict(project, m)


@api_bp.post("/organizations/<int:org_id>/projects")
@jwt_required()
def create_project(org_id: int):
    user = current_user()
    membership = get_membership(org_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, org_id)

    data = get_json_body()
    start, end = parse_date(data, "start_date"), parse_date(data, "end_date")
    _check_dates(start, end)

    project = Project(
        organization_id=org_id,
        owner_id=user.id,
        name=require_str(data, "name", max_len=200),
        type=optional_str(data, "type", max_len=60),
        description=optional_str(data, "description", max_len=5000),
        status=_parse_status(data) or ProjectStatus.PLANNED,
        budget=parse_money(data, "budget", required=False) or Decimal("0.00"),
        currency=parse_currency(data, "currency", org.default_currency),
        start_date=start,
        end_date=end,
    )
    db.session.add(project)
    db.session.flush()
    log_action(
        organization_id=org_id,
        actor_id=user.id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        meta={"name": project.name, "budget": _money(project.budget), "currency": project.currency},
    )
    db.session.commit()
    return jsonify(project=_one_project_dict(project, org)), 201


@api_bp.get("/organizations/<int:org_id>/projects")
@jwt_required()
def list_projects(org_id: int):
    user = current_user()
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)

    query = Project.query.filter_by(organization_id=org_id)
    status = request.args.get("status")
    if status:
        try:
            query = query.filter(Project.status == ProjectStatus(status))
        except ValueError:
            raise ApiError("validation_error", "Unknown status filter.", 400, {"field": "status"})
    elif request.args.get("include_archived") != "true":
        query = query.filter(Project.status != ProjectStatus.ARCHIVED)

    projects = query.order_by(Project.created_at.desc(), Project.id.desc()).all()
    ids = [p.id for p in projects]
    expenses, tasks = svc.load_expenses(ids), svc.load_tasks(ids)
    today = svc.org_today(org.timezone)
    return jsonify(
        projects=[
            project_to_dict(p, svc.project_metrics(p, expenses.get(p.id, []), tasks.get(p.id, []), today))
            for p in projects
        ]
    )


@api_bp.get("/organizations/<int:org_id>/dashboard")
@jwt_required()
def organization_dashboard(org_id: int):
    user = current_user()
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    summary = svc.organization_summary(org_id, org.timezone)
    summary["totals"] = [
        {k: (_money(v) if k != "currency" else v) for k, v in t.items()} for t in summary["totals"]
    ]
    return jsonify(summary=summary)


@api_bp.get("/projects/<int:project_id>")
@jwt_required()
def get_project(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    org = db.session.get(Organization, project.organization_id)
    return jsonify(project=_one_project_dict(project, org))


@api_bp.patch("/projects/<int:project_id>")
@jwt_required()
def update_project(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, project.organization_id)
    data = get_json_body()

    changes: dict = {}
    if "name" in data:
        changes["name"] = require_str(data, "name", max_len=200)
    if "type" in data:
        changes["type"] = optional_str(data, "type", max_len=60)
    if "description" in data:
        changes["description"] = optional_str(data, "description", max_len=5000)
    if "status" in data:
        status = _parse_status(data)
        if status is None:
            raise ApiError("validation_error", "Status can't be empty.", 400, {"field": "status"})
        changes["status"] = status
    if "budget" in data:
        changes["budget"] = parse_money(data, "budget")
    if "currency" in data:
        new_currency = parse_currency(data, "currency", project.currency)
        if new_currency != project.currency:
            # One currency per project; changing it would silently mislabel existing expenses.
            if svc.load_expenses([project.id]).get(project.id):
                raise ApiError(
                    "currency_locked", "Currency can't change once the project has expenses.", 409, {"field": "currency"}
                )
            changes["currency"] = new_currency
    if "start_date" in data:
        changes["start_date"] = parse_date(data, "start_date")
    if "end_date" in data:
        changes["end_date"] = parse_date(data, "end_date")

    _check_dates(
        changes.get("start_date", project.start_date),
        changes.get("end_date", project.end_date),
    )

    audit_meta = {}
    for field, new in changes.items():
        old = getattr(project, field)
        if old == new:
            continue
        setattr(project, field, new)
        # Names and descriptions can be long or sensitive: log only that they changed.
        audit_meta[field] = [_audit_value(old), _audit_value(new)] if field in AUDITED_VALUE_FIELDS else "changed"

    if audit_meta:
        log_action(
            organization_id=project.organization_id,
            actor_id=user.id,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            meta=audit_meta,
        )
        db.session.commit()
    return jsonify(project=_one_project_dict(project, org))


@api_bp.post("/projects/<int:project_id>/archive")
@jwt_required()
def archive_project(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, project.organization_id)

    if project.status != ProjectStatus.ARCHIVED:
        previous = project.status.value
        project.status = ProjectStatus.ARCHIVED
        log_action(
            organization_id=project.organization_id,
            actor_id=user.id,
            action="project.archived",
            entity_type="project",
            entity_id=project.id,
            meta={"previous_status": previous},
        )
        db.session.commit()
    return jsonify(project=_one_project_dict(project, org))
