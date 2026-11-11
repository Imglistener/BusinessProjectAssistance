"""Changes the assistant drafts for the user: tasks, milestones, projects, expenses, trips, fuel prices and
notifications. Nothing is saved here. Each draft line becomes one request to the app's own API, which the browser
sends with the user's session once they confirm, so the same validation and permission checks apply as when they
click the button themselves. The checks below only say up front which lines the user may confirm.

Not offered, even with confirmation: deleting projects or trips for good, members, roles and invitations, and
file uploads. Stock has its own drafts (stock_plans).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from ..models import (
    Expense,
    Milestone,
    OrganizationMember,
    Project,
    ProjectStatus,
    Role,
    Task,
    TaskPriority,
    TaskStatus,
    Trip,
    TripStatus,
    User,
)
from .permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES
from .stock_plans import _match

MAX_ACTIONS = 25

# Editable project statuses ("archived" has its own actions).
PROJECT_STATUSES = ("planned", "active", "on_hold", "completed")
MILESTONE_STATUSES = ("open", "done")
FUEL_TYPES = ("petrol", "diesel")

UNKNOWN = "Unknown action: {kind}."
NOTHING = "Nothing to change."
NO_PROJECT = "No project called {name}."
SEVERAL = "Several projects match: {names}. Say which one."
NO_MEMBER = "No member called {name}."
NO_MILESTONE = "No milestone called {name} in this project."
BAD_DATE = "Not a valid date: {value}. Use YYYY-MM-DD."
BAD_AMOUNT = "The amount must be a positive number."
BAD_VALUE = "Not a valid {field}: {value}."
ARCHIVED = "This project is archived. Restore it to make changes."
NOT_ARCHIVED = "This project isn't archived."
ALREADY_ARCHIVED = "This project is already archived."
MISSING = "Missing {field}."


class _Bad(Exception):
    pass


def _bad(message: str, **values) -> _Bad:
    return _Bad(message.format(**values) if values else message)


class _Context:
    def __init__(self, organization_id: int, user_id: int, role: Role):
        self.org = organization_id
        self.user_id = user_id
        self.role = role
        self.projects = Project.query.filter_by(organization_id=organization_id).all()
        members = (
            OrganizationMember.query.filter_by(organization_id=organization_id, status="active")
            .join(User, User.id == OrganizationMember.user_id)
            .with_entities(User)
            .all()
        )
        self.members = members

    @property
    def can_manage(self) -> bool:
        return self.role in PROJECT_WRITE_ROLES

    @property
    def can_contribute(self) -> bool:
        return self.role in CONTRIBUTE_ROLES

    def project(self, a: dict) -> Project:
        pid = a.get("project_id")
        if isinstance(pid, int) and not isinstance(pid, bool):
            for p in self.projects:
                if p.id == pid:
                    return p
        name = a.get("project")
        if isinstance(name, str) and name.strip():
            found, candidates = _match(self.projects, name)
            if found is not None:
                return found
            if candidates:
                raise _bad(SEVERAL, names=", ".join(candidates))
            raise _bad(NO_PROJECT, name=name.strip())
        raise _bad(MISSING, field="project")

    def owned(self, model, a: dict, key: str, label: str):
        """A task, milestone, expense or trip of this organization, by ID."""
        rid = a.get(key)
        row = None
        if isinstance(rid, int) and not isinstance(rid, bool):
            row = model.query.filter_by(id=rid).first()
        project = next((p for p in self.projects if row is not None and p.id == row.project_id), None)
        if row is None or project is None:
            raise _bad(f"{label} not found.")
        return row, project

    def member(self, name: Any) -> Optional[int]:
        if name in (None, ""):
            return None
        if not isinstance(name, str):
            raise _bad(NO_MEMBER, name=str(name))
        found, candidates = _match(
            self.members, name, label=lambda u: f"{u.first_name} {u.last_name}", extra=lambda u: (u.email, u.first_name)
        )
        if found is None:
            raise _bad(SEVERAL if candidates else NO_MEMBER, names=", ".join(candidates), name=name)
        return found.id

    def member_name(self, user_id: Optional[int]) -> Optional[str]:
        u = next((m for m in self.members if m.id == user_id), None)
        return f"{u.first_name} {u.last_name}" if u else None


def _date(a: dict, key: str, required: bool = False) -> Optional[str]:
    value = a.get(key)
    if value in (None, ""):
        if required:
            raise _bad(MISSING, field=key)
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise _bad(BAD_DATE, value=value)


def _money(a: dict, key: str, required: bool = False) -> Optional[str]:
    value = a.get(key)
    if value in (None, ""):
        if required:
            raise _bad(MISSING, field=key)
        return None
    try:
        amount = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        raise _bad(BAD_AMOUNT)
    if amount <= 0:
        raise _bad(BAD_AMOUNT)
    return f"{amount.quantize(Decimal('0.01'))}"


def _choice(a: dict, key: str, allowed) -> Optional[str]:
    value = a.get(key)
    if value in (None, ""):
        return None
    v = str(value).strip().lower().replace(" ", "_")
    if v not in allowed:
        raise _bad(BAD_VALUE, field=key, value=value)
    return v


def _text(a: dict, key: str, required: bool = False, max_len: int = 200) -> Optional[str]:
    value = a.get(key)
    if not isinstance(value, str) or not value.strip():
        if required:
            raise _bad(MISSING, field=key)
        return None
    return value.strip()[:max_len]


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _enum(v) -> Optional[str]:
    return getattr(v, "value", v)


def _change(changes: list, body: dict, field: str, before, after, api_field: Optional[str] = None) -> None:
    if after is None or str(after) == str(before if before is not None else ""):
        return
    changes.append({"field": field, "before": None if before is None else str(before), "after": str(after)})
    body[api_field or field] = after


def _active(project: Project) -> None:
    if project.status == ProjectStatus.ARCHIVED:
        raise _bad(ARCHIVED)


# --- one builder per action kind: (ctx, args) -> line fields ------------------------------------------------


def _update_project(c: _Context, a: dict) -> dict:
    p = c.project(a)
    _active(p)
    changes, body = [], {}
    _change(changes, body, "name", p.name, _text(a, "name"))
    _change(changes, body, "description", p.description, _text(a, "description", max_len=5000))
    _change(changes, body, "budget", f"{p.budget:.2f}", _money(a, "budget"))
    _change(changes, body, "start_date", _iso(p.start_date), _date(a, "start_date"))
    _change(changes, body, "end_date", _iso(p.end_date), _date(a, "end_date"))
    _change(changes, body, "status", _enum(p.status), _choice(a, "status", PROJECT_STATUSES))
    return dict(project=p, target=p.name, changes=changes, allowed=c.can_manage,
                request=("PATCH", f"/projects/{p.id}", body))


def _archive_project(c: _Context, a: dict) -> dict:
    p = c.project(a)
    if p.status == ProjectStatus.ARCHIVED:
        raise _bad(ALREADY_ARCHIVED)
    return dict(project=p, target=p.name, changes=[{"field": "status", "before": _enum(p.status), "after": "archived"}],
                allowed=c.can_manage, request=("POST", f"/projects/{p.id}/archive", None))


def _restore_project(c: _Context, a: dict) -> dict:
    p = c.project(a)
    if p.status != ProjectStatus.ARCHIVED:
        raise _bad(NOT_ARCHIVED)
    return dict(project=p, target=p.name, changes=[{"field": "status", "before": "archived", "after": "active"}],
                allowed=c.can_manage, request=("PATCH", f"/projects/{p.id}", {"status": "active"}))


def _milestone_id(p: Project, title: Any) -> Optional[int]:
    if title in (None, ""):
        return None
    rows = Milestone.query.filter_by(project_id=p.id).all()
    found, _ = _match(rows, str(title), label=lambda m: m.title)
    if found is None:
        raise _bad(NO_MILESTONE, name=title)
    return found.id


def _create_task(c: _Context, a: dict) -> dict:
    p = c.project(a)
    _active(p)
    title = _text(a, "title", required=True)
    body: dict = {"title": title}
    changes = [{"field": "title", "before": None, "after": title}]
    for field, value in (
        ("due_date", _date(a, "due_date")),
        ("priority", _choice(a, "priority", [x.value for x in TaskPriority])),
        ("description", _text(a, "description", max_len=5000)),
    ):
        if value is not None:
            body[field] = value
            changes.append({"field": field, "before": None, "after": value})
    assignee = c.member(a.get("assignee"))
    if assignee is not None:
        body["assignee_id"] = assignee
        changes.append({"field": "assignee", "before": None, "after": c.member_name(assignee)})
    milestone = _milestone_id(p, a.get("milestone"))
    if milestone is not None:
        body["milestone_id"] = milestone
        changes.append({"field": "milestone", "before": None, "after": str(a.get("milestone"))})
    return dict(project=p, target=title, changes=changes, allowed=c.can_contribute,
                request=("POST", f"/projects/{p.id}/tasks", body))


def _update_task(c: _Context, a: dict) -> dict:
    t, p = c.owned(Task, a, "task_id", "Task")
    _active(p)
    changes, body = [], {}
    _change(changes, body, "title", t.title, _text(a, "title"))
    _change(changes, body, "status", _enum(t.status), _choice(a, "status", [x.value for x in TaskStatus]))
    _change(changes, body, "priority", _enum(t.priority), _choice(a, "priority", [x.value for x in TaskPriority]))
    _change(changes, body, "due_date", _iso(t.due_date), _date(a, "due_date"))
    if a.get("assignee") not in (None, ""):
        new = c.member(a.get("assignee"))
        if new != t.assignee_id:
            changes.append({"field": "assignee", "before": c.member_name(t.assignee_id), "after": c.member_name(new)})
            body["assignee_id"] = new
    if a.get("milestone") not in (None, ""):
        new = _milestone_id(p, a.get("milestone"))
        if new != t.milestone_id:
            changes.append({"field": "milestone", "before": None, "after": str(a.get("milestone"))})
            body["milestone_id"] = new
    # Contributors may only change the status of tasks assigned to them (same rule as the API).
    allowed = c.can_manage or (c.role == Role.CONTRIBUTOR and t.assignee_id == c.user_id and set(body) <= {"status"})
    return dict(project=p, target=t.title, changes=changes, allowed=allowed,
                request=("PATCH", f"/tasks/{t.id}", body))


def _create_milestone(c: _Context, a: dict) -> dict:
    p = c.project(a)
    _active(p)
    title = _text(a, "title", required=True)
    body: dict = {"title": title}
    changes = [{"field": "title", "before": None, "after": title}]
    due = _date(a, "due_date")
    if due:
        body["due_date"] = due
        changes.append({"field": "due_date", "before": None, "after": due})
    return dict(project=p, target=title, changes=changes, allowed=c.can_manage,
                request=("POST", f"/projects/{p.id}/milestones", body))


def _update_milestone(c: _Context, a: dict) -> dict:
    m, p = c.owned(Milestone, a, "milestone_id", "Milestone")
    _active(p)
    changes, body = [], {}
    _change(changes, body, "title", m.title, _text(a, "title"))
    _change(changes, body, "due_date", _iso(m.due_date), _date(a, "due_date"))
    _change(changes, body, "milestone_status", m.status, _choice(a, "status", MILESTONE_STATUSES), api_field="status")
    return dict(project=p, target=m.title, changes=changes, allowed=c.can_manage,
                request=("PATCH", f"/milestones/{m.id}", body))


def _delete_milestone(c: _Context, a: dict) -> dict:
    m, p = c.owned(Milestone, a, "milestone_id", "Milestone")
    _active(p)
    return dict(project=p, target=m.title, changes=[], allowed=c.can_manage,
                request=("DELETE", f"/milestones/{m.id}", None))


def _add_expense(c: _Context, a: dict) -> dict:
    p = c.project(a)
    _active(p)
    body = {
        "category": _text(a, "category", required=True, max_len=80),
        "amount": _money(a, "amount", required=True),
        "expense_date": _date(a, "expense_date", required=True),
    }
    description = _text(a, "description", max_len=5000)
    if description:
        body["description"] = description
    trip_id = a.get("trip_id")
    if isinstance(trip_id, int) and not isinstance(trip_id, bool):
        trip, trip_project = c.owned(Trip, a, "trip_id", "Trip")
        if trip_project.id != p.id:
            raise _bad("Trip not found.")
        body["trip_id"] = trip.id
    changes = [{"field": k, "before": None, "after": v} for k, v in body.items() if k != "trip_id"]
    return dict(project=p, target=body["category"], changes=changes, allowed=c.can_contribute,
                request=("POST", f"/projects/{p.id}/expenses", body), currency=p.currency)


def _void_expense(c: _Context, a: dict) -> dict:
    e, p = c.owned(Expense, a, "expense_id", "Expense")
    _active(p)
    if _enum(e.status) == "voided":
        raise _bad(NOTHING)
    allowed = c.can_manage or (c.role == Role.CONTRIBUTOR and e.created_by == c.user_id)
    target = f"{e.category} · {e.amount:.2f} {e.currency} · {e.expense_date.isoformat()}"
    return dict(project=p, target=target, changes=[{"field": "expense_status", "before": _enum(e.status), "after": "voided"}],
                allowed=allowed, request=("POST", f"/expenses/{e.id}/void", None))


def _create_trip(c: _Context, a: dict) -> dict:
    p = c.project(a)
    _active(p)
    body = {
        "title": _text(a, "title", required=True),
        "destination": _text(a, "destination", required=True),
        "start_date": _date(a, "start_date", required=True),
        "end_date": _date(a, "end_date", required=True),
    }
    for key, value in (("purpose", _text(a, "purpose", max_len=5000)), ("budget", _money(a, "budget"))):
        if value is not None:
            body[key] = value
    changes = [{"field": k, "before": None, "after": v} for k, v in body.items()]
    return dict(project=p, target=body["title"], changes=changes, allowed=c.can_contribute,
                request=("POST", f"/projects/{p.id}/trips", body), currency=p.currency)


def _update_trip(c: _Context, a: dict) -> dict:
    t, p = c.owned(Trip, a, "trip_id", "Trip")
    _active(p)
    changes, body = [], {}
    _change(changes, body, "title", t.title, _text(a, "title"))
    _change(changes, body, "destination", t.destination, _text(a, "destination"))
    _change(changes, body, "start_date", _iso(t.start_date), _date(a, "start_date"))
    _change(changes, body, "end_date", _iso(t.end_date), _date(a, "end_date"))
    _change(changes, body, "trip_status", _enum(t.status), _choice(a, "status", [x.value for x in TripStatus]),
            api_field="status")
    _change(changes, body, "budget", None if t.budget is None else f"{t.budget:.2f}", _money(a, "budget"))
    allowed = c.can_manage or (c.role == Role.CONTRIBUTOR and t.created_by == c.user_id)
    return dict(project=p, target=t.title, changes=changes, allowed=allowed,
                request=("PATCH", f"/trips/{t.id}", body), currency=p.currency)


def _refresh_fuel_prices(c: _Context, a: dict) -> dict:
    return dict(project=None, target=None, changes=[], allowed=c.can_manage,
                request=("POST", f"/organizations/{c.org}/fuel-prices/sync", None))


def _set_fuel_price(c: _Context, a: dict) -> dict:
    fuel = _choice(a, "fuel_type", FUEL_TYPES)
    if fuel is None:
        raise _bad(MISSING, field="fuel_type")
    price = _money(a, "price_per_litre", required=True)
    city = _text(a, "city", max_len=80) or ""
    body = {"fuel_type": fuel, "price_per_litre": price, "city": city}
    changes = [{"field": "fuel_type", "before": None, "after": fuel}, {"field": "price_per_litre", "before": None, "after": price}]
    if city:
        changes.append({"field": "city", "before": None, "after": city})
    return dict(project=None, target=city or None, changes=changes, allowed=c.can_manage,
                request=("PUT", f"/organizations/{c.org}/fuel-prices", body))


def _mark_notifications_read(c: _Context, a: dict) -> dict:
    return dict(project=None, target=None, changes=[], allowed=True, request=("POST", "/notifications/read-all", None))


BUILDERS: dict[str, Callable[[_Context, dict], dict]] = {
    "update_project": _update_project,
    "archive_project": _archive_project,
    "restore_project": _restore_project,
    "create_task": _create_task,
    "update_task": _update_task,
    "create_milestone": _create_milestone,
    "update_milestone": _update_milestone,
    "delete_milestone": _delete_milestone,
    "add_expense": _add_expense,
    "void_expense": _void_expense,
    "create_trip": _create_trip,
    "update_trip": _update_trip,
    "refresh_fuel_prices": _refresh_fuel_prices,
    "set_fuel_price": _set_fuel_price,
    "mark_notifications_read": _mark_notifications_read,
}
KINDS = tuple(BUILDERS)
# Lines whose request changes nothing but are still worth confirming (no field changes to show).
NO_CHANGES_NEEDED = {"archive_project", "restore_project", "delete_milestone", "void_expense", "refresh_fuel_prices",
                     "mark_notifications_read"}


def draft_actions(organization_id: int, user_id: int, role: Role, raw: Any) -> dict:
    """Validate and describe the actions; each line carries the request the browser sends on confirmation."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("Give at least one action.")
    if len(raw) > MAX_ACTIONS:
        raise ValueError(f"At most {MAX_ACTIONS} actions at a time.")
    c = _Context(organization_id, user_id, role)
    lines = []
    for a in raw:
        a = a if isinstance(a, dict) else {}
        kind = a.get("kind") if isinstance(a.get("kind"), str) else ""
        line = {"kind": kind, "target": None, "project_id": None, "project_name": None, "changes": [],
                "request": None, "allowed": False, "error": None, "currency": None}
        try:
            builder = BUILDERS.get(kind)
            if builder is None:
                raise _bad(UNKNOWN, kind=kind or "?")
            built = builder(c, a)
            method, path, body = built["request"]
            if kind not in NO_CHANGES_NEEDED and not built["changes"]:
                raise _bad(NOTHING)
            project = built.get("project")
            line.update(
                target=built.get("target"),
                project_id=project.id if project else None,
                project_name=project.name if project else None,
                changes=built["changes"],
                request={"method": method, "path": path, "body": body},
                allowed=bool(built["allowed"]),
                currency=built.get("currency") or (project.currency if project else None),
            )
        except _Bad as e:
            line["error"] = str(e)
        lines.append(line)
    return {"lines": lines, "can_apply": any(l["allowed"] and not l["error"] for l in lines)}
