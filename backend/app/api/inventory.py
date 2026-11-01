"""Inventory: stock items, warehouses, movements (receive / issue / adjust / transfer / move) and stock counts.

Each project has its own inventory, and the organization has General stock (items and warehouses without a
project). Lists take ?scope=general (default), ?scope=<project id> or ?scope=all. The rules live in
services.stock; this module checks access and input. Values use the organization's default currency.
"""
from __future__ import annotations

from decimal import Decimal

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from ..errors import ApiError
from ..extensions import db
from ..models import (
    InventoryItem,
    InventoryMovement,
    InventoryStock,
    MovementKind,
    Organization,
    Project,
    User,
    Warehouse,
)
from ..services import metrics
from ..services import projects as svc
from ..services import stock
from ..services.permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES, get_membership, require_role
from ..services.stock import item_to_dict, q2 as _q
from ..services.tokens import aware
from . import api_bp
from .auth import current_user
from .projects import _like
from .validation import (
    get_json_body,
    optional_str,
    parse_money,
    parse_optional_id,
    parse_quantity,
    parse_signed_quantity,
    require_str,
)

MAX_COUNT_LINES = 500
HISTORY_PAGE = 50
# Contributors receive, issue, transfer and count stock; adjustments and managing items, warehouses and moves
# between inventories are for managers.
ADJUST_ROLES = PROJECT_WRITE_ROLES

# Kept for the assistant's confirmed drafts (services.stock_plans).
_apply = stock.apply
_audit = stock.audit
_check_project = stock.check_project


def movement_to_dict(m: InventoryMovement, names: dict, projects: dict, warehouses: dict) -> dict:
    return {
        "id": m.id,
        "item_id": m.item_id,
        "kind": m.kind.value,
        "quantity_delta": _q(m.quantity_delta),
        "quantity_after": _q(m.quantity_after),
        "project_id": m.project_id,
        "project_name": projects.get(m.project_id),
        "warehouse": warehouses.get(m.warehouse_id),
        "to_warehouse": warehouses.get(m.to_warehouse_id),
        "note": m.note,
        "created_by": names.get(m.created_by),
        "created_at": aware(m.created_at).isoformat(),
    }


def _org(org_id: int, user_id: int):
    membership = get_membership(org_id, user_id)
    return membership, db.session.get(Organization, org_id)


def _item_for_user(item_id: int, user_id: int, *, lock: bool = False):
    query = db.session.query(InventoryItem).filter_by(id=item_id)
    if lock:
        query = query.with_for_update()  # serialise concurrent stock changes (no-op on SQLite)
    item = query.first()
    if item is None:
        raise ApiError("not_found", "Item not found.", 404)
    try:
        membership, org = _org(item.organization_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Item not found.", 404)
    return item, membership, org


def _scope(org_id: int):
    """?scope=general (default) | all | <project id>: (filter for project_id, project or None)."""
    raw = (request.args.get("scope") or "general").strip()
    if raw == "general":
        return "general", None
    if raw == "all":
        return "all", None
    try:
        project_id = int(raw)
    except ValueError:
        raise ApiError("validation_error", "Choose General stock or a project.", 400, {"field": "scope"})
    p = db.session.get(Project, project_id)
    if p is None or p.organization_id != org_id:
        raise ApiError("not_found", "Project not found.", 404)
    return "project", p


def _in_scope(query, model, kind: str, project):
    if kind == "general":
        return query.filter(model.project_id.is_(None))
    if kind == "project":
        return query.filter(model.project_id == project.id)
    return query


def _summary(items: list[InventoryItem]) -> dict:
    active = [i for i in items if not i.archived]
    total = Decimal("0")
    unpriced = 0
    for i in active:
        v = metrics.stock_value(i.quantity_on_hand, i.unit_cost)
        if v is None:
            unpriced += 1
        else:
            total += v
    return {
        "item_count": len(active),
        "low_stock_count": sum(1 for i in active if metrics.is_low_stock(i.quantity_on_hand, i.reorder_level)),
        "stock_value": _q(metrics.q(total)),
        "unpriced_item_count": unpriced,
    }


def _warehouse_list(org_id: int, kind: str, project) -> list[dict]:
    rows = _in_scope(Warehouse.query.filter_by(organization_id=org_id), Warehouse, kind, project).order_by(Warehouse.name).all()
    contents = stock.warehouse_contents([w.id for w in rows])
    return [stock.warehouse_to_dict(w, contents.get(w.id)) for w in rows]


# ---------- items ----------


@api_bp.get("/organizations/<int:org_id>/inventory")
@jwt_required()
def list_inventory(org_id: int):
    user = current_user()
    _, org = _org(org_id, user.id)
    kind, project = _scope(org_id)
    base = _in_scope(InventoryItem.query.filter_by(organization_id=org_id), InventoryItem, kind, project)
    query = base
    if request.args.get("include_archived") != "true":
        query = query.filter(InventoryItem.archived.is_(False))
    q = (request.args.get("q") or "").strip()
    if len(q) > 100:
        raise ApiError("validation_error", "Search text is too long.", 400, {"field": "q"})
    if q:
        pattern = _like(q)
        query = query.filter(
            or_(
                InventoryItem.name.ilike(pattern, escape="\\"),
                InventoryItem.sku.ilike(pattern, escape="\\"),
                InventoryItem.location.ilike(pattern, escape="\\"),
            )
        )
    items = query.order_by(InventoryItem.name, InventoryItem.id).all()
    per_item = stock.stock_by_item([i.id for i in items])
    rows = [item_to_dict(i, org.default_currency, per_item.get(i.id, [])) for i in items]
    if request.args.get("low_stock") == "true":
        rows = [r for r in rows if r["low_stock"]]
    return jsonify(
        items=rows,
        summary={**_summary(base.all()), "currency": org.default_currency},
        warehouses=_warehouse_list(org_id, kind, project) if kind != "all" else [],
        scope={"project_id": project.id if project else None, "project_name": project.name if project else None},
    )


def _item_fields(data: dict, *, creating: bool) -> dict:
    fields: dict = {}
    if creating or "name" in data:
        fields["name"] = require_str(data, "name", max_len=200)
    if creating or "unit" in data:
        fields["unit"] = (optional_str(data, "unit", max_len=20) or "pcs") if creating else require_str(data, "unit", max_len=20)
    for key, max_len in (("sku", 60), ("location", 120), ("description", 5000)):
        if creating or key in data:
            fields[key] = optional_str(data, key, max_len=max_len)
    if creating or "unit_cost" in data:
        fields["unit_cost"] = parse_money(data, "unit_cost", required=False)
    if creating or "reorder_level" in data:
        fields["reorder_level"] = parse_quantity(data, "reorder_level", required=False)
    return fields


def create_item_in(org_id: int, user_id: int, data: dict, project) -> InventoryItem:
    """Shared by the Stock page and project creation (opening inventory)."""
    item = InventoryItem(
        organization_id=org_id,
        project_id=project.id if project else None,
        quantity_on_hand=Decimal("0"),
        archived=False,
        **_item_fields(data, creating=True),
    )
    db.session.add(item)
    db.session.flush()
    stock.audit(user_id, item, "inventory.item_created", {"item": item.name})
    opening = parse_quantity(data, "quantity", required=False)
    if opening:
        warehouse = stock.warehouse_in_inventory(item, parse_optional_id(data, "warehouse_id"))
        stock.apply(item, user_id, MovementKind.COUNT, opening, note="Opening stock", warehouse=warehouse)
    return item


@api_bp.post("/organizations/<int:org_id>/inventory")
@jwt_required()
def create_item(org_id: int):
    """{name, unit?, ..., quantity?, warehouse_id?, project_id?}: in General stock, or a project's inventory."""
    user = current_user()
    membership, org = _org(org_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    data = get_json_body()
    project = stock.project_for_inventory(org_id, parse_optional_id(data, "project_id"))
    item = create_item_in(org_id, user.id, data, project)
    db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency)), 201


@api_bp.patch("/inventory/<int:item_id>")
@jwt_required()
def update_item(item_id: int):
    user = current_user()
    item, membership, org = _item_for_user(item_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    data = get_json_body()
    if "quantity_on_hand" in data:
        raise ApiError(
            "validation_error", "Change quantities with Receive, Issue, Adjust or a stock count.", 400,
            {"field": "quantity_on_hand"},
        )
    fields = _item_fields(data, creating=False)
    if "archived" in data:
        if not isinstance(data["archived"], bool):
            raise ApiError("validation_error", "Archived must be true or false.", 400, {"field": "archived"})
        fields["archived"] = data["archived"]
    meta = {}
    for key, new in fields.items():
        old = getattr(item, key)
        if old == new:
            continue
        setattr(item, key, new)
        meta[key] = [_q(old), _q(new)] if key in ("unit_cost", "reorder_level") else (
            [old, new] if key in ("archived", "unit") else "changed"
        )
    if meta:
        stock.audit(user.id, item, "inventory.item_updated", meta)
        db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency))


@api_bp.delete("/inventory/<int:item_id>")
@jwt_required()
def delete_item(item_id: int):
    """Remove an item for good, with its stock and history (managers). Archiving keeps them."""
    user = current_user()
    item, membership, _ = _item_for_user(item_id, user.id, lock=True)
    require_role(membership, *PROJECT_WRITE_ROLES)
    stock.delete_item(item, user.id)
    db.session.commit()
    return jsonify(deleted=True)


# ---------- movements ----------


@api_bp.post("/inventory/<int:item_id>/movements")
@jwt_required()
def record_movement(item_id: int):
    """{kind: receive|issue|adjust, quantity, warehouse_id?, project_id?, note?}. Adjust takes a signed quantity."""
    user = current_user()
    item, membership, org = _item_for_user(item_id, user.id, lock=True)
    data = get_json_body()
    kind = data.get("kind")
    if kind not in ("receive", "issue", "adjust"):
        raise ApiError("validation_error", "Kind must be receive, issue or adjust.", 400, {"field": "kind"})
    require_role(membership, *(ADJUST_ROLES if kind == "adjust" else CONTRIBUTE_ROLES))
    stock.check_item_editable(item)

    note = optional_str(data, "note", max_len=500)
    warehouse = stock.warehouse_in_inventory(item, parse_optional_id(data, "warehouse_id"))
    project_id = None
    if kind == "adjust":
        delta = parse_signed_quantity(data, "quantity")
        if not note:
            raise ApiError("validation_error", "Say why the stock is being adjusted.", 400, {"field": "note"})
    else:
        qty = parse_quantity(data, "quantity", positive=True)
        delta = qty if kind == "receive" else -qty
        if kind == "issue" and item.project_id is None:
            project_id = parse_optional_id(data, "project_id")
            stock.check_project(item.organization_id, project_id)

    movement = stock.apply(item, user.id, MovementKind(kind), delta, project_id=project_id, note=note, warehouse=warehouse)
    db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency), movement=_movement_dict(movement)), 201


@api_bp.post("/inventory/<int:item_id>/transfers")
@jwt_required()
def transfer_stock(item_id: int):
    """{quantity, from_warehouse_id | null, to_warehouse_id | null, note?}: between places of this inventory."""
    user = current_user()
    item, membership, org = _item_for_user(item_id, user.id, lock=True)
    require_role(membership, *CONTRIBUTE_ROLES)
    stock.check_item_editable(item)
    data = get_json_body()
    qty = parse_quantity(data, "quantity", positive=True)
    source = stock.warehouse_in_inventory(item, parse_optional_id(data, "from_warehouse_id"), field="from_warehouse_id")
    target = stock.warehouse_in_inventory(item, parse_optional_id(data, "to_warehouse_id"), field="to_warehouse_id")
    movement = stock.transfer(item, user.id, qty, source, target, optional_str(data, "note", max_len=500))
    db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency), movement=_movement_dict(movement)), 201


@api_bp.post("/inventory/<int:item_id>/move")
@jwt_required()
def move_stock(item_id: int):
    """{to_project_id | null, quantity, from_warehouse_id?, to_warehouse_id?, note?}: to another inventory.

    General stock -> a project, a project -> General stock, or between projects. Managers only.
    """
    user = current_user()
    item, membership, org = _item_for_user(item_id, user.id, lock=True)
    require_role(membership, *PROJECT_WRITE_ROLES)
    stock.check_item_editable(item)
    data = get_json_body()
    if "to_project_id" not in data:
        raise ApiError("validation_error", "Choose where to move it.", 400, {"field": "to_project_id"})
    target_project = stock.project_for_inventory(item.organization_id, parse_optional_id(data, "to_project_id"), field="to_project_id")
    qty = parse_quantity(data, "quantity", positive=True)
    source = stock.warehouse_in_inventory(item, parse_optional_id(data, "from_warehouse_id"), field="from_warehouse_id")
    target = stock.move_to_inventory(
        item, user.id, qty, target_project, source=source,
        target_warehouse_id=parse_optional_id(data, "to_warehouse_id"), note=optional_str(data, "note", max_len=500),
    )
    db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency), target=item_to_dict(target, org.default_currency)), 201


def _movement_dict(m: InventoryMovement) -> dict:
    user = db.session.get(User, m.created_by)
    names = {user.id: f"{user.first_name} {user.last_name}"} if user else {}
    projects = {m.project_id: db.session.get(Project, m.project_id).name} if m.project_id else {}
    wids = {w for w in (m.warehouse_id, m.to_warehouse_id) if w}
    warehouses = {w.id: w.name for w in Warehouse.query.filter(Warehouse.id.in_(wids))} if wids else {}
    return movement_to_dict(m, names, projects, warehouses)


def _history(query, limit: int, offset: int):
    total = query.count()
    rows = query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc()).limit(limit).offset(offset).all()
    user_ids = {m.created_by for m in rows}
    project_ids = {m.project_id for m in rows if m.project_id}
    wids = {w for m in rows for w in (m.warehouse_id, m.to_warehouse_id) if w}
    names = {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(user_ids))} if user_ids else {}
    projects = {p.id: p.name for p in Project.query.filter(Project.id.in_(project_ids))} if project_ids else {}
    warehouses = {w.id: w.name for w in Warehouse.query.filter(Warehouse.id.in_(wids))} if wids else {}
    return total, [movement_to_dict(m, names, projects, warehouses) for m in rows]


def _page() -> tuple[int, int]:
    try:
        return min(max(int(request.args.get("limit", HISTORY_PAGE)), 1), 200), max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError("validation_error", "limit and offset must be whole numbers.", 400)


@api_bp.get("/inventory/<int:item_id>/movements")
@jwt_required()
def item_movements(item_id: int):
    user = current_user()
    item, _, _ = _item_for_user(item_id, user.id)
    limit, offset = _page()
    total, rows = _history(InventoryMovement.query.filter_by(item_id=item.id), limit, offset)
    return jsonify(movements=rows, total=total)


@api_bp.get("/projects/<int:project_id>/materials")
@jwt_required()
def project_materials(project_id: int):
    """Stock used on a project (issued from General stock or from its own inventory), valued at current cost."""
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    org = db.session.get(Organization, project.organization_id)
    movements = InventoryMovement.query.filter_by(project_id=project.id, kind=MovementKind.ISSUE).all()
    items = {i.id: i for i in InventoryItem.query.filter(InventoryItem.id.in_({m.item_id for m in movements}))} if movements else {}
    per_item: dict[int, Decimal] = {}
    for m in movements:
        per_item[m.item_id] = per_item.get(m.item_id, Decimal("0")) - m.quantity_delta  # issues are negative
    rows = []
    total = Decimal("0")
    for item_id, qty in sorted(per_item.items(), key=lambda kv: items[kv[0]].name):
        value = metrics.stock_value(qty, items[item_id].unit_cost)
        total += value or 0
        rows.append({"item_id": item_id, "name": items[item_id].name, "unit": items[item_id].unit,
                     "quantity": _q(qty), "value": _q(value)})
    return jsonify(materials=rows, total_value=_q(metrics.q(total)), currency=org.default_currency)


@api_bp.get("/projects/<int:project_id>/inventory-summary")
@jwt_required()
def project_inventory_summary(project_id: int):
    """The project's own inventory at a glance, for its page."""
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    org = db.session.get(Organization, project.organization_id)
    items = InventoryItem.query.filter_by(project_id=project.id).all()
    warehouse_count = Warehouse.query.filter_by(project_id=project.id).count()
    return jsonify(summary={**_summary(items), "currency": org.default_currency, "warehouse_count": warehouse_count})


# ---------- stock counts ----------


@api_bp.post("/organizations/<int:org_id>/inventory/counts")
@jwt_required()
def record_count(org_id: int):
    """{counts: [{item_id, counted, warehouse_id?}], note?}. Sets what's at each place to what was counted.

    With a warehouse, the count is for that warehouse; without one, for stock that isn't in a warehouse.
    """
    user = current_user()
    membership, org = _org(org_id, user.id)
    require_role(membership, *CONTRIBUTE_ROLES)
    data = get_json_body()
    lines = data.get("counts")
    if not isinstance(lines, list) or not lines:
        raise ApiError("validation_error", "Enter at least one counted quantity.", 400, {"field": "counts"})
    if len(lines) > MAX_COUNT_LINES:
        raise ApiError("validation_error", f"Count at most {MAX_COUNT_LINES} items at a time.", 400, {"field": "counts"})
    note = optional_str(data, "note", max_len=500) or "Stock count"

    parsed: list[tuple[int, int | None, Decimal]] = []
    seen: set[tuple[int, int | None]] = set()
    for line in lines:
        if not isinstance(line, dict):
            raise ApiError("validation_error", "Each count needs an item and a quantity.", 400, {"field": "counts"})
        item_id = parse_optional_id(line, "item_id")
        warehouse_id = parse_optional_id(line, "warehouse_id")
        if item_id is None or (item_id, warehouse_id) in seen:
            raise ApiError("validation_error", "Each item can be counted once.", 400, {"field": "counts"})
        seen.add((item_id, warehouse_id))
        parsed.append((item_id, warehouse_id, parse_quantity(line, "counted")))

    ids = {i for i, _ in seen}
    items = {
        i.id: i
        for i in db.session.query(InventoryItem)
        .filter(InventoryItem.id.in_(ids), InventoryItem.organization_id == org_id)
        .with_for_update()
    }
    if len(items) != len(ids):
        raise ApiError("validation_error", "Some items aren't in this organization.", 400, {"field": "counts"})
    if any(items[i].archived for i in ids):
        raise ApiError("item_archived", "Archived items can't be counted.", 409)

    results = []
    value_change = Decimal("0")
    for item_id, warehouse_id, counted in parsed:
        item = items[item_id]
        warehouse = stock.warehouse_in_inventory(item, warehouse_id)
        expected = stock.place_quantity(item, warehouse)
        delta = counted - expected
        if delta != 0:
            stock.apply(item, user.id, MovementKind.COUNT, delta, note=note, warehouse=warehouse)
            value_change += metrics.stock_value(delta, item.unit_cost) or 0
        results.append({"item_id": item_id, "name": item.name, "unit": item.unit, "expected": _q(expected),
                        "counted": _q(counted), "difference": _q(delta),
                        "warehouse": warehouse.name if warehouse else None})
    db.session.commit()
    return jsonify(
        results=results,
        changed_count=sum(1 for r in results if Decimal(r["difference"]) != 0),
        value_change=_q(metrics.q(value_change)),
        currency=org.default_currency,
    )


# ---------- warehouses ----------


def _warehouse_fields(data: dict, *, creating: bool) -> dict:
    fields: dict = {}
    if creating or "name" in data:
        fields["name"] = require_str(data, "name", max_len=120)
    for key, max_len in (("address", 300), ("notes", 500)):
        if creating or key in data:
            fields[key] = optional_str(data, key, max_len=max_len)
    if creating or "lat" in data or "lng" in data:
        lat, lng = data.get("lat"), data.get("lng")
        if (lat is None) != (lng is None):
            raise ApiError("validation_error", "Give both coordinates, or neither.", 400, {"field": "lat"})
        if lat is not None:
            if isinstance(lat, bool) or isinstance(lng, bool) or not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
                raise ApiError("validation_error", "Coordinates must be numbers.", 400, {"field": "lat"})
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ApiError("validation_error", "Coordinates are out of range.", 400, {"field": "lat"})
        fields["lat"], fields["lng"] = (float(lat), float(lng)) if lat is not None else (None, None)
    return fields


def _warehouse_for_user(warehouse_id: int, user_id: int):
    w = db.session.get(Warehouse, warehouse_id)
    if w is None:
        raise ApiError("not_found", "Warehouse not found.", 404)
    try:
        membership, org = _org(w.organization_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Warehouse not found.", 404)
    return w, membership, org


def _warehouse_audit(user_id: int, w: Warehouse, action: str, meta: dict) -> None:
    from ..services.audit import log_action

    if w.project_id:
        meta = {**meta, "project_id": w.project_id}
    log_action(organization_id=w.organization_id, actor_id=user_id, action=action, entity_type="warehouse",
               entity_id=w.id, meta=meta)


@api_bp.get("/organizations/<int:org_id>/warehouses")
@jwt_required()
def list_warehouses(org_id: int):
    user = current_user()
    _org(org_id, user.id)
    kind, project = _scope(org_id)
    return jsonify(warehouses=_warehouse_list(org_id, kind, project))


@api_bp.post("/organizations/<int:org_id>/warehouses")
@jwt_required()
def create_warehouse(org_id: int):
    """{name, address?, lat?, lng?, notes?, project_id?}: for General stock, or a project's inventory."""
    user = current_user()
    membership, _ = _org(org_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    data = get_json_body()
    project = stock.project_for_inventory(org_id, parse_optional_id(data, "project_id"))
    w = Warehouse(organization_id=org_id, project_id=project.id if project else None, **_warehouse_fields(data, creating=True))
    db.session.add(w)
    db.session.flush()
    _warehouse_audit(user.id, w, "warehouse.created", {"warehouse": w.name})
    db.session.commit()
    return jsonify(warehouse=stock.warehouse_to_dict(w)), 201


@api_bp.patch("/warehouses/<int:warehouse_id>")
@jwt_required()
def update_warehouse(warehouse_id: int):
    user = current_user()
    w, membership, _ = _warehouse_for_user(warehouse_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    changed = []
    for key, value in _warehouse_fields(get_json_body(), creating=False).items():
        if getattr(w, key) != value:
            setattr(w, key, value)
            changed.append(key)
    if changed:
        _warehouse_audit(user.id, w, "warehouse.updated", {"warehouse": w.name, "fields": changed})
        db.session.commit()
    return jsonify(warehouse=stock.warehouse_to_dict(w, stock.warehouse_contents([w.id]).get(w.id)))


@api_bp.delete("/warehouses/<int:warehouse_id>")
@jwt_required()
def delete_warehouse(warehouse_id: int):
    """Only an empty warehouse can go; its history stays (movements just lose the warehouse name)."""
    user = current_user()
    w, membership, _ = _warehouse_for_user(warehouse_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    if InventoryStock.query.filter(InventoryStock.warehouse_id == w.id, InventoryStock.quantity != 0).first():
        raise ApiError("warehouse_not_empty", "Move the stock out of this warehouse first.", 409)
    InventoryStock.query.filter_by(warehouse_id=w.id).delete(synchronize_session=False)
    InventoryMovement.query.filter_by(warehouse_id=w.id).update({InventoryMovement.warehouse_id: None}, synchronize_session=False)
    InventoryMovement.query.filter_by(to_warehouse_id=w.id).update({InventoryMovement.to_warehouse_id: None}, synchronize_session=False)
    _warehouse_audit(user.id, w, "warehouse.deleted", {"warehouse": w.name})
    db.session.delete(w)
    db.session.commit()
    return jsonify(deleted=True)


# ---------- changes confirmed from an assistant draft ----------


@api_bp.post("/organizations/<int:org_id>/inventory/changes")
@jwt_required()
def apply_stock_changes(org_id: int):
    """{changes: [...]}: all saved, or none. The assistant drafts these (services.stock_plans); every line is
    checked again here."""
    from ..services import stock_plans

    user = current_user()
    membership, org = _org(org_id, user.id)
    data = get_json_body()
    try:
        items = stock_plans.apply_changes(org_id, user.id, membership.role, data.get("changes"))
        db.session.commit()
    except ApiError:
        db.session.rollback()
        raise
    return jsonify(items=[item_to_dict(i, org.default_currency) for i in items], applied=len(data["changes"])), 201
