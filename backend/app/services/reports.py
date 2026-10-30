"""Project report (FR-11) and CSV exports. Figures come from services.metrics only."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from ..models import Milestone, Organization, Project, Task, User, utcnow
from . import metrics
from . import projects as svc

UPCOMING_DAYS = 14
# Spreadsheet apps run cells starting with these as formulas ("CSV injection").
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _m(value) -> str | None:
    return None if value is None else f"{Decimal(value):.2f}"


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _names(user_ids) -> dict[int, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    return {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(ids)).all()}


def _task_row(t: Task, today: date, names: dict, milestone_titles: dict) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status.value,
        "priority": t.priority.value,
        "due_date": _iso(t.due_date),
        "assignee": names.get(t.assignee_id),
        "milestone": milestone_titles.get(t.milestone_id),
        "days_overdue": (today - t.due_date).days if metrics.is_overdue(t, today) else None,
    }


def build_report(project: Project, org: Organization) -> dict:
    today = svc.org_today(org.timezone)
    expenses = svc.load_expenses([project.id]).get(project.id, [])
    tasks = svc.load_tasks([project.id]).get(project.id, [])
    m = svc.project_metrics(project, expenses, tasks, today)
    actual = m["actual"]

    def breakdown(group_by: str) -> list[dict]:
        return [
            {
                "group": r["key"],
                "total": _m(r["total"]),
                "expense_count": r["count"],
                "share_pct": _m(metrics.share_pct(r["total"], actual)),
            }
            for r in metrics.expense_breakdown(expenses, group_by)
        ]

    milestones = (
        Milestone.query.filter_by(project_id=project.id)
        .order_by(Milestone.due_date.is_(None), Milestone.due_date, Milestone.id)
        .all()
    )
    titles = {ms.id: ms.title for ms in milestones}
    names = _names(t.assignee_id for t in tasks)
    by_status: dict[str, int] = {}
    for t in tasks:
        by_status[t.status.value] = by_status.get(t.status.value, 0) + 1

    overdue = sorted(metrics.overdue_tasks(tasks, today), key=lambda t: (t.due_date, t.id))
    horizon = today + timedelta(days=UPCOMING_DAYS)
    upcoming = sorted(
        (
            t
            for t in tasks
            if t.due_date and today <= t.due_date <= horizon and t.status.value not in (metrics.DONE, metrics.CANCELLED)
        ),
        key=lambda t: (t.due_date, t.id),
    )

    milestone_rows = []
    for ms in milestones:
        linked = [t for t in tasks if t.milestone_id == ms.id]
        milestone_rows.append(
            {
                "title": ms.title,
                "due_date": _iso(ms.due_date),
                "status": ms.status,
                "is_overdue": metrics.is_milestone_overdue(ms, today),
                "task_count": len(linked),
                "task_completion_pct": _m(metrics.task_completion_pct(linked)),
            }
        )

    owner = _names([project.owner_id]).get(project.owner_id)
    return {
        "generated_at": utcnow().isoformat(),
        "as_of": today.isoformat(),
        "organization": {"name": org.name, "timezone": org.timezone},
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status.value,
            "owner": owner,
            "start_date": _iso(project.start_date),
            "end_date": _iso(project.end_date),
            "currency": project.currency,
        },
        "budget": {
            "approved": _m(m["budget"]),
            "actual": _m(actual),
            "remaining": _m(m["remaining"]),
            "variance": _m(m["variance"]),
            "consumed_pct": _m(m["consumed_pct"]),
            "over_budget": m["over_budget"],
            "valid_expense_count": sum(1 for e in expenses if e.status.value == metrics.VALID_EXPENSE_STATUS),
            "excluded_expense_count": sum(1 for e in expenses if e.status.value != metrics.VALID_EXPENSE_STATUS),
        },
        "spending_by_category": breakdown("category"),
        "spending_by_month": breakdown("month"),
        "tasks": {
            "total": len(tasks),
            "by_status": by_status,
            "completion_pct": _m(m["task_completion_pct"]),
            "overdue": [_task_row(t, today, names, titles) for t in overdue],
            "upcoming": [_task_row(t, today, names, titles) for t in upcoming],
        },
        "milestones": milestone_rows,
        "definitions": {
            "actual": "Sum of valid expenses; voided and refunded entries are excluded.",
            "variance": "Actual minus approved budget; positive means over budget.",
            "completion": "Done tasks / tasks that aren't cancelled.",
            "overdue": "Not done or cancelled, due before today in the organization's timezone.",
        },
    }


# ---------- CSV ----------


def _safe(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe(v) for v in row])
    # BOM so Excel reads accents and Arabic text as UTF-8.
    return "﻿" + buf.getvalue()


def expenses_csv(project: Project) -> str:
    expenses = sorted(
        svc.load_expenses([project.id]).get(project.id, []), key=lambda e: (e.expense_date, e.id)
    )
    names = _names(e.created_by for e in expenses)
    rows = [
        [e.expense_date.isoformat(), e.category, f"{Decimal(e.amount):.2f}", e.currency, e.status.value,
         e.description, names.get(e.created_by)]
        for e in expenses
    ]
    return _csv(["date", "category", "amount", "currency", "status", "description", "recorded_by"], rows)


def tasks_csv(project: Project, org: Organization) -> str:
    today = svc.org_today(org.timezone)
    tasks = svc.load_tasks([project.id]).get(project.id, [])
    tasks.sort(key=lambda t: (t.due_date is None, t.due_date or date.max, t.id))
    names = _names(t.assignee_id for t in tasks)
    titles = {ms.id: ms.title for ms in Milestone.query.filter_by(project_id=project.id).all()}
    rows = [
        [t.title, t.status.value, t.priority.value, _iso(t.due_date), names.get(t.assignee_id),
         titles.get(t.milestone_id), t.completed_at.date().isoformat() if t.completed_at else None,
         "yes" if metrics.is_overdue(t, today) else "no"]
        for t in tasks
    ]
    return _csv(["title", "status", "priority", "due_date", "assignee", "milestone", "completed_on", "overdue"], rows)
