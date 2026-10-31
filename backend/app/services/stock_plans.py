"""Stock changes drafted by the assistant and confirmed by a person.

The assistant's propose_stock_changes tool calls `draft_changes`: it finds the items and projects named in
the request, works out each line's quantity before and after, and flags problems. Nothing is saved.
The app shows the draft; when the user confirms, `POST /organizations/:id/inventory/changes` calls
`apply_changes`, which checks every line again (never trusting the draft) and saves them all in one
transaction through the same code as the Stock page, so permissions, notifications and history match.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func

from ..errors import ApiError
from ..extensions import db
from ..models import InventoryItem, MovementKind, Project, ProjectStatus, Role
from .permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES

MAX_LINES = 50
KINDS = ("receive", "issue", "adjust", "create")
# Contributors receive and issue stock; adding items and adjusting counts is for managers (as on the Stock page).
MANAGER_KINDS = ("adjust", "create")
MAX_QUANTITY = Decimal("9999999999.99")
MAX_MONEY = Decimal("999999999999.99")


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


# ---------- finding items and projects by what the user called them ----------


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


def find_items(organization_id: int, query: Optional[str], limit: int = 25) -> list[InventoryItem]:
    q = InventoryItem.query.filter_by(organization_id=organization_id, archived=False)
    if query:
        like = f"%{query.strip().lower()}%"
        q = q.filter(
            func.lower(InventoryItem.name).like(like)
            | func.lower(func.coalesce(InventoryItem.sku, "")).like(like)
            | func.lower(func.coalesce(InventoryItem.location, "")).like(like)
        )
    return q.order_by(InventoryItem.name).limit(limit).all()


# ---------- the draft ----------


def draft_changes(organization_id: int, role: Role, changes: Any) -> dict:
    """Resolve and preview the lines; problems are reported per line instead of failing the whole draft."""
    if not isinstance(changes, list) or not changes:
        raise ValueError("List at least one stock change.")
    if len(changes) > MAX_LINES:
        raise ValueError(f"Draft at most {MAX_LINES} stock changes at a time.")

    items = InventoryItem.query.filter_by(organization_id=organization_id).all()
    projects = Project.query.filter(
        Project.organization_id == organization_id, Project.status != ProjectStatus.ARCHIVED
    ).all()
    on_hand: dict[int, Decimal] = {i.id: i.quantity_on_hand for i in items}
    lines = []
    for raw in changes:
        raw = raw if isinstance(raw, dict) else {}
        lines.append(_draft_line(raw, items, projects, on_hand, role))
    return {
        "lines": lines,
        "can_apply": any(not line["error"] and line["allowed"] for line in lines),
    }


def _draft_line(raw: dict, items: list, projects: list, on_hand: dict, role: Role) -> dict:
    kind = raw.get("kind") if raw.get("kind") in KINDS else None
    line: dict = {
        "kind": kind or "receive",
        "item_id": None,
        "name": _text(raw.get("item") or raw.get("name"), 200),
        "unit": _text(raw.get("unit"), 20),
        "quantity": None,
        "on_hand_before": None,
        "on_hand_after": None,
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
        return fail("Choose receive, issue, adjust or create.")
    if not line["name"]:
        return fail("Say which item.")
    qty = _num(raw.get("quantity"))

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
            return _draft_line({**raw, "kind": "create"}, items, projects, on_hand, role)
        return fail(f"No item called {line['name']}. Create it first.")
    line.update(item_id=item.id, name=item.name, unit=item.unit)
    if item.archived:
        return fail("This item is archived. Restore it to change its stock.")

    if qty is None or qty == 0 or (kind != "adjust" and qty < 0):
        return fail("Give a quantity greater than zero." if kind != "adjust" else "Give the change, like 5 or -3.")
    if abs(qty) > MAX_QUANTITY:
        return fail("That quantity is too large.")
    delta = qty if kind in ("receive", "adjust") else -qty
    line["quantity"] = _q(qty)

    if kind == "issue" and (raw.get("project") or raw.get("project_id")):
        if isinstance(raw.get("project_id"), int):
            project = next((p for p in projects if p.id == raw["project_id"]), None)
            pcands: list[str] = []
        else:
            project, pcands = _match(projects, str(raw.get("project")))
        if project is None:
            return fail(
                f"Several projects match: {', '.join(pcands)}. Say which one."
                if pcands
                else f"No active project called {raw.get('project') or raw.get('project_id')}."
            )
        line.update(project_id=project.id, project_name=project.name)
    if kind == "adjust" and not line["note"]:
        return fail("Say why the stock is being adjusted.")

    before = on_hand[item.id]
    after = before + delta
    line["on_hand_before"] = _q(before)
    line["on_hand_after"] = _q(after)
    if after < 0:
        return fail(f"Only {_q(before)} {item.unit} on hand.")
    on_hand[item.id] = after  # later lines on the same item start from here
    line["low_after"] = item.reorder_level is not None and after <= item.reorder_level
    return line


# ---------- applying a confirmed draft ----------


def apply_changes(organization_id: int, user_id: int, role: Role, changes: Any) -> list[InventoryItem]:
    """Save the confirmed lines in order, all or nothing. Raises ApiError with details.line on a bad line."""
    # Imported here: the API module imports this one.
    from ..api.inventory import _apply, _audit, _check_project

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
            raise bad("Choose receive, issue, adjust or create.", field="kind")
        if not allowed(kind, role):
            raise bad("You do not have permission to do this.", 403, "forbidden")
        note = _text(raw.get("note"), 500)
        qty = _num(raw.get("quantity"))

        if kind == "create":
            name = _text(raw.get("name"), 200)
            if not name:
                raise bad("Say which item.", field="name")
            if InventoryItem.query.filter(
                InventoryItem.organization_id == organization_id, func.lower(InventoryItem.name) == name.lower()
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
            _audit(user_id, item, "inventory.item_created", {"item": item.name, "source": "assistant"})
            if qty:
                _apply(item, user_id, MovementKind.COUNT, qty, note="Opening stock")
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
        if item.archived:
            raise bad("This item is archived. Restore it to change its stock.", 409, "item_archived")
        if qty is None or qty == 0 or (kind != "adjust" and qty < 0) or abs(qty) > MAX_QUANTITY:
            raise bad("Give a quantity greater than zero." if kind != "adjust" else "Give the change, like 5 or -3.",
                      field="quantity")
        project_id = None
        if kind == "issue":
            project_id = raw.get("project_id") if isinstance(raw.get("project_id"), int) else None
            try:
                _check_project(organization_id, project_id)
            except ApiError as e:
                raise bad(e.message, e.status, e.code, "project_id")
        if kind == "adjust" and not note:
            raise bad("Say why the stock is being adjusted.", field="note")
        delta = qty if kind in ("receive", "adjust") else -qty
        try:
            _apply(item, user_id, MovementKind(kind), delta, project_id=project_id, note=note)
        except ApiError as e:
            raise bad(e.message, e.status, e.code, "quantity")
        touched[item.id] = item
    return list(touched.values())
