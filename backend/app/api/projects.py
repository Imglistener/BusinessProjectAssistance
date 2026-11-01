from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import jsonify, request
from sqlalchemy import or_
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Milestone, Organization, Project, ProjectStatus, Role, Task, TaskPriority, TaskStatus
from ..services import project_delete
from ..services import projects as svc
from ..services.plans import PlanError, validate_inventory, validate_plan
from ..services.audit import log_action
from ..services.permissions import PROJECT_WRITE_ROLES, get_membership, require_role
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

MAX_SEARCH_LEN = 100
SORTS = ("newest", "name", "end_date")


def _like(term: str) -> str:
    """Case-insensitive 'contains' pattern with LIKE wildcards in the search text escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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


def project_payload(project: Project) -> dict:
    """Project with fresh metrics; returned by endpoints that change budget-relevant records."""
    org = db.session.get(Organization, project.organization_id)
    return _one_project_dict(project, org)


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
    try:
        inventory = validate_inventory(data.get("inventory"))  # optional opening inventory
    except PlanError as e:
        raise ApiError("validation_error", str(e), 400, {"field": e.field} if e.field else None)

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
    _add_opening_inventory(org_id, user.id, project, inventory)
    db.session.commit()
    return jsonify(project=_one_project_dict(project, org)), 201


@api_bp.post("/organizations/<int:org_id>/projects/from-plan")
@jwt_required()
def create_project_from_plan(org_id: int):
    """Create a project with its milestones and tasks from a plan the user reviewed (usually drafted by the
    assistant). The plan is validated again here; nothing from the draft is trusted."""
    user = current_user()
    membership = get_membership(org_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, org_id)
    try:
        plan = validate_plan(get_json_body(), default_currency=org.default_currency, today=svc.org_today(org.timezone))
    except PlanError as e:
        raise ApiError("validation_error", str(e), 400, {"field": e.field} if e.field else None)

    project = Project(
        organization_id=org_id,
        owner_id=user.id,
        name=plan["name"],
        description=plan["description"],
        status=ProjectStatus.PLANNED,
        budget=Decimal(plan["budget"] or "0"),
        currency=plan["currency"],
        start_date=date.fromisoformat(plan["start_date"]) if plan["start_date"] else None,
        end_date=date.fromisoformat(plan["end_date"]) if plan["end_date"] else None,
    )
    db.session.add(project)
    db.session.flush()
    milestone_ids = {}
    for m in plan["milestones"]:
        row = Milestone(
            project_id=project.id,
            title=m["title"],
            due_date=date.fromisoformat(m["due_date"]) if m["due_date"] else None,
            status="open",
        )
        db.session.add(row)
        db.session.flush()
        milestone_ids[m["title"].lower()] = row.id
    for t in plan["tasks"]:
        db.session.add(
            Task(
                project_id=project.id,
                title=t["title"],
                description=t["description"],
                priority=TaskPriority(t["priority"]),
                status=TaskStatus.TODO,
                due_date=date.fromisoformat(t["due_date"]) if t["due_date"] else None,
                milestone_id=milestone_ids.get((t["milestone"] or "").lower()),
            )
        )
    _add_opening_inventory(org_id, user.id, project, plan["inventory"])
    log_action(
        organization_id=org_id,
        actor_id=user.id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        meta={
            "name": project.name,
            "budget": _money(project.budget),
            "currency": project.currency,
            "source": "assistant_plan",
            "milestones": len(plan["milestones"]),
            "tasks": len(plan["tasks"]),
        },
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

    q = (request.args.get("q") or "").strip()
    if len(q) > MAX_SEARCH_LEN:
        raise ApiError("validation_error", "Search text is too long.", 400, {"field": "q"})
    if q:
        pattern = _like(q)
        query = query.filter(
            or_(Project.name.ilike(pattern, escape="\\"), Project.description.ilike(pattern, escape="\\"))
        )

    sort = request.args.get("sort") or "newest"
    if sort not in SORTS:
        raise ApiError("validation_error", f"Sort must be one of: {', '.join(SORTS)}.", 400, {"field": "sort"})
    if sort == "name":
        query = query.order_by(Project.name, Project.id)
    elif sort == "end_date":
        # Soonest end date first; projects without one last.
        query = query.order_by(Project.end_date.is_(None), Project.end_date, Project.id)
    else:
        query = query.order_by(Project.created_at.desc(), Project.id.desc())

    projects = query.all()
    ids = [p.id for p in projects]
    expenses, tasks = svc.load_expenses(ids), svc.load_tasks(ids)
    today = svc.org_today(org.timezone)
    rows = [
        project_to_dict(p, svc.project_metrics(p, expenses.get(p.id, []), tasks.get(p.id, []), today))
        for p in projects
    ]
    # Computed figures can't be filtered in SQL; filter after the metrics are known.
    if request.args.get("over_budget") == "true":
        rows = [r for r in rows if r["over_budget"]]
    if request.args.get("has_overdue") == "true":
        rows = [r for r in rows if r["overdue_task_count"] > 0]
    return jsonify(projects=rows)


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


@api_bp.get("/organizations/<int:org_id>/deadlines")
@jwt_required()
def organization_deadlines(org_id: int):
    user = current_user()
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    return jsonify(svc.deadlines(org_id, org.timezone, user.id))


@api_bp.get("/projects/<int:project_id>")
@jwt_required()
def get_project(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    org = db.session.get(Organization, project.organization_id)
    return jsonify(project={**_one_project_dict(project, org), "my_role": membership.role.value})


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


# ---------- deleting (owners only; archiving is the everyday option) ----------


def _deletable(org_id: int, user_id: int, project_ids) -> list[Project]:
    require_role(get_membership(org_id, user_id), Role.OWNER)
    return project_delete.load(org_id, project_ids)


@api_bp.post("/organizations/<int:org_id>/projects/delete-preview")
@jwt_required()
def preview_project_delete(org_id: int):
    """{project_ids}: what deleting them would remove. Changes nothing."""
    user = current_user()
    projects = _deletable(org_id, user.id, get_json_body().get("project_ids"))
    return jsonify(project_delete.summary(projects))


@api_bp.post("/organizations/<int:org_id>/projects/delete")
@jwt_required()
def delete_projects(org_id: int):
    """{project_ids}: delete them all, or none if any ID isn't one of this organization's projects."""
    user = current_user()
    projects = _deletable(org_id, user.id, get_json_body().get("project_ids"))
    files = project_delete.delete(projects, user.id)
    db.session.commit()
    project_delete.remove_files(files)
    return jsonify(deleted=len(projects))


@api_bp.delete("/projects/<int:project_id>")
@jwt_required()
def delete_project(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    projects = _deletable(project.organization_id, user.id, [project.id])
    files = project_delete.delete(projects, user.id)
    db.session.commit()
    project_delete.remove_files(files)
    return jsonify(deleted=1)


def _add_opening_inventory(org_id: int, user_id: int, project: Project, rows: list[dict]) -> None:
    """Create the new project's inventory items (already validated by plans.validate_inventory)."""
    from .inventory import create_item_in

    for row in rows:
        create_item_in(org_id, user_id, {k: v for k, v in row.items() if v is not None}, project)
