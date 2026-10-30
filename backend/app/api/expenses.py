from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from ..errors import ApiError
from ..extensions import db
from ..models import Attachment, Expense, ExpenseStatus, Project, Role
from ..services import metrics
from ..services import projects as svc
from ..services.audit import log_action
from ..services.permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES, require_role
from . import api_bp
from .auth import current_user
from .projects import project_payload
from .trips import check_trip
from .validation import (
    get_json_body,
    optional_str,
    parse_date,
    parse_enum,
    parse_money,
    parse_optional_id,
    require_str,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
AUDITED_VALUE_FIELDS = ("amount", "category", "expense_date", "trip_id")


def expense_to_dict(e: Expense, attachment_count: int | None = None) -> dict:
    """`attachment_count` comes from the list's grouped query; single-expense responses count here."""
    if attachment_count is None:
        attachment_count = Attachment.query.filter_by(expense_id=e.id).count() if e.id else 0
    return {
        "id": e.id,
        "project_id": e.project_id,
        "created_by": e.created_by,
        "category": e.category,
        "amount": f"{Decimal(e.amount):.2f}",
        "currency": e.currency,
        "description": e.description,
        "expense_date": e.expense_date.isoformat(),
        "status": e.status.value,
        "trip_id": e.trip_id,
        "attachment_count": attachment_count,
    }


def _audit_value(v):
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    if isinstance(v, date):
        return v.isoformat()
    return v


def get_expense_for_user(expense_id: int, user_id: int):
    """Return (expense, project, membership); outsiders get the same 404 as unknown IDs."""
    expense = db.session.get(Expense, expense_id)
    if expense is None:
        raise ApiError("not_found", "Expense not found.", 404)
    try:
        project, membership = svc.get_project_for_user(expense.project_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Expense not found.", 404)
    return expense, project, membership


def _require_can_modify(expense: Expense, membership, user_id: int) -> None:
    """Owners and project managers change any expense; contributors only their own."""
    if membership.role in PROJECT_WRITE_ROLES:
        return
    if membership.role == Role.CONTRIBUTOR and expense.created_by == user_id:
        return
    raise ApiError("forbidden", "You do not have permission to do this.", 403)


def _audit(user_id: int, project: Project, action: str, expense: Expense, meta: dict) -> None:
    log_action(
        organization_id=project.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="expense",
        entity_id=expense.id,
        meta={"project_id": project.id, **meta},
    )


@api_bp.post("/projects/<int:project_id>/expenses")
@jwt_required()
def create_expense(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *CONTRIBUTE_ROLES)
    svc.require_active_project(project)
    data = get_json_body()
    trip_id = parse_optional_id(data, "trip_id")
    check_trip(project, trip_id)

    expense = Expense(
        project_id=project.id,
        created_by=user.id,
        category=require_str(data, "category", max_len=80),
        amount=parse_money(data, "amount", positive=True),
        currency=project.currency,  # one currency per project; never taken from the request
        description=optional_str(data, "description", max_len=5000),
        expense_date=parse_date(data, "expense_date", required=True),
        status=ExpenseStatus.VALID,
        trip_id=trip_id,
    )
    db.session.add(expense)
    db.session.flush()
    _audit(
        user.id,
        project,
        "expense.created",
        expense,
        {"amount": _audit_value(expense.amount), "currency": expense.currency, "category": expense.category},
    )
    db.session.commit()
    return jsonify(expense=expense_to_dict(expense), project=project_payload(project)), 201


@api_bp.get("/projects/<int:project_id>/expenses")
@jwt_required()
def list_expenses(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)

    query = Expense.query.filter_by(project_id=project.id)
    status = request.args.get("status")
    if status:
        query = query.filter(Expense.status == parse_enum({"status": status}, "status", ExpenseStatus))
    category = request.args.get("category")
    if category:
        query = query.filter(Expense.category == category)
    start = parse_date({"from": request.args.get("from")}, "from")
    end = parse_date({"to": request.args.get("to")}, "to")
    if start:
        query = query.filter(Expense.expense_date >= start)
    if end:
        query = query.filter(Expense.expense_date <= end)

    try:
        limit = min(max(int(request.args.get("limit", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError("validation_error", "limit and offset must be whole numbers.", 400)

    if start and end and end < start:
        raise ApiError("validation_error", "The end date can't be before the start date.", 400, {"field": "to"})

    total = query.count()
    rows = (
        query.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit).offset(offset).all()
    )
    # Sum of valid expenses matching the filter (all pages), from the metrics service.
    matching_amount = metrics.total_actual_expenses(query.all())
    categories = [
        c for (c,) in db.session.query(Expense.category).filter_by(project_id=project.id).distinct().order_by(Expense.category)
    ]
    counts = dict(
        db.session.query(Attachment.expense_id, func.count(Attachment.id))
        .filter(Attachment.expense_id.in_([e.id for e in rows]))
        .group_by(Attachment.expense_id)
        .all()
    ) if rows else {}
    return jsonify(
        expenses=[expense_to_dict(e, counts.get(e.id, 0)) for e in rows],
        total=total,
        limit=limit,
        offset=offset,
        matching_amount=f"{matching_amount:.2f}",
        currency=project.currency,
        categories=categories,
    )


@api_bp.patch("/expenses/<int:expense_id>")
@jwt_required()
def update_expense(expense_id: int):
    user = current_user()
    expense, project, membership = get_expense_for_user(expense_id, user.id)
    _require_can_modify(expense, membership, user.id)
    svc.require_active_project(project)
    if expense.status != ExpenseStatus.VALID:
        raise ApiError("expense_not_editable", "Only valid expenses can be edited.", 409)
    data = get_json_body()

    changes: dict = {}
    if "category" in data:
        changes["category"] = require_str(data, "category", max_len=80)
    if "amount" in data:
        changes["amount"] = parse_money(data, "amount", positive=True)
    if "description" in data:
        changes["description"] = optional_str(data, "description", max_len=5000)
    if "expense_date" in data:
        changes["expense_date"] = parse_date(data, "expense_date", required=True)
    if "trip_id" in data:
        trip_id = parse_optional_id(data, "trip_id")
        check_trip(project, trip_id)
        changes["trip_id"] = trip_id

    audit_meta = {}
    for field, new in changes.items():
        old = getattr(expense, field)
        if old == new:
            continue
        setattr(expense, field, new)
        audit_meta[field] = [_audit_value(old), _audit_value(new)] if field in AUDITED_VALUE_FIELDS else "changed"

    if audit_meta:
        _audit(user.id, project, "expense.updated", expense, audit_meta)
        db.session.commit()
    return jsonify(expense=expense_to_dict(expense), project=project_payload(project))


@api_bp.post("/expenses/<int:expense_id>/void")
@jwt_required()
def void_expense(expense_id: int):
    """Expenses are never deleted: a voided expense stays on record but drops out of every total."""
    user = current_user()
    expense, project, membership = get_expense_for_user(expense_id, user.id)
    _require_can_modify(expense, membership, user.id)
    svc.require_active_project(project)

    if expense.status != ExpenseStatus.VOIDED:
        previous = expense.status.value
        expense.status = ExpenseStatus.VOIDED
        _audit(
            user.id,
            project,
            "expense.voided",
            expense,
            {"amount": _audit_value(expense.amount), "previous_status": previous},
        )
        db.session.commit()
    return jsonify(expense=expense_to_dict(expense), project=project_payload(project))
