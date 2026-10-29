"""Project queries and metric assembly. All arithmetic is delegated to services.metrics."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import ApiError
from ..extensions import db
from ..models import Expense, Project, ProjectStatus, Task
from . import metrics
from .permissions import get_membership


def org_today(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def get_project_for_user(project_id: int, user_id: int):
    """Return (project, membership); 404 for unknown projects and for outsiders alike."""
    project = db.session.get(Project, project_id)
    if project is None:
        raise ApiError("not_found", "Project not found.", 404)
    try:
        membership = get_membership(project.organization_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Project not found.", 404)
    return project, membership


def _group(rows: Iterable, key: str) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        grouped[getattr(row, key)].append(row)
    return grouped


def load_expenses(project_ids: list[int]) -> dict:
    if not project_ids:
        return {}
    return _group(Expense.query.filter(Expense.project_id.in_(project_ids)).all(), "project_id")


def load_tasks(project_ids: list[int]) -> dict:
    if not project_ids:
        return {}
    return _group(Task.query.filter(Task.project_id.in_(project_ids)).all(), "project_id")


def project_metrics(project: Project, expenses: list, tasks: list, today: date) -> dict:
    b = metrics.calculate_budget_metrics(project.budget, expenses)
    return {
        "budget": b.budget,
        "actual": b.actual,
        "remaining": b.remaining,
        "variance": b.variance,
        "consumed_pct": b.consumed_pct,  # None when the budget is zero
        "task_completion_pct": metrics.task_completion_pct(tasks),
        "overdue_task_count": len(metrics.overdue_tasks(tasks, today)),
        "over_budget": b.variance > 0,
    }


def organization_summary(org_id: int, tz_name: str) -> dict:
    """Totals across non-archived projects, grouped by currency (one currency per project)."""
    projects = Project.query.filter(
        Project.organization_id == org_id, Project.status != ProjectStatus.ARCHIVED
    ).all()
    ids = [p.id for p in projects]
    expenses, tasks = load_expenses(ids), load_tasks(ids)
    today = org_today(tz_name)

    by_currency: dict[str, dict] = {}
    over_budget_projects = 0
    overdue_tasks = 0
    for p in projects:
        m = project_metrics(p, expenses.get(p.id, []), tasks.get(p.id, []), today)
        t = by_currency.setdefault(
            p.currency, {"currency": p.currency, "budget": Decimal("0"), "actual": Decimal("0")}
        )
        t["budget"] += m["budget"]
        t["actual"] += m["actual"]
        over_budget_projects += 1 if m["over_budget"] else 0
        overdue_tasks += m["overdue_task_count"]

    totals = []
    for currency in sorted(by_currency):
        t = by_currency[currency]
        totals.append(
            {
                "currency": currency,
                "budget": metrics.q(t["budget"]),
                "actual": metrics.q(t["actual"]),
                "remaining": metrics.remaining_budget(t["budget"], t["actual"]),
            }
        )
    return {
        "totals": totals,
        "project_count": len(projects),
        "over_budget_project_count": over_budget_projects,
        "overdue_task_count": overdue_tasks,
    }
