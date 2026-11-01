"""Stock changes drafted by the assistant and confirmed by a person.

The assistant's propose_stock_changes tool calls `draft_changes`: it finds the inventories, items, warehouses
and projects named in the request, works out each line's quantities before and after, and flags problems.
Nothing is saved. The app shows the draft; when the user confirms, `POST /organizations/:id/inventory/changes`
calls `apply_changes`, which checks every line again (never trusting the draft) and saves them all in one
transaction through services.stock, so permissions, notifications and history match the Stock page.

Each line belongs to an inventory: General stock (the organization's own) or one project's. Kinds:
receive, issue, adjust and create (with an optional warehouse), transfer (between two places of the same
inventory), move (to another inventory) and delete (remove an item for good).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func

from ..errors import ApiError
from ..extensions import db
from ..models import (
    InventoryItem,
    InventoryStock,
    MovementKind,
    Project,
    ProjectStatus,
    Role,
    Warehouse,
)
from . import stock
from .permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES

MAX_LINES = 50
KINDS = ("receive", "issue", "adjust", "create", "transfer", "move", "delete")
# Contributors receive, issue and transfer stock; adding, adjusting, moving between inventories and deleting
# items is for managers (as on the Stock page).
MANAGER_KINDS = ("adjust", "create", "move", "delete")
MAX_QUANTITY = Decimal("9999999999.99")
MAX_MONEY = Decimal("999999999999.99")
GENERAL = "General stock"


def _q(v) -> Optional[str]:
    return None if v is None else f"{Decimal(v):.2f}"


def _num(value: Any) -> Optional[Decimal]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal("0.01")) if d.is_finite() else None


def _text(value: Any, max_len: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_len] or None


def allowed(kind: str, role: Role) -> bool:
    return role in (PROJECT_WRITE_ROLES if kind in MANAGER_KINDS else CONTRIBUTE_ROLES)


# ---------- finding things by what the user called them ----------


def _match(rows: list, name: str, *, label=lambda r: r.name, extra=lambda r: ()) -> tuple[Any, list[str]]:
    """The one row called `name` (exactly, ignoring case; else the only partial match), or candidates."""
    wanted = name.strip().lower()
    exact = [r for r in rows if label(r).lower() == wanted or wanted in [x.lower() for x in extra(r) if x]]
    if len(exact) == 1:
        return exact[0], []
    partial = exact or [r for r in rows if wanted in label(r).lower()]
    if len(partial) == 1:
        return partial[0], []
    return None, [label(r) for r in partial[:5]]


def is_general(name: Any) -> bool:
    return not name or (isinstance(name, str) and name.strip().lower() in ("general", "general stock", "stock général",
                                                                            "stock general", "المخزون العام"))


def find_items(organization_id: int, query: Optional[str], limit: int = 25, project_id: Any = "all") -> list[InventoryItem]:
    """project_id: "all", None (General stock) or a project's ID."""
    q = InventoryItem.query.filter_by(organization_id=organization_id, archived=False)
    if project_id != "all":
        q = q.filter(InventoryItem.project_id.is_(None) if project_id is None else InventoryItem.project_id == project_id)
    if query:
        like = f"%{query.strip().lower()}%"
        q = q.filter(
            func.lower(InventoryItem.name).like(like)
            | func.lower(func.coalesce(InventoryItem.sku, "")).like(like)
            | func.lower(func.coalesce(InventoryItem.location, "")).like(like)
        )
    return q.order_by(InventoryItem.name).limit(limit).all()


class _Context:
    """Everything a draft needs, loaded once, plus running quantities as lines are previewed."""

    def __init__(self, organization_id: int):
        self.organization_id = organization_id
        self.items = InventoryItem.query.filter_by(organization_id=organization_id).all()
        self.projects = Project.query.filter(
            Project.organization_id == organization_id, Project.status != ProjectStatus.ARCHIVED
        ).all()
        self.warehouses = Warehouse.query.filter_by(organization_id=organization_id).all()
        self.on_hand = {i.id: i.quantity_on_hand for i in self.items}
        self.place: dict[tuple[int, Optional[int]], Decimal] = {}
        rows = InventoryStock.query.filter(InventoryStock.item_id.in_([i.id for i in self.items])).all() if self.items else []
        allocated: dict[int, Decimal] = {}
        for r in rows:
            self.place[(r.item_id, r.warehouse_id)] = r.quantity
            allocated[r.item_id] = allocated.get(r.item_id, Decimal("0")) + r.quantity
        for i in self.items:
            self.place[(i.id, None)] = i.quantity_on_hand - allocated.get(i.id, Decimal("0"))
        self.deleted: set[int] = set()

    def inventory(self, name: Any) -> tuple[Optional[Project], Optional[str]]:
        """(project or None for General stock, error)."""
        if is_general(name):
            return None, None
        project, candidates = _match(self.projects, str(name))
        if project is None:
            if candidates:
                return None, f"Several projects match: {', '.join(candidates)}. Say which one."
            return None, f"No active project called {name}."
        return project, None

    def items_in(self, project: Optional[Project]) -> list[InventoryItem]:
        pid = project.id if project else None
        return [i for i in self.items if i.project_id == pid and i.id not in self.deleted]

    def warehouse(self, project: Optional[Project], name: Any) -> tuple[Optional[Warehouse], Optional[str]]:
        if not name:
            return None, None
        pid = project.id if project else None
        rows = [w for w in self.warehouses if w.project_id == pid]
        w, candidates = _match(rows, str(name))
        if w is None:
            if candidates:
                return None, f"Several warehouses match: {', '.join(candidates)}. Say which one."
            return None, f"No warehouse called {name} in {project.name if project else GENERAL}."
        return w, None


# ---------- the draft ----------


def draft_changes(organization_id: int, role: Role, changes: Any) -> dict:
    """Resolve and preview the lines; problems are reported per line instead of failing the whole draft."""
    if not isinstance(changes, list) or not changes:
        raise ValueError("List at least one stock change.")
    if len(changes) > MAX_LINES:
        raise ValueError(f"Draft at most {MAX_LINES} stock changes at a time.")
    ctx = _Context(organization_id)
    lines = [_draft_line(raw if isinstance(raw, dict) else {}, ctx, role) for raw in changes]
    return {
        "lines": lines,
        "can_apply": any(not line["error"] and line["allowed"] for line in lines),
    }


def _draft_line(raw: dict, ctx: _Context, role: Role) -> dict:
    kind = raw.get("kind") if raw.get("kind") in KINDS else None
    line: dict = {
        "kind": kind or "receive",
        "inventory_project_id": None,
        "inventory_name": GENERAL,
        "item_id": None,
        "name": _text(raw.get("item") or raw.get("name"), 200),
        "unit": _text(raw.get("unit"), 20),
        "quantity": None,
        "on_hand_before": None,
        "on_hand_after": None,
        "warehouse_id": None,
        "warehouse_name": None,
        "to_warehouse_id": None,
        "to_warehouse_name": None,
        "to_project_id": None,
        "to_inventory_name": None,
        "project_id": None,
        "project_name": None,
        "note": _text(raw.get("note") or raw.get("reason"), 500),
        "sku": _text(raw.get("sku"), 60),
        "location": _text(raw.get("location"), 120),
        "unit_cost": _q(_num(raw.get("unit_cost"))),
        "reorder_level": _q(_num(raw.get("reorder_level"))),
        "low_after": False,
        "allowed": allowed(kind or "receive", role),
        "error": None,
    }

    def fail(message: str) -> dict:
        line["error"] = message
        return line

    if kind is None:
        return fail("Choose receive, issue, adjust, create, transfer, move or delete.")
    inventory, problem = ctx.inventory(raw.get("inventory"))
    if problem:
        return fail(problem)
    line["inventory_project_id"] = inventory.id if inventory else None
    line["inventory_name"] = inventory.name if inventory else GENERAL
    if not line["name"]:
        return fail("Say which item.")
    qty = _num(raw.get("quantity"))
    warehouse, problem = ctx.warehouse(inventory, raw.get("warehouse") or raw.get("from_warehouse"))
    if problem:
        return fail(problem)
    if warehouse:
        line.update(warehouse_id=warehouse.id, warehouse_name=warehouse.name)
    items = ctx.items_in(inventory)

    if kind == "create":
        if line["name"] == line["name"].lower():
            line["name"] = line["name"][:1].upper() + line["name"][1:]  # "whiteboard markers" -> "Whiteboard markers"
        existing, _ = _match(items, line["name"], extra=lambda r: (r.sku,))
        if existing is not None and existing.name.lower() == line["name"].lower():
            return fail(f"An item called {existing.name} already exists. Receive stock into it instead.")
        line["unit"] = line["unit"] or "pcs"
        opening = qty if qty is not None else Decimal("0")
        if opening < 0 or opening > MAX_QUANTITY:
            return fail("The opening quantity must be zero or more.")
        line["quantity"] = _q(opening)
        line["on_hand_before"] = "0.00"
        line["on_hand_after"] = _q(opening)
        reorder = _num(raw.get("reorder_level"))
        line["low_after"] = reorder is not None and opening <= reorder
        return line

    item, candidates = _match(items, line["name"], extra=lambda r: (r.sku,))
    if item is None:
        if candidates:
            return fail(f"Several items match: {', '.join(candidates)}. Say which one.")
        if kind == "receive" and qty is not None and qty > 0:
            # Stock arrived for something not tracked yet: offer to add it, with what arrived as opening stock.
            return _draft_line({**raw, "kind": "create"}, ctx, role)
        return fail(f"No item called {line['name']} in {line['inventory_name']}.")
    line.update(item_id=item.id, name=item.name, unit=item.unit)
    if item.archived:
        return fail("This item is archived. Restore it to change its stock.")
    before = ctx.on_hand[item.id]
    line["on_hand_before"] = _q(before)

    if kind == "delete":
        line["on_hand_after"] = "0.00"
        line["quantity"] = _q(before)
        ctx.deleted.add(item.id)
        return line

    if qty is None or qty == 0 or (kind != "adjust" and qty < 0):
        return fail("Give a quantity greater than zero." if kind != "adjust" else "Give the change, like 5 or -3.")
    if abs(qty) > MAX_QUANTITY:
        return fail("That quantity is too large.")
    line["quantity"] = _q(qty)
    here = (item.id, warehouse.id if warehouse else None)
    where = warehouse.name if warehouse else None

    def take(amount: Decimal) -> Optional[str]:
        available = ctx.place.get(here, Decimal("0"))
        if available < amount:
            return (f"Only {_q(available)} {item.unit} in {where}." if where
                    else f"Only {_q(available)} {item.unit} on hand." if available == ctx.on_hand[item.id]
                    else f"Only {_q(available)} {item.unit} aren't in a warehouse. Choose the warehouse to take it from.")
        ctx.place[here] = available - amount
        return None

    if kind == "transfer":
        target, problem = ctx.warehouse(inventory, raw.get("to_warehouse"))
        if problem:
            return fail(problem)
        if (target.id if target else None) == (warehouse.id if warehouse else None):
            return fail("Choose two different places.")
        line.update(to_warehouse_id=target.id if target else None, to_warehouse_name=target.name if target else None)
        problem = take(qty)
        if problem:
            return fail(problem)
        there = (item.id, target.id if target else None)
        ctx.place[there] = ctx.place.get(there, Decimal("0")) + qty
        line["on_hand_after"] = _q(before)  # the total doesn't change
        return line

    if kind == "move":
        target_project, problem = ctx.inventory(raw.get("to_inventory") or raw.get("to_project"))
        if problem:
            return fail(problem)
        if (target_project.id if target_project else None) == (inventory.id if inventory else None):
            return fail("Choose a different inventory.")
        line.update(to_project_id=target_project.id if target_project else None,
                    to_inventory_name=target_project.name if target_project else GENERAL)
        target_warehouse, problem = ctx.warehouse(target_project, raw.get("to_warehouse"))
        if problem:
            return fail(problem)
        if target_warehouse:
            line.update(to_warehouse_id=target_warehouse.id, to_warehouse_name=target_warehouse.name)
        problem = take(qty)
        if problem:
            return fail(problem)
        ctx.on_hand[item.id] = before - qty
        line["on_hand_after"] = _q(before - qty)
        return line

    delta = qty if kind in ("receive", "adjust") else -qty
    if kind == "issue" and inventory is None and (raw.get("project") or raw.get("project_id")):
        project, problem = ctx.inventory(raw.get("project"))
        if problem:
            return fail(problem)
        if project is not None:
            line.update(project_id=project.id, project_name=project.name)
    if kind == "adjust" and not line["note"]:
        return fail("Say why the stock is being adjusted.")
    if delta < 0:
        problem = take(-delta)
        if problem:
            return fail(problem)
    else:
        ctx.place[here] = ctx.place.get(here, Decimal("0")) + delta
    after = before + delta
    ctx.on_hand[item.id] = after  # later lines on the same item start from here
    line["on_hand_after"] = _q(after)
    line["low_after"] = item.reorder_level is not None and after <= item.reorder_level
    return line


# ---------- applying a confirmed draft ----------


def apply_changes(organization_id: int, user_id: int, role: Role, changes: Any) -> list[InventoryItem]:
    """Save the confirmed lines in order, all or nothing. Raises ApiError with details.line on a bad line."""
    if not isinstance(changes, list) or not changes:
        raise ApiError("validation_error", "List at least one stock change.", 400)
    if len(changes) > MAX_LINES:
        raise ApiError("validation_error", f"Apply at most {MAX_LINES} stock changes at a time.", 400)

    touched: dict[int, InventoryItem] = {}
    for index, raw in enumerate(changes):
        def bad(message: str, status: int = 400, code: str = "validation_error", field: str | None = None):
            details = {"line": index}
            if field:
                details["field"] = field
            return ApiError(code, message, status, details)

        raw = raw if isinstance(raw, dict) else {}
        kind = raw.get("kind")
        if kind not in KINDS:
            raise bad("Choose receive, issue, adjust, create, transfer, move or delete.", field="kind")
        if not allowed(kind, role):
            raise bad("You do not have permission to do this.", 403, "forbidden")
        note = _text(raw.get("note"), 500)
        qty = _num(raw.get("quantity"))
        try:
            if kind == "create":
                item = _create(organization_id, user_id, raw, qty, bad)
                touched[item.id] = item
                continue

            item_id = raw.get("item_id")
            item = (
                db.session.query(InventoryItem).filter_by(id=item_id).with_for_update().first()
                if isinstance(item_id, int) and not isinstance(item_id, bool)
                else None
            )
            if item is None or item.organization_id != organization_id:
                raise bad("Item not found.", 404, "not_found", "item_id")
            if kind == "delete":
                touched.pop(item.id, None)
                stock.delete_item(item, user_id)
                continue
            stock.check_item_editable(item)
            if qty is None or qty == 0 or (kind != "adjust" and qty < 0) or abs(qty) > MAX_QUANTITY:
                raise bad("Give a quantity greater than zero." if kind != "adjust" else "Give the change, like 5 or -3.",
                          field="quantity")
            warehouse = stock.warehouse_in_inventory(item, raw.get("warehouse_id"))
            if kind == "transfer":
                target = stock.warehouse_in_inventory(item, raw.get("to_warehouse_id"), field="to_warehouse_id")
                stock.transfer(item, user_id, qty, warehouse, target, note)
            elif kind == "move":
                target_project = stock.project_for_inventory(organization_id, raw.get("to_project_id"), field="to_project_id")
                target = stock.move_to_inventory(item, user_id, qty, target_project, source=warehouse,
                                                 target_warehouse_id=raw.get("to_warehouse_id"), note=note)
                touched[target.id] = target
            else:
                project_id = None
                if kind == "issue" and item.project_id is None:
                    project_id = raw.get("project_id") if isinstance(raw.get("project_id"), int) else None
                    stock.check_project(organization_id, project_id)
                if kind == "adjust" and not note:
                    raise bad("Say why the stock is being adjusted.", field="note")
                delta = qty if kind in ("receive", "adjust") else -qty
                stock.apply(item, user_id, MovementKind(kind), delta, project_id=project_id, note=note, warehouse=warehouse)
            touched[item.id] = item
        except ApiError as e:
            if e.details and "line" in e.details:
                raise
            field = (e.details or {}).get("field") if isinstance(e.details, dict) else None
            raise bad(e.message, e.status, e.code, field)
    return list(touched.values())


def _create(organization_id: int, user_id: int, raw: dict, qty, bad) -> InventoryItem:
    name = _text(raw.get("name"), 200)
    if not name:
        raise bad("Say which item.", field="name")
    project = stock.project_for_inventory(organization_id, raw.get("inventory_project_id"), field="inventory_project_id")
    pid = project.id if project else None
    if InventoryItem.query.filter(
        InventoryItem.organization_id == organization_id,
        InventoryItem.project_id.is_(None) if pid is None else InventoryItem.project_id == pid,
        func.lower(InventoryItem.name) == name.lower(),
    ).first():
        raise bad(f"An item called {name} already exists. Receive stock into it instead.", 409, "duplicate")
    unit_cost, reorder = _num(raw.get("unit_cost")), _num(raw.get("reorder_level"))
    if unit_cost is not None and not Decimal("0") <= unit_cost <= MAX_MONEY:
        raise bad("Unit cost can't be negative.", field="unit_cost")
    if reorder is not None and not Decimal("0") <= reorder <= MAX_QUANTITY:
        raise bad("Reorder level can't be negative.", field="reorder_level")
    if qty is not None and not Decimal("0") <= qty <= MAX_QUANTITY:
        raise bad("The opening quantity must be zero or more.", field="quantity")
    item = InventoryItem(
        organization_id=organization_id,
        project_id=pid,
        name=name,
        unit=_text(raw.get("unit"), 20) or "pcs",
        sku=_text(raw.get("sku"), 60),
        location=_text(raw.get("location"), 120),
        unit_cost=unit_cost,
        reorder_level=reorder,
        quantity_on_hand=Decimal("0"),
        archived=False,
    )
    db.session.add(item)
    db.session.flush()
    stock.audit(user_id, item, "inventory.item_created", {"item": item.name, "source": "assistant"})
    if qty:
        warehouse = stock.warehouse_in_inventory(item, raw.get("warehouse_id"))
        stock.apply(item, user_id, MovementKind.COUNT, qty, note="Opening stock", warehouse=warehouse)
    return item
