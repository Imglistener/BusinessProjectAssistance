"""Project queries and metric assembly. All arithmetic is delegated to services.metrics."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import ApiError
from ..extensions import db
from ..models import Expense, Milestone, Project, ProjectStatus, Role, Task, Trip, TripStatus, User
from . import metrics
from .notifications import members_with_roles, notify
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


def require_active_project(project: Project) -> None:
    """Archived projects are read-only; restore one (status -> active) before changing its records."""
    if project.status == ProjectStatus.ARCHIVED:
        raise ApiError("project_archived", "This project is archived. Restore it to make changes.", 409)


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


def is_over_budget(project: Project) -> bool:
    expenses = load_expenses([project.id]).get(project.id, [])
    return metrics.calculate_budget_metrics(project.budget, expenses).variance > 0


def notify_if_now_over_budget(project: Project, was_over: bool, actor_id: int) -> None:
    """Tell the project's owner and the organization owners when a change tips the project over budget."""
    if was_over or not is_over_budget(project):
        return
    notify(
        organization_id=project.organization_id,
        user_ids=[project.owner_id, *members_with_roles(project.organization_id, Role.OWNER)],
        actor_id=actor_id,
        kind="project_over_budget",
        title=f"{project.name} is over budget",
        body="Recorded spending is now above the approved budget.",
        link=f"/app/projects/{project.id}",
    )


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


DEADLINE_HORIZON_DAYS = 14
MAX_DEADLINES = 20
MAX_MY_TASKS = 10


def _open_task(t: Task) -> bool:
    return t.status.value not in (metrics.DONE, metrics.CANCELLED)


def deadlines(org_id: int, tz_name: str, user_id: int) -> dict:
    """Overdue and soon-due tasks and milestones across active projects, plus the user's open tasks."""
    today = org_today(tz_name)
    horizon = today + timedelta(days=DEADLINE_HORIZON_DAYS)
    projects = {
        p.id: p
        for p in Project.query.filter(Project.organization_id == org_id, Project.status != ProjectStatus.ARCHIVED)
    }
    ids = list(projects)
    tasks = Task.query.filter(Task.project_id.in_(ids)).all() if ids else []
    milestones = Milestone.query.filter(Milestone.project_id.in_(ids)).all() if ids else []
    names = {}
    assignee_ids = {t.assignee_id for t in tasks if t.assignee_id}
    if assignee_ids:
        names = {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(assignee_ids))}

    def task_item(t: Task) -> dict:
        return {
            "kind": "task",
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "days_until_due": (t.due_date - today).days if t.due_date else None,
            "overdue": metrics.is_overdue(t, today),
            "project_id": t.project_id,
            "project_name": projects[t.project_id].name,
            "assignee": names.get(t.assignee_id),
            "priority": t.priority.value,
            "status": t.status.value,
        }

    items = [task_item(t) for t in tasks if _open_task(t) and t.due_date and t.due_date <= horizon]
    for m in milestones:
        if m.due_date and m.due_date <= horizon and m.status != metrics.MILESTONE_DONE:
            items.append(
                {
                    "kind": "milestone",
                    "id": m.id,
                    "title": m.title,
                    "due_date": m.due_date.isoformat(),
                    "days_until_due": (m.due_date - today).days,
                    "overdue": metrics.is_milestone_overdue(m, today),
                    "project_id": m.project_id,
                    "project_name": projects[m.project_id].name,
                }
            )
    trips = (
        Trip.query.filter(
            Trip.project_id.in_(ids),
            Trip.start_date >= today,
            Trip.start_date <= horizon,
            Trip.status.in_([TripStatus.PLANNED, TripStatus.BOOKED]),
        ).all()
        if ids
        else []
    )
    for t in trips:
        items.append(
            {
                "kind": "trip",
                "id": t.id,
                "title": f"{t.title} ({t.destination})",
                "due_date": t.start_date.isoformat(),
                "days_until_due": (t.start_date - today).days,
                "overdue": False,
                "project_id": t.project_id,
                "project_name": projects[t.project_id].name,
            }
        )
    order = {"milestone": 0, "trip": 1, "task": 2}
    items.sort(key=lambda i: (i["due_date"], order[i["kind"]], i["id"]))

    mine = sorted(
        (t for t in tasks if t.assignee_id == user_id and _open_task(t)),
        key=lambda t: (t.due_date is None, t.due_date or date.max, t.id),
    )
    return {
        "as_of": today.isoformat(),
        "horizon_days": DEADLINE_HORIZON_DAYS,
        "items": items[:MAX_DEADLINES],
        "item_count": len(items),
        "my_tasks": [task_item(t) for t in mine[:MAX_MY_TASKS]],
        "my_task_count": len(mine),
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
                "consumed_pct": metrics.budget_consumed_pct(t["budget"], t["actual"]),
            }
        )
    return {
        "totals": totals,
        "project_count": len(projects),
        "over_budget_project_count": over_budget_projects,
        "overdue_task_count": overdue_tasks,
    }
