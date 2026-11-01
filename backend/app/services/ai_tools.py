"""Read-only tools the assistant may call (spec 8.2). The allowlist is TOOLS below: nothing else runs.

Every tool re-checks that the user is an active member of the chat's organization and that the
project belongs to it, exactly like the REST endpoints. All figures come from services.metrics;
results carry money as decimal strings with the currency, and state their assumptions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional

from ..errors import ApiError
from ..extensions import db
from ..models import Expense, InventoryItem, Milestone, Organization, Project, ProjectStatus, Task, Trip, User, Warehouse
from . import metrics, travel
from .calculator import CalculationError, calculate as _calculate
from .plans import PlanError, validate_plan
from . import stock, stock_plans
from .permissions import get_membership
from . import projects as svc

MAX_LIST = 25
MAX_DESCRIPTION = 500
UPCOMING_DAYS = 14


class ToolError(Exception):
    """Shown to the model as the tool result, so keep messages short and free of internals."""


@dataclass
class ToolContext:
    user_id: int
    organization_id: int
    today: date


def _m(value) -> Optional[str]:
    return None if value is None else f"{Decimal(value):.2f}"


# ---------- argument parsing (model output is untrusted input) ----------


def _int_arg(args: dict, name: str, *, default=None, lo=1, hi=None) -> int:
    value = args.get(name, default)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"'{name}' must be a whole number.")
    if value < lo or (hi is not None and value > hi):
        raise ToolError(f"'{name}' must be between {lo} and {hi}." if hi else f"'{name}' must be at least {lo}.")
    return value


def _date_arg(args: dict, name: str) -> Optional[date]:
    value = args.get(name)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolError(f"'{name}' must be a date like 2026-10-31.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"'{name}' must be a date like 2026-10-31.")


def _choice_arg(args: dict, name: str, allowed: tuple[str, ...], default: str) -> str:
    value = args.get(name) or default
    if value not in allowed:
        raise ToolError(f"'{name}' must be one of: {', '.join(allowed)}.")
    return value


def project_for_context(ctx: ToolContext, args: dict) -> Project:
    project_id = _int_arg(args, "project_id")
    try:
        project, _ = svc.get_project_for_user(project_id, ctx.user_id)
    except ApiError:
        project = None
    # Same answer for unknown IDs, other organizations and lost access: nothing to probe.
    if project is None or project.organization_id != ctx.organization_id:
        raise ToolError("Project not found or not accessible.")
    return project


def _data(project: Project):
    return svc.load_expenses([project.id]).get(project.id, []), svc.load_tasks([project.id]).get(project.id, [])


def _budget(project: Project, expenses: list) -> dict:
    b = metrics.calculate_budget_metrics(project.budget, expenses)
    return {
        "currency": project.currency,
        "approved_budget": _m(b.budget),
        "actual_expenses": _m(b.actual),
        "remaining_budget": _m(b.remaining),
        "budget_variance": _m(b.variance),
        "budget_consumed_pct": _m(b.consumed_pct),
        "over_budget": b.variance > 0,
    }


def _assignee_names(tasks: list) -> dict[int, str]:
    ids = {t.assignee_id for t in tasks if t.assignee_id}
    if not ids:
        return {}
    return {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(ids)).all()}


def _task_brief(t: Task, today: date, names: dict[int, str]) -> dict:
    row = {
        "task_id": t.id,
        "title": t.title,
        "status": t.status.value,
        "priority": t.priority.value,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "assignee": names.get(t.assignee_id) if t.assignee_id else None,
    }
    if metrics.is_overdue(t, today):
        row["days_overdue"] = (today - t.due_date).days
    return row


def _milestones(project: Project, tasks: list, today: date) -> list[dict]:
    rows = (
        Milestone.query.filter_by(project_id=project.id)
        .order_by(Milestone.due_date.is_(None), Milestone.due_date, Milestone.id)
        .limit(MAX_LIST)
        .all()
    )
    out = []
    for m in rows:
        linked = [t for t in tasks if t.milestone_id == m.id]
        out.append(
            {
                "title": m.title,
                "due_date": m.due_date.isoformat() if m.due_date else None,
                "status": m.status,
                "overdue": metrics.is_milestone_overdue(m, today),
                "linked_tasks": len(linked),
                "task_completion_pct": _m(metrics.task_completion_pct(linked)),
            }
        )
    return out


def _trips(project: Project) -> list[dict]:
    trips = Trip.query.filter_by(project_id=project.id).order_by(Trip.start_date, Trip.id).limit(MAX_LIST).all()
    out = []
    for t in trips:
        spent = metrics.total_actual_expenses(Expense.query.filter_by(trip_id=t.id).all())
        out.append(
            {
                "trip_id": t.id,
                "title": t.title,
                "destination": t.destination,
                "start_date": t.start_date.isoformat(),
                "end_date": t.end_date.isoformat(),
                "status": t.status.value,
                "budget": _m(t.budget),
                "actual": _m(spent),
                "travelers": len(t.travelers),
            }
        )
    return out


# ---------- tools ----------


def list_projects(ctx: ToolContext, args: dict) -> dict:
    include_archived = args.get("include_archived") is True
    query = Project.query.filter_by(organization_id=ctx.organization_id)
    if not include_archived:
        query = query.filter(Project.status != ProjectStatus.ARCHIVED)
    projects = query.order_by(Project.name, Project.id).limit(MAX_LIST + 1).all()
    ids = [p.id for p in projects[:MAX_LIST]]
    expenses, tasks = svc.load_expenses(ids), svc.load_tasks(ids)
    rows = []
    for p in projects[:MAX_LIST]:
        m = svc.project_metrics(p, expenses.get(p.id, []), tasks.get(p.id, []), ctx.today)
        rows.append(
            {
                "project_id": p.id,
                "name": p.name,
                "status": p.status.value,
                "currency": p.currency,
                "over_budget": m["over_budget"],
                "overdue_task_count": m["overdue_task_count"],
            }
        )
    return {"as_of": ctx.today.isoformat(), "projects": rows, "truncated": len(projects) > MAX_LIST}


def get_project_summary(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    expenses, tasks = _data(project)
    by_status: dict[str, int] = {}
    for t in tasks:
        by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
    description = project.description or None
    if description and len(description) > MAX_DESCRIPTION:
        description = description[:MAX_DESCRIPTION] + "…"
    return {
        "as_of": ctx.today.isoformat(),
        "project_id": project.id,
        "name": project.name,
        "status": project.status.value,
        "description": description,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "budget": _budget(project, expenses),
        "tasks": {
            "total": len(tasks),
            "by_status": by_status,
            "completion_pct": _m(metrics.task_completion_pct(tasks)),
            "overdue_count": len(metrics.overdue_tasks(tasks, ctx.today)),
        },
        "valid_expense_count": sum(1 for e in expenses if e.status.value == metrics.VALID_EXPENSE_STATUS),
        "milestones": _milestones(project, tasks, ctx.today),
        "trips": _trips(project),
    }


def calculate_budget_metrics(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    expenses, _ = _data(project)
    return {
        "as_of": ctx.today.isoformat(),
        "project_id": project.id,
        **_budget(project, expenses),
        "definitions": {
            "actual_expenses": "Sum of valid expenses; voided and refunded entries are excluded.",
            "remaining_budget": "Approved budget minus actual expenses; negative means overspent.",
            "budget_variance": "Actual expenses minus approved budget; positive means over budget.",
            "budget_consumed_pct": "Actual / budget x 100; null (N/A) when the budget is zero.",
        },
    }


def get_expense_breakdown(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    start, end = _date_arg(args, "start_date"), _date_arg(args, "end_date")
    if start and end and end < start:
        raise ToolError("'end_date' can't be before 'start_date'.")
    group_by = _choice_arg(args, "group_by", ("category", "month"), "category")
    expenses, _ = _data(project)
    rows = metrics.expense_breakdown(expenses, group_by, start, end)
    return {
        "project_id": project.id,
        "currency": project.currency,
        "period": {"start_date": start.isoformat() if start else None, "end_date": end.isoformat() if end else None},
        "group_by": group_by,
        "groups": [{"group": r["key"], "total": _m(r["total"]), "expense_count": r["count"]} for r in rows],
        "total": _m(metrics.total_actual_expenses(expenses, start, end)),
        "note": "Only valid expenses are counted; voided and refunded entries are excluded.",
    }


def list_overdue_tasks(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    _, tasks = _data(project)
    overdue = sorted(metrics.overdue_tasks(tasks, ctx.today), key=lambda t: (t.due_date, t.id))
    names = _assignee_names(overdue[:MAX_LIST])
    return {
        "as_of": ctx.today.isoformat(),
        "project_id": project.id,
        "overdue_count": len(overdue),
        "tasks": [_task_brief(t, ctx.today, names) for t in overdue[:MAX_LIST]],
        "truncated": len(overdue) > MAX_LIST,
        "definition": "Not done or cancelled, with a due date before today in the organization's timezone. "
        "Blocked tasks count as overdue.",
    }


def estimate_spend_rate(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    period_days = _int_arg(args, "period_days", default=30, lo=1, hi=365)
    expenses, _ = _data(project)
    start = ctx.today - timedelta(days=period_days - 1)
    per_day = metrics.spend_rate_per_day(expenses, period_days, ctx.today)
    b = metrics.calculate_budget_metrics(project.budget, expenses)
    days_left = metrics.days_until_budget_exhausted(b.remaining, per_day)

    limitations = ["This is an estimate based on past spending, not a forecast of future costs."]
    if project.start_date and project.start_date > start:
        limitations.append(
            f"The project started on {project.start_date.isoformat()}, after the start of this window, "
            "so the daily rate may be understated."
        )
    if per_day == 0:
        limitations.append("No valid expenses in this window, so no rate can be estimated.")
    return {
        "project_id": project.id,
        "currency": project.currency,
        "window": {"start_date": start.isoformat(), "end_date": ctx.today.isoformat(), "days": period_days},
        "spent_in_window": _m(metrics.total_actual_expenses(expenses, start, ctx.today)),
        "average_per_day": _m(per_day),
        "remaining_budget": _m(b.remaining),
        "days_until_budget_used_at_this_rate": days_left,
        "assumptions": [
            "Average daily spend = valid expenses dated in the window / number of days in the window.",
            "Spending continues at the same average rate.",
        ],
        "limitations": limitations,
    }


def draft_project_update(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    summary = get_project_summary(ctx, {"project_id": project.id})
    _, tasks = _data(project)
    overdue = list_overdue_tasks(ctx, {"project_id": project.id})
    horizon = ctx.today + timedelta(days=UPCOMING_DAYS)
    upcoming = sorted(
        (
            t
            for t in tasks
            if t.due_date
            and ctx.today <= t.due_date <= horizon
            and t.status.value not in (metrics.DONE, metrics.CANCELLED)
        ),
        key=lambda t: (t.due_date, t.id),
    )[:MAX_LIST]
    names = _assignee_names(upcoming)
    top = get_expense_breakdown(ctx, {"project_id": project.id, "group_by": "category"})["groups"][:3]
    return {
        "facts": summary,
        "overdue_tasks": overdue["tasks"],
        "tasks_due_next_14_days": [_task_brief(t, ctx.today, names) for t in upcoming],
        "top_expense_categories": top,
        "instructions": "Write a short draft update using only these facts. Label it as an AI-generated draft "
        "for the user to review before sharing. Mention any missing data (e.g. no budget, no dates).",
    }


def get_inventory_status(ctx: ToolContext, args: dict) -> dict:
    items = InventoryItem.query.filter_by(organization_id=ctx.organization_id, archived=False).all()
    currency = db.session.get(Organization, ctx.organization_id).default_currency if items else None
    low = sorted(
        (i for i in items if metrics.is_low_stock(i.quantity_on_hand, i.reorder_level)), key=lambda i: i.name
    )
    total = Decimal("0")
    unpriced = 0
    for i in items:
        v = metrics.stock_value(i.quantity_on_hand, i.unit_cost)
        if v is None:
            unpriced += 1
        else:
            total += v
    return {
        "currency": currency,
        "item_count": len(items),
        "stock_value": _m(metrics.q(total)),
        "unpriced_item_count": unpriced,
        "low_stock": [
            {"name": i.name, "sku": i.sku, "on_hand": _m(i.quantity_on_hand), "unit": i.unit,
             "reorder_level": _m(i.reorder_level), "location": i.location}
            for i in low[:MAX_LIST]
        ],
        "notes": [
            "Low stock = at or below the item's reorder level; items without a level are never low.",
            "Stock value = quantity on hand x unit cost; items without a cost are left out of the value.",
        ],
    }


def _inventory_arg(ctx: ToolContext, args: dict):
    """("all" | None for General stock | project ID, label) from the optional `inventory` argument."""
    name = args.get("inventory")
    if not isinstance(name, str) or not name.strip():
        return "all", "all inventories"
    if stock_plans.is_general(name):
        return None, stock_plans.GENERAL
    projects = Project.query.filter(Project.organization_id == ctx.organization_id).all()
    project, candidates = stock_plans._match(projects, name)
    if project is None:
        raise ToolError(f"Several projects match: {', '.join(candidates)}." if candidates else f"No project called {name}.")
    return project.id, project.name


def find_inventory_items(ctx: ToolContext, args: dict) -> dict:
    query = args.get("query") if isinstance(args.get("query"), str) else None
    scope, label = _inventory_arg(ctx, args)
    items = stock_plans.find_items(ctx.organization_id, query, limit=MAX_LIST, project_id=scope)
    names = {p.id: p.name for p in Project.query.filter(Project.id.in_({i.project_id for i in items if i.project_id}))} if items else {}
    per_item = stock.stock_by_item([i.id for i in items])
    return {
        "inventory": label,
        "items": [
            {"name": i.name, "inventory": names.get(i.project_id, stock_plans.GENERAL), "sku": i.sku,
             "on_hand": _m(i.quantity_on_hand), "unit": i.unit, "unit_cost": _m(i.unit_cost),
             "reorder_level": _m(i.reorder_level),
             "low_stock": metrics.is_low_stock(i.quantity_on_hand, i.reorder_level),
             "by_warehouse": {s["warehouse"]: s["quantity"] for s in per_item.get(i.id, [])},
             "not_in_a_warehouse": _m(i.quantity_on_hand - sum((Decimal(s["quantity"]) for s in per_item.get(i.id, [])), Decimal("0")))}
            for i in items
        ],
        "note": "Each project has its own inventory; General stock is the organization's own. "
        "Matches by name, SKU or location; archived items are left out.",
    }


def list_warehouses(ctx: ToolContext, args: dict) -> dict:
    scope, label = _inventory_arg(ctx, args)
    q = Warehouse.query.filter_by(organization_id=ctx.organization_id)
    if scope != "all":
        q = q.filter(Warehouse.project_id.is_(None) if scope is None else Warehouse.project_id == scope)
    rows = q.order_by(Warehouse.name).limit(MAX_LIST).all()
    names = {p.id: p.name for p in Project.query.filter(Project.id.in_({w.project_id for w in rows if w.project_id}))} if rows else {}
    contents = stock.warehouse_contents([w.id for w in rows])
    held: dict[int, list] = {}
    if rows:
        from ..models import InventoryStock
        for s, item in (
            db.session.query(InventoryStock, InventoryItem)
            .join(InventoryItem, InventoryItem.id == InventoryStock.item_id)
            .filter(InventoryStock.warehouse_id.in_([w.id for w in rows]), InventoryStock.quantity != 0)
        ):
            held.setdefault(s.warehouse_id, []).append(f"{item.name}: {_m(s.quantity)} {item.unit}")
    return {
        "inventory": label,
        "warehouses": [
            {"name": w.name, "inventory": names.get(w.project_id, stock_plans.GENERAL), "address": w.address,
             "has_map_position": w.lat is not None, "items": held.get(w.id, [])[:MAX_LIST],
             "stock_value": contents.get(w.id, {}).get("value")}
            for w in rows
        ],
        "note": "To reorganize, draft transfer lines with propose_stock_changes. Warehouses themselves are added and "
        "placed on the map by the user on the Stock page.",
    }


def propose_stock_changes(ctx: ToolContext, args: dict) -> dict:
    """Preview stock changes. Nothing is saved: the user reviews them and confirms in the app."""
    role = get_membership(ctx.organization_id, ctx.user_id).role
    try:
        draft = stock_plans.draft_changes(ctx.organization_id, role, args.get("changes"))
    except ValueError as e:
        raise ToolError(str(e))
    problems = [f"{line['name'] or '?'}: {line['error']}" for line in draft["lines"] if line["error"]]
    not_allowed = [line["name"] for line in draft["lines"] if not line["allowed"]]
    return {
        "proposal": draft,
        "status": "draft_not_saved",
        "problems": problems,
        "needs_manager": not_allowed,
        "next_step": "Tell the user the changes are shown below your message with a 'Confirm' button and nothing "
        "has changed yet. Mention any problems (e.g. an unknown item to create first) and lines only an owner or "
        "project manager can confirm.",
    }


def calculate(ctx: ToolContext, args: dict) -> dict:
    expression = args.get("expression")
    try:
        return {"expression": expression, "result": _calculate(expression)}
    except CalculationError as e:
        raise ToolError(str(e))


def _decimal_arg(args: dict, name: str, *, default=None, lo=None, hi=None) -> Decimal:
    value = args.get(name, default)
    if value is None or isinstance(value, bool):
        raise ToolError(f"'{name}' is required.")
    try:
        d = Decimal(str(value))
    except ArithmeticError:
        raise ToolError(f"'{name}' must be a number.")
    if not d.is_finite() or (lo is not None and d < lo) or (hi is not None and d > hi):
        raise ToolError(f"'{name}' is out of range.")
    return d


def vat(ctx: ToolContext, args: dict) -> dict:
    amount = _decimal_arg(args, "amount", lo=Decimal("0"), hi=Decimal("1e12"))
    rate = _decimal_arg(args, "rate_pct", default="20", lo=Decimal("0"), hi=Decimal("100"))
    mode = _choice_arg(args, "mode", ("add", "extract"), "add")
    return {**{k: _m(v) for k, v in metrics.vat(amount, rate, mode).items()}, "rate_pct": str(rate), "mode": mode,
            "note": "Morocco's standard VAT (TVA) rate is 20%; reduced rates (7%, 10%, 14%) apply to some goods and services."}


def budget_what_if(ctx: ToolContext, args: dict) -> dict:
    project = project_for_context(ctx, args)
    extra = _decimal_arg(args, "additional_spend", lo=Decimal("-1e12"), hi=Decimal("1e12"))
    expenses, _ = _data(project)
    now = metrics.calculate_budget_metrics(project.budget, expenses)
    actual = now.actual + extra
    return {
        "project_id": project.id,
        "currency": project.currency,
        "additional_spend": _m(extra),
        "now": {"actual": _m(now.actual), "remaining": _m(now.remaining), "consumed_pct": _m(now.consumed_pct)},
        "after": {
            "actual": _m(metrics.q(actual)),
            "remaining": _m(metrics.remaining_budget(project.budget, actual)),
            "consumed_pct": _m(metrics.budget_consumed_pct(project.budget, actual)),
            "over_budget": metrics.budget_variance(project.budget, actual) > 0,
        },
        "note": "Hypothetical: nothing is recorded.",
    }


def _find_trip(ctx: ToolContext, args: dict) -> Trip:
    """By trip_id, or by trip_title within the chat's organization (only one match allowed)."""
    if args.get("trip_id") is not None:
        trip = db.session.get(Trip, _int_arg(args, "trip_id"))
    else:
        title = args.get("trip_title")
        if not isinstance(title, str) or not title.strip():
            raise ToolError("Give trip_id or trip_title.")
        matches = (
            Trip.query.join(Project, Project.id == Trip.project_id)
            .filter(Project.organization_id == ctx.organization_id, Trip.title.ilike(title.strip()))
            .all()
        )
        if len(matches) > 1:
            raise ToolError("Several trips have that title; use trip_id from the project summary.")
        trip = matches[0] if matches else None
    if trip is None:
        raise ToolError("Trip not found or not accessible.")
    return trip


def estimate_trip_fuel_cost(ctx: ToolContext, args: dict) -> dict:
    trip = _find_trip(ctx, args)
    project = project_for_context(ctx, {"project_id": trip.project_id})
    overrides = {}
    if args.get("vehicle_type"):
        overrides["vehicle_type"] = _choice_arg(args, "vehicle_type", tuple(travel.VEHICLES), travel.DEFAULT_VEHICLE)
    if args.get("vehicle_count") is not None:
        overrides["vehicle_count"] = _int_arg(args, "vehicle_count", lo=1, hi=50)
    if isinstance(args.get("round_trip"), bool):
        overrides["round_trip"] = args["round_trip"]
    try:
        return {"trip_id": trip.id, "title": trip.title, "from": trip.origin, "to": trip.destination,
                **travel.estimate_for_trip(trip, project, overrides)}
    except travel.EstimateUnavailable as e:
        raise ToolError(str(e))


def estimate_fuel_cost(ctx: ToolContext, args: dict) -> dict:
    """Hypothetical drive: between two known cities, or over a given distance."""
    vehicle = _choice_arg(args, "vehicle_type", tuple(travel.VEHICLES), travel.DEFAULT_VEHICLE)
    from_city, to_city = args.get("from_city"), args.get("to_city")
    if args.get("distance_km") not in (None, ""):
        km, source = _decimal_arg(args, "distance_km", lo=Decimal("0.1"), hi=Decimal("20000")), "manual"
    else:
        a, b = travel.city_for(from_city), travel.city_for(to_city)
        if not a or not b:
            known = ", ".join(travel.CITIES)
            raise ToolError(f"Give distance_km, or two known cities: {known}.")
        straight = metrics.straight_line_km(*travel.CITIES[a], *travel.CITIES[b])
        km, source = (straight * travel.ROAD_FACTOR).quantize(Decimal("0.1")), "straight_line"
    org = db.session.get(Organization, ctx.organization_id)
    try:
        result = travel.estimate_fuel(
            organization_id=ctx.organization_id,
            currency=org.default_currency,
            one_way_km=km,
            distance_source=source,
            vehicle_type=vehicle,
            vehicle_count=_int_arg(args, "vehicle_count", default=1, lo=1, hi=50),
            round_trip=args.get("round_trip") is True,
            city=travel.city_for(args.get("fuel_city") or from_city) or args.get("fuel_city") or from_city,
            today=ctx.today,
        )
    except travel.EstimateUnavailable as e:
        raise ToolError(str(e))
    return {"from": from_city, "to": to_city, **result}


def propose_project(ctx: ToolContext, args: dict) -> dict:
    """Validate a draft plan. Nothing is created: the user reviews it and confirms in the app."""
    org = db.session.get(Organization, ctx.organization_id)
    try:
        plan = validate_plan(args, default_currency=org.default_currency, today=ctx.today)
    except PlanError as e:
        raise ToolError(str(e))
    return {
        "proposal": plan,
        "status": "draft_not_saved",
        "next_step": "Tell the user the draft is shown below their message with a 'Create project' button; "
        "they can adjust it first. Summarise the plan briefly; don't repeat every task.",
    }


_PROJECT_ID = {"project_id": {"type": "integer", "description": "Project ID from list_projects."}}

# name -> (function, description, JSON-schema parameters)
TOOLS: dict[str, tuple[Callable[[ToolContext, dict], dict], str, dict]] = {
    "list_projects": (
        list_projects,
        "List the projects in this organization with their IDs, status, currency and warning flags.",
        {
            "type": "object",
            "properties": {"include_archived": {"type": "boolean", "description": "Also list archived projects."}},
        },
    ),
    "get_project_summary": (
        get_project_summary,
        "Current facts for one project: status, dates, budget figures, task counts, completion and milestones.",
        {"type": "object", "properties": _PROJECT_ID, "required": ["project_id"]},
    ),
    "calculate_budget_metrics": (
        calculate_budget_metrics,
        "Backend-calculated budget, actual spend, remaining, variance and % consumed, with definitions.",
        {"type": "object", "properties": _PROJECT_ID, "required": ["project_id"]},
    ),
    "get_expense_breakdown": (
        get_expense_breakdown,
        "Totals of valid expenses grouped by category or month, optionally within a date range.",
        {
            "type": "object",
            "properties": {
                **_PROJECT_ID,
                "start_date": {"type": "string", "description": "Inclusive, YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "Inclusive, YYYY-MM-DD."},
                "group_by": {"type": "string", "enum": ["category", "month"]},
            },
            "required": ["project_id"],
        },
    ),
    "list_overdue_tasks": (
        list_overdue_tasks,
        "Overdue tasks for one project, oldest due date first, with assignee and days overdue.",
        {"type": "object", "properties": _PROJECT_ID, "required": ["project_id"]},
    ),
    "estimate_spend_rate": (
        estimate_spend_rate,
        "Average daily spend over the last N days and how long the remaining budget lasts at that rate. "
        "Returns its assumptions and limitations, which must be shared with the user.",
        {
            "type": "object",
            "properties": {
                **_PROJECT_ID,
                "period_days": {"type": "integer", "description": "Window length in days (1-365). Default 30."},
            },
            "required": ["project_id"],
        },
    ),
    "get_inventory_status": (
        get_inventory_status,
        "Organization stock: item count, total stock value and items at or below their reorder level.",
        {"type": "object", "properties": {}},
    ),
    "find_inventory_items": (
        find_inventory_items,
        "Look up stock items by name, SKU or location: inventory, quantity on hand and per warehouse, unit, unit "
        "cost, reorder level. Each project has its own inventory; 'General stock' is the organization's own. "
        "Leave query empty to list all items; leave inventory empty to search every inventory.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "inventory": {"type": "string", "description": "A project name, or 'General stock'."},
        }},
    ),
    "list_warehouses": (
        list_warehouses,
        "Warehouses with their inventory, address and what each holds. Leave inventory empty for all.",
        {"type": "object", "properties": {
            "inventory": {"type": "string", "description": "A project name, or 'General stock'."},
        }},
    ),
    "propose_stock_changes": (
        propose_stock_changes,
        "Draft stock changes for the user to confirm (saves nothing): receive (stock arrived), issue (stock used), "
        "adjust (signed correction with a reason, e.g. -2 damaged), create (new item, optional opening quantity), "
        "transfer (between warehouses of the same inventory), move (to another inventory, e.g. General stock to a "
        "project), delete (remove an item for good). Every line is in an inventory: a project name, or omit for "
        "General stock. Use exact stored names from find_inventory_items / list_warehouses; one line per item.",
        {
            "type": "object",
            "properties": {
                "changes": {"type": "array", "items": {"type": "object", "properties": {
                    "kind": {"type": "string", "enum": list(stock_plans.KINDS)},
                    "inventory": {"type": "string", "description": "Project whose inventory this is; omit for General stock."},
                    "item": {"type": "string", "description": "Item name or SKU (the new item's name for create)."},
                    "warehouse": {"type": "string", "description": "Where stock arrives, leaves or is counted; for transfer and move, where it's taken from."},
                    "to_warehouse": {"type": "string", "description": "transfer/move: destination warehouse (omit = not in a warehouse)."},
                    "to_inventory": {"type": "string", "description": "move: destination project name, or 'General stock'."},
                    "quantity": {"type": "number", "description": "Positive; signed for adjust; opening stock for create."},
                    "project": {"type": "string", "description": "issue from General stock: the project it was used for."},
                    "note": {"type": "string", "description": "Reason (required for adjust) or short note, in the user's language."},
                    "unit": {"type": "string", "description": "create only, e.g. pcs, box, kg."},
                    "unit_cost": {"type": "number", "description": "create only."},
                    "reorder_level": {"type": "number", "description": "create only."},
                    "location": {"type": "string", "description": "create only."},
                    "sku": {"type": "string", "description": "create only."},
                }, "required": ["kind", "item"]}},
            },
            "required": ["changes"],
        },
    ),
    "calculate": (
        calculate,
        "Exact arithmetic. Use it for EVERY calculation you need (sums, differences, percentages, conversions). "
        "Numbers without thousands separators; + - * / % ** ( ) and round(x, places), abs, min, max.",
        {"type": "object", "properties": {"expression": {"type": "string", "description": "e.g. (12500 - 9800) / 12500 * 100"}},
         "required": ["expression"]},
    ),
    "vat": (
        vat,
        "VAT (TVA) on an amount: mode 'add' treats the amount as net and adds VAT; 'extract' treats it as gross (VAT included).",
        {"type": "object", "properties": {
            "amount": {"type": "number"}, "rate_pct": {"type": "number", "description": "Default 20."},
            "mode": {"type": "string", "enum": ["add", "extract"]}}, "required": ["amount"]},
    ),
    "budget_what_if": (
        budget_what_if,
        "What a project's budget figures would be after spending an extra amount (negative to remove). Nothing is saved.",
        {"type": "object", "properties": {**_PROJECT_ID, "additional_spend": {"type": "number"}},
         "required": ["project_id", "additional_spend"]},
    ),
    "estimate_trip_fuel_cost": (
        estimate_trip_fuel_cost,
        "Fuel cost range for a saved trip (by trip_id, or trip_title), using the trip's own route, vehicle and fuel "
        "price. Pass vehicle_type, vehicle_count or round_trip ONLY if the user asks about a different setup.",
        {"type": "object", "properties": {
            "trip_id": {"type": "integer"}, "trip_title": {"type": "string"},
            "vehicle_type": {"type": "string", "enum": list(travel.VEHICLES)},
            "vehicle_count": {"type": "integer"}, "round_trip": {"type": "boolean"}}},
    ),
    "estimate_fuel_cost": (
        estimate_fuel_cost,
        "Fuel cost range for a hypothetical drive between two Moroccan cities, or over distance_km (one way).",
        {"type": "object", "properties": {
            "from_city": {"type": "string"}, "to_city": {"type": "string"},
            "distance_km": {"type": "number"},
            "vehicle_type": {"type": "string", "enum": list(travel.VEHICLES)},
            "vehicle_count": {"type": "integer"}, "round_trip": {"type": "boolean"},
            "fuel_city": {"type": "string"}}},
    ),
    "propose_project": (
        propose_project,
        "Draft a NEW project (budget, YYYY-MM-DD dates, milestones, tasks) from a description. Saves nothing: the user "
        "edits and confirms it. Draft right away with sensible, stated assumptions; ask only if the goal is unclear.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "budget": {"type": "number"},
                "currency": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "milestones": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string"}, "due_date": {"type": "string"}}, "required": ["title"]}},
                "inventory": {"type": "array", "description": "Optional opening stock for the project's own inventory.",
                              "items": {"type": "object", "properties": {
                                  "name": {"type": "string"}, "unit": {"type": "string"}, "quantity": {"type": "number"},
                                  "unit_cost": {"type": "number"}}, "required": ["name"]}},
                "tasks": {"type": "array", "items": {"type": "object", "properties": {
                    "title": {"type": "string"}, "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                    "due_date": {"type": "string"},
                    "milestone": {"type": "string", "description": "A milestone title."}},
                    "required": ["title"]}},
            },
            "required": ["name"],
        },
    ),
    "draft_project_update": (
        draft_project_update,
        "Facts for drafting a project status update. The draft is for the user to review; nothing is sent.",
        {"type": "object", "properties": _PROJECT_ID, "required": ["project_id"]},
    ),
}


def tool_definitions() -> list[dict]:
    return [
        {"type": "function", "function": {"name": name, "description": desc, "parameters": params}}
        for name, (_, desc, params) in TOOLS.items()
    ]


def run_tool(ctx: ToolContext, name: str, raw_arguments: str) -> tuple[dict, dict, bool]:
    """Return (result for the model, parsed arguments for the trace, ok)."""
    if name not in TOOLS:
        return {"error": f"Unknown tool '{name}'."}, {}, False
    try:
        args = json.loads(raw_arguments or "{}")
    except (ValueError, TypeError):
        return {"error": "Arguments must be a JSON object."}, {}, False
    if not isinstance(args, dict):
        return {"error": "Arguments must be a JSON object."}, {}, False
    # The trace is shown to the user: keep only declared, short, scalar arguments.
    known = TOOLS[name][2].get("properties", {})
    shown = {
        k: v for k, v in args.items() if k in known and isinstance(v, (int, bool, str)) and len(str(v)) <= 40
    }
    try:
        return TOOLS[name][0](ctx, args), shown, True
    except ToolError as e:
        return {"error": str(e)}, shown, False
