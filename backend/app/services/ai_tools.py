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
from ..models import Project, ProjectStatus, Task, User
from . import metrics
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
        "Current facts for one project: status, dates, budget figures, task counts and completion.",
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
