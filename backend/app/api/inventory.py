"""Inventory: stock items, movements (receive / issue / adjust) and stock counts.

Quantities only change through movements, so every change has a who, when and why. Values use the
organization's default currency. Arithmetic on quantities and values lives in services.metrics.
"""
from __future__ import annotations

from decimal import Decimal

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from ..errors import ApiError
from ..extensions import db
from ..models import InventoryItem, InventoryMovement, MovementKind, Organization, Project, ProjectStatus, User
from ..services import metrics
from ..services import projects as svc
from ..services.audit import log_action
from ..services.notifications import members_with_roles, notify
from ..services.permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES, get_membership, require_role
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
# Contributors receive, issue and count stock; manual adjustments are for managers.
ADJUST_ROLES = PROJECT_WRITE_ROLES


def _q(v) -> str | None:
    return None if v is None else f"{Decimal(v):.2f}"


def item_to_dict(item: InventoryItem, currency: str) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "sku": item.sku,
        "unit": item.unit,
        "unit_cost": _q(item.unit_cost),
        "currency": currency,
        "quantity_on_hand": _q(item.quantity_on_hand),
        "reorder_level": _q(item.reorder_level),
        "location": item.location,
        "description": item.description,
        "archived": item.archived,
        "stock_value": _q(metrics.stock_value(item.quantity_on_hand, item.unit_cost)),
        "low_stock": not item.archived and metrics.is_low_stock(item.quantity_on_hand, item.reorder_level),
    }


def movement_to_dict(m: InventoryMovement, names: dict, projects: dict) -> dict:
    return {
        "id": m.id,
        "item_id": m.item_id,
        "kind": m.kind.value,
        "quantity_delta": _q(m.quantity_delta),
        "quantity_after": _q(m.quantity_after),
        "project_id": m.project_id,
        "project_name": projects.get(m.project_id),
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


def _audit(user_id: int, item: InventoryItem, action: str, meta: dict) -> None:
    log_action(
        organization_id=item.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="inventory_item",
        entity_id=item.id,
        meta=meta,
    )


def _apply(item: InventoryItem, user_id: int, kind: MovementKind, delta: Decimal, *, project_id=None, note=None):
    was_low = metrics.is_low_stock(item.quantity_on_hand, item.reorder_level)
    after = item.quantity_on_hand + delta
    if after < 0:
        raise ApiError(
            "insufficient_stock",
            f"Only {_q(item.quantity_on_hand)} {item.unit} on hand.",
            409,
            {"field": "quantity"},
        )
    item.quantity_on_hand = after
    movement = InventoryMovement(
        organization_id=item.organization_id,
        item_id=item.id,
        kind=kind,
        quantity_delta=delta,
        quantity_after=after,
        project_id=project_id,
        note=note,
        created_by=user_id,
    )
    db.session.add(movement)
    db.session.flush()
    meta = {"kind": kind.value, "delta": _q(delta), "after": _q(after), "unit": item.unit, "item": item.name}
    if project_id:
        meta["project_id"] = project_id  # shows the issue in that project's activity
    _audit(user_id, item, f"inventory.{kind.value}", meta)
    if not was_low and metrics.is_low_stock(after, item.reorder_level):
        notify(
            organization_id=item.organization_id,
            user_ids=members_with_roles(item.organization_id, *PROJECT_WRITE_ROLES),
            actor_id=user_id,
            kind="low_stock",
            title=f"Low stock: {item.name}",
            body=f"{_q(after)} {item.unit} left (reorder level {_q(item.reorder_level)}).",
            link="/app/inventory",
        )
    return movement


def _check_project(org_id: int, project_id) -> None:
    if project_id is None:
        return
    p = db.session.get(Project, project_id)
    if p is None or p.organization_id != org_id:
        raise ApiError("validation_error", "Project must belong to this organization.", 400, {"field": "project_id"})
    if p.status == ProjectStatus.ARCHIVED:
        raise ApiError("project_archived", "That project is archived.", 409, {"field": "project_id"})


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


# ---------- items ----------


@api_bp.get("/organizations/<int:org_id>/inventory")
@jwt_required()
def list_inventory(org_id: int):
    user = current_user()
    _, org = _org(org_id, user.id)
    query = InventoryItem.query.filter_by(organization_id=org_id)
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
    every = InventoryItem.query.filter_by(organization_id=org_id).all()
    rows = [item_to_dict(i, org.default_currency) for i in items]
    if request.args.get("low_stock") == "true":
        rows = [r for r in rows if r["low_stock"]]
    return jsonify(items=rows, summary={**_summary(every), "currency": org.default_currency})


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


@api_bp.post("/organizations/<int:org_id>/inventory")
@jwt_required()
def create_item(org_id: int):
    user = current_user()
    membership, org = _org(org_id, user.id)
    require_role(membership, *PROJECT_WRITE_ROLES)
    data = get_json_body()
    item = InventoryItem(organization_id=org_id, quantity_on_hand=Decimal("0"), archived=False, **_item_fields(data, creating=True))
    db.session.add(item)
    db.session.flush()
    _audit(user.id, item, "inventory.item_created", {"item": item.name})
    opening = parse_quantity(data, "quantity", required=False)
    if opening:
        _apply(item, user.id, MovementKind.COUNT, opening, note="Opening stock")
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
        _audit(user.id, item, "inventory.item_updated", meta)
        db.session.commit()
    return jsonify(item=item_to_dict(item, org.default_currency))


# ---------- movements ----------


@api_bp.post("/inventory/<int:item_id>/movements")
@jwt_required()
def record_movement(item_id: int):
    """{kind: receive|issue|adjust, quantity, project_id?, note?}. Adjust takes a signed quantity."""
    user = current_user()
    item, membership, org = _item_for_user(item_id, user.id, lock=True)
    data = get_json_body()
    kind = data.get("kind")
    if kind not in ("receive", "issue", "adjust"):
        raise ApiError("validation_error", "Kind must be receive, issue or adjust.", 400, {"field": "kind"})
    require_role(membership, *(ADJUST_ROLES if kind == "adjust" else CONTRIBUTE_ROLES))
    if item.archived:
        raise ApiError("item_archived", "This item is archived. Restore it to change its stock.", 409)

    note = optional_str(data, "note", max_len=500)
    project_id = None
    if kind == "adjust":
        delta = parse_signed_quantity(data, "quantity")
        if not note:
            raise ApiError("validation_error", "Say why the stock is being adjusted.", 400, {"field": "note"})
    else:
        qty = parse_quantity(data, "quantity", positive=True)
        delta = qty if kind == "receive" else -qty
        if kind == "issue":
            project_id = parse_optional_id(data, "project_id")
            _check_project(item.organization_id, project_id)

    movement = _apply(item, user.id, MovementKind(kind), delta, project_id=project_id, note=note)
    db.session.commit()
    names = {user.id: f"{user.first_name} {user.last_name}"}
    projects = {project_id: db.session.get(Project, project_id).name} if project_id else {}
    return jsonify(item=item_to_dict(item, org.default_currency), movement=movement_to_dict(movement, names, projects)), 201


def _history(query, limit: int, offset: int):
    total = query.count()
    rows = query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc()).limit(limit).offset(offset).all()
    user_ids = {m.created_by for m in rows}
    project_ids = {m.project_id for m in rows if m.project_id}
    names = {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(user_ids))} if user_ids else {}
    projects = {p.id: p.name for p in Project.query.filter(Project.id.in_(project_ids))} if project_ids else {}
    return total, [movement_to_dict(m, names, projects) for m in rows]


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
    """Stock issued to a project, per item, valued at the items' current unit cost."""
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


# ---------- stock counts ----------


@api_bp.post("/organizations/<int:org_id>/inventory/counts")
@jwt_required()
def record_count(org_id: int):
    """{counts: [{item_id, counted}], note?}. Sets each item to what was counted; returns the differences."""
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

    parsed: list[tuple[int, Decimal]] = []
    seen = set()
    for line in lines:
        if not isinstance(line, dict):
            raise ApiError("validation_error", "Each count needs an item and a quantity.", 400, {"field": "counts"})
        item_id = parse_optional_id(line, "item_id")
        if item_id is None or item_id in seen:
            raise ApiError("validation_error", "Each item can be counted once.", 400, {"field": "counts"})
        seen.add(item_id)
        parsed.append((item_id, parse_quantity(line, "counted")))

    items = {
        i.id: i
        for i in db.session.query(InventoryItem)
        .filter(InventoryItem.id.in_(seen), InventoryItem.organization_id == org_id)
        .with_for_update()
    }
    if len(items) != len(seen):
        raise ApiError("validation_error", "Some items aren't in this organization.", 400, {"field": "counts"})
    if any(items[i].archived for i in seen):
        raise ApiError("item_archived", "Archived items can't be counted.", 409)

    results = []
    value_change = Decimal("0")
    for item_id, counted in parsed:
        item = items[item_id]
        expected = item.quantity_on_hand
        delta = counted - expected
        if delta != 0:
            _apply(item, user.id, MovementKind.COUNT, delta, note=note)
            value_change += metrics.stock_value(delta, item.unit_cost) or 0
        results.append({"item_id": item_id, "name": item.name, "unit": item.unit, "expected": _q(expected),
                        "counted": _q(counted), "difference": _q(delta)})
    db.session.commit()
    return jsonify(
        results=results,
        changed_count=sum(1 for r in results if Decimal(r["difference"]) != 0),
        value_change=_q(metrics.q(value_change)),
        currency=org.default_currency,
    )


# ---------- changes confirmed from an assistant draft ----------


@api_bp.post("/organizations/<int:org_id>/inventory/changes")
@jwt_required()
def apply_stock_changes(org_id: int):
    """{changes: [{kind, item_id | name..., quantity, project_id?, note?}]}: all saved, or none.

    The assistant drafts these (services.stock_plans); every line is checked again here.
    """
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
