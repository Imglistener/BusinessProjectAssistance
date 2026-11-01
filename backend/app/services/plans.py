"""Project plans drafted by the assistant from a customer's description.

A plan is only data until a person confirms it: the assistant's `propose_project` tool validates and
returns it, and `POST /organizations/:id/projects/from-plan` validates it again (never trusting the
draft) before creating the project, its milestones, tasks and opening inventory in one transaction.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_MILESTONES = 20
MAX_TASKS = 50
MAX_INVENTORY = 50
MAX_QUANTITY = Decimal("9999999999.99")
MAX_YEARS = 5
PRIORITIES = ("low", "medium", "high")


class PlanError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def _text(data: dict, key: str, *, required: bool, max_len: int, label: str) -> str | None:
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise PlanError(f"{label} is required.", key)
        return None
    if not isinstance(value, str):
        raise PlanError(f"{label} must be text.", key)
    value = value.strip()
    if len(value) > max_len:
        raise PlanError(f"{label} is too long.", key)
    return value


def _date(value: Any, field: str, today: date) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PlanError("Dates must look like 2026-11-30.", field)
    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise PlanError("Dates must look like 2026-11-30.", field)
    if abs((d - today).days) > 365 * MAX_YEARS:
        raise PlanError("That date is too far from today.", field)
    return d


def _money(value: Any, field: str) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PlanError("The budget must be an amount.", field)
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise PlanError("The budget must be an amount.", field)
    if not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99"):
        raise PlanError("The budget must be a positive amount.", field)
    return amount.quantize(Decimal("0.01"))


def validate_plan(data: Any, *, default_currency: str, today: date) -> dict:
    """A clean plan (JSON-friendly) or PlanError naming the problem."""
    if not isinstance(data, dict):
        raise PlanError("The plan must be an object.")
    name = _text(data, "name", required=True, max_len=200, label="Project name")
    description = _text(data, "description", required=False, max_len=5000, label="Description")
    currency = (_text(data, "currency", required=False, max_len=3, label="Currency") or default_currency).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise PlanError("Currency must be a 3-letter code, like MAD.", "currency")
    budget = _money(data.get("budget"), "budget")
    start = _date(data.get("start_date"), "start_date", today)
    end = _date(data.get("end_date"), "end_date", today)
    if start and end and end < start:
        raise PlanError("The end date can't be before the start date.", "end_date")

    raw_milestones = data.get("milestones") or []
    if not isinstance(raw_milestones, list) or len(raw_milestones) > MAX_MILESTONES:
        raise PlanError(f"At most {MAX_MILESTONES} milestones.", "milestones")
    milestones = []
    titles = set()
    for m in raw_milestones:
        if not isinstance(m, dict):
            raise PlanError("Each milestone needs a title.", "milestones")
        title = _text(m, "title", required=True, max_len=200, label="Milestone title")
        if title.lower() in titles:
            raise PlanError(f"Two milestones are called '{title}'.", "milestones")
        titles.add(title.lower())
        milestones.append({"title": title, "due_date": _iso(_date(m.get("due_date"), "milestones", today))})

    raw_tasks = data.get("tasks") or []
    if not isinstance(raw_tasks, list) or len(raw_tasks) > MAX_TASKS:
        raise PlanError(f"At most {MAX_TASKS} tasks.", "tasks")
    tasks = []
    for t in raw_tasks:
        if not isinstance(t, dict):
            raise PlanError("Each task needs a title.", "tasks")
        priority = t.get("priority") or "medium"
        if priority not in PRIORITIES:
            raise PlanError("Task priority must be low, medium or high.", "tasks")
        milestone = _text(t, "milestone", required=False, max_len=200, label="Milestone")
        if milestone and milestone.lower() not in titles:
            milestone = None  # a task pointing at an unknown milestone just stays unlinked
        tasks.append(
            {
                "title": _text(t, "title", required=True, max_len=200, label="Task title"),
                "description": _text(t, "description", required=False, max_len=2000, label="Task description"),
                "priority": priority,
                "due_date": _iso(_date(t.get("due_date"), "tasks", today)),
                "milestone": milestone,
            }
        )
    return {
        "inventory": validate_inventory(data.get("inventory")),
        "name": name,
        "description": description,
        "currency": currency,
        "budget": None if budget is None else f"{budget:.2f}",
        "start_date": _iso(start),
        "end_date": _iso(end),
        "milestones": milestones,
        "tasks": tasks,
    }


def _quantity(value: Any, label: str) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PlanError(f"{label} must be a number.", "inventory")
    try:
        d = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise PlanError(f"{label} must be a number.", "inventory")
    if not d.is_finite() or d < 0 or d > MAX_QUANTITY:
        raise PlanError(f"{label} must be zero or more.", "inventory")
    return d.quantize(Decimal("0.01"))


def validate_inventory(raw: Any) -> list[dict]:
    """A new project's opening inventory: [{name, unit, quantity, unit_cost, reorder_level}]."""
    try:
        return _inventory(raw)
    except PlanError as e:
        raise PlanError(str(e), "inventory")  # errors point at the inventory list, not a project field


def _inventory(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_INVENTORY:
        raise PlanError(f"At most {MAX_INVENTORY} inventory items.", "inventory")
    items, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            raise PlanError("Each inventory item needs a name.", "inventory")
        name = _text(row, "name", required=True, max_len=200, label="Item name")
        if name.lower() in seen:
            raise PlanError(f"Two inventory items are called '{name}'.", "inventory")
        seen.add(name.lower())
        quantity = _quantity(row.get("quantity"), "Quantity")
        unit_cost = _quantity(row.get("unit_cost"), "Unit cost")
        reorder = _quantity(row.get("reorder_level"), "Reorder level")
        items.append({
            "name": name,
            "unit": _text(row, "unit", required=False, max_len=20, label="Unit") or "pcs",
            "quantity": None if quantity is None else f"{quantity:.2f}",
            "unit_cost": None if unit_cost is None else f"{unit_cost:.2f}",
            "reorder_level": None if reorder is None else f"{reorder:.2f}",
        })
    return items


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None

