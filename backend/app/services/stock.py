"""Stock rules shared by the Stock page's API and the assistant's confirmed drafts.

Inventories: every item belongs to General stock (the organization's own, project_id empty) or to one
project's inventory. Warehouses belong to an inventory the same way, and an item's quantity can be spread
across that inventory's warehouses (InventoryStock); what isn't in any warehouse is "not in a warehouse".

Quantities only change through movements, so every change has a who, when, where and why.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func

from ..errors import ApiError
from ..extensions import db
from ..models import (
    InventoryItem,
    InventoryMovement,
    InventoryStock,
    MovementKind,
    Project,
    ProjectStatus,
    Warehouse,
)
from . import metrics
from .audit import log_action
from .notifications import members_with_roles, notify
from .permissions import PROJECT_WRITE_ROLES


def q2(v) -> Optional[str]:
    return None if v is None else f"{Decimal(v):.2f}"


# ---------- inventories (General stock or a project) ----------


def project_for_inventory(organization_id: int, project_id, *, field: str = "project_id") -> Optional[Project]:
    """None for General stock; else the organization's project, which must not be archived."""
    if project_id is None:
        return None
    p = db.session.get(Project, project_id) if isinstance(project_id, int) and not isinstance(project_id, bool) else None
    if p is None or p.organization_id != organization_id:
        raise ApiError("validation_error", "Project must belong to this organization.", 400, {"field": field})
    if p.status == ProjectStatus.ARCHIVED:
        raise ApiError("project_archived", "That project is archived.", 409, {"field": field})
    return p


def check_item_editable(item: InventoryItem) -> None:
    if item.archived:
        raise ApiError("item_archived", "This item is archived. Restore it to change its stock.", 409)
    if item.project_id is not None:
        p = db.session.get(Project, item.project_id)
        if p is not None and p.status == ProjectStatus.ARCHIVED:
            raise ApiError("project_archived", "That project is archived.", 409)


def check_project(organization_id: int, project_id) -> None:
    """For "issued for project X" on General stock: any of the organization's projects that isn't archived."""
    if project_id is None:
        return
    project_for_inventory(organization_id, project_id)


# ---------- warehouses ----------


def warehouse_in_inventory(item_or_scope, warehouse_id, *, field: str = "warehouse_id") -> Optional[Warehouse]:
    """The warehouse, which must be in the same inventory as the item (or scope tuple (org_id, project_id))."""
    if warehouse_id is None:
        return None
    if isinstance(item_or_scope, InventoryItem):
        org_id, project_id = item_or_scope.organization_id, item_or_scope.project_id
    else:
        org_id, project_id = item_or_scope
    w = db.session.get(Warehouse, warehouse_id) if isinstance(warehouse_id, int) and not isinstance(warehouse_id, bool) else None
    if w is None or w.organization_id != org_id or w.project_id != project_id:
        raise ApiError("validation_error", "That warehouse isn't in this inventory.", 400, {"field": field})
    return w


def _row(item: InventoryItem, warehouse: Warehouse, *, create: bool) -> Optional[InventoryStock]:
    row = InventoryStock.query.filter_by(item_id=item.id, warehouse_id=warehouse.id).with_for_update().first()
    if row is None and create:
        row = InventoryStock(item_id=item.id, warehouse_id=warehouse.id, quantity=Decimal("0"))
        db.session.add(row)
    return row


def allocated(item: InventoryItem) -> Decimal:
    total = db.session.query(func.coalesce(func.sum(InventoryStock.quantity), 0)).filter(
        InventoryStock.item_id == item.id
    ).scalar()
    return Decimal(total)


def unallocated(item: InventoryItem) -> Decimal:
    return item.quantity_on_hand - allocated(item)


def place_quantity(item: InventoryItem, warehouse: Optional[Warehouse]) -> Decimal:
    if warehouse is None:
        return unallocated(item)
    row = _row(item, warehouse, create=False)
    return row.quantity if row else Decimal("0")


def _take_from(item: InventoryItem, warehouse: Optional[Warehouse], delta: Decimal) -> None:
    """Change the quantity at one place (a warehouse, or not in a warehouse); refuse to go below zero."""
    if warehouse is not None:
        row = _row(item, warehouse, create=True)
        if row.quantity + delta < 0:
            raise ApiError(
                "insufficient_stock", f"Only {q2(row.quantity)} {item.unit} in {warehouse.name}.", 409, {"field": "quantity"}
            )
        row.quantity = row.quantity + delta
        return
    if delta < 0:
        free = unallocated(item)
        if free + delta < 0:
            if free < item.quantity_on_hand:  # some of it is in warehouses
                raise ApiError(
                    "insufficient_stock",
                    f"Only {q2(free)} {item.unit} aren't in a warehouse. Choose the warehouse to take it from.",
                    409,
                    {"field": "warehouse_id"},
                )
            raise ApiError("insufficient_stock", f"Only {q2(item.quantity_on_hand)} {item.unit} on hand.", 409, {"field": "quantity"})


# ---------- movements ----------


def audit(user_id: int, item: InventoryItem, action: str, meta: dict) -> None:
    if item.project_id:
        meta = {**meta, "project_id": item.project_id}  # shows in that project's activity
    log_action(
        organization_id=item.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="inventory_item",
        entity_id=item.id,
        meta=meta,
    )


def apply(
    item: InventoryItem,
    user_id: int,
    kind: MovementKind,
    delta: Decimal,
    *,
    project_id=None,
    note=None,
    warehouse: Optional[Warehouse] = None,
) -> InventoryMovement:
    """Receive, issue, adjust, count or move stock at one place, and record it."""
    was_low = metrics.is_low_stock(item.quantity_on_hand, item.reorder_level)
    after = item.quantity_on_hand + delta
    if after < 0:
        raise ApiError("insufficient_stock", f"Only {q2(item.quantity_on_hand)} {item.unit} on hand.", 409, {"field": "quantity"})
    _take_from(item, warehouse, delta)
    item.quantity_on_hand = after
    if kind == MovementKind.ISSUE and project_id is None and item.project_id is not None:
        project_id = item.project_id  # stock used from a project's inventory counts as that project's materials
    movement = InventoryMovement(
        organization_id=item.organization_id,
        item_id=item.id,
        kind=kind,
        quantity_delta=delta,
        quantity_after=after,
        project_id=project_id,
        warehouse_id=warehouse.id if warehouse else None,
        note=note,
        created_by=user_id,
    )
    db.session.add(movement)
    db.session.flush()
    meta = {"kind": kind.value, "delta": q2(delta), "after": q2(after), "unit": item.unit, "item": item.name}
    if warehouse:
        meta["warehouse"] = warehouse.name
    if project_id and not item.project_id:
        meta["project_id"] = project_id  # General stock issued to a project shows in that project's activity
    audit(user_id, item, f"inventory.{kind.value}", meta)
    if not was_low and metrics.is_low_stock(after, item.reorder_level):
        notify(
            organization_id=item.organization_id,
            user_ids=members_with_roles(item.organization_id, *PROJECT_WRITE_ROLES),
            actor_id=user_id,
            kind="low_stock",
            title=f"Low stock: {item.name}",
            body=f"{q2(after)} {item.unit} left (reorder level {q2(item.reorder_level)}).",
            link=f"/app/inventory?scope={item.project_id or 'general'}",
        )
    return movement


def transfer(
    item: InventoryItem,
    user_id: int,
    quantity: Decimal,
    source: Optional[Warehouse],
    target: Optional[Warehouse],
    note=None,
) -> InventoryMovement:
    """Move stock between two places of the same inventory. The item's total doesn't change."""
    if quantity <= 0:
        raise ApiError("validation_error", "Give a quantity greater than zero.", 400, {"field": "quantity"})
    if (source.id if source else None) == (target.id if target else None):
        raise ApiError("validation_error", "Choose two different places.", 400, {"field": "to_warehouse_id"})
    _take_from(item, source, -quantity)
    if target is not None:
        row = _row(item, target, create=True)
        row.quantity = row.quantity + quantity
    movement = InventoryMovement(
        organization_id=item.organization_id,
        item_id=item.id,
        kind=MovementKind.TRANSFER,
        quantity_delta=quantity,
        quantity_after=item.quantity_on_hand,
        warehouse_id=source.id if source else None,
        to_warehouse_id=target.id if target else None,
        project_id=item.project_id,
        note=note,
        created_by=user_id,
    )
    db.session.add(movement)
    db.session.flush()
    audit(user_id, item, "inventory.transfer", {
        "item": item.name, "unit": item.unit, "quantity": q2(quantity),
        "from": source.name if source else None, "to": target.name if target else None,
    })
    return movement


def matching_item(organization_id: int, project_id: Optional[int], like: InventoryItem) -> Optional[InventoryItem]:
    """The item with the same name (ignoring case) in another inventory, if there is one."""
    return InventoryItem.query.filter(
        InventoryItem.organization_id == organization_id,
        InventoryItem.project_id.is_(None) if project_id is None else InventoryItem.project_id == project_id,
        func.lower(InventoryItem.name) == like.name.lower(),
    ).first()


def move_to_inventory(
    item: InventoryItem,
    user_id: int,
    quantity: Decimal,
    target_project: Optional[Project],
    *,
    source: Optional[Warehouse] = None,
    target_warehouse_id=None,
    note=None,
) -> InventoryItem:
    """Move stock to another inventory (General stock <-> a project). The item there is found by name, or created."""
    target_project_id = target_project.id if target_project else None
    if target_project_id == item.project_id:
        raise ApiError("validation_error", "Choose a different inventory.", 400, {"field": "to_project_id"})
    if quantity <= 0:
        raise ApiError("validation_error", "Give a quantity greater than zero.", 400, {"field": "quantity"})
    target = matching_item(item.organization_id, target_project_id, item)
    if target is not None and target.unit != item.unit:
        raise ApiError(
            "unit_mismatch", f"{target.name} is counted in {target.unit} there, not {item.unit}.", 409, {"field": "to_project_id"}
        )
    if target is None:
        target = InventoryItem(
            organization_id=item.organization_id, project_id=target_project_id, name=item.name, sku=item.sku,
            unit=item.unit, unit_cost=item.unit_cost, reorder_level=None, location=item.location,
            description=item.description, quantity_on_hand=Decimal("0"), archived=False,
        )
        db.session.add(target)
        db.session.flush()
        audit(user_id, target, "inventory.item_created", {"item": target.name, "source": "move"})
    elif target.archived:
        target.archived = False
    target_warehouse = warehouse_in_inventory(target, target_warehouse_id, field="to_warehouse_id")
    where_to = target_project.name if target_project else "General stock"
    where_from = db.session.get(Project, item.project_id).name if item.project_id else "General stock"
    apply(item, user_id, MovementKind.MOVE_OUT, -quantity, warehouse=source, note=note or f"Moved to {where_to}",
          project_id=target_project_id)
    apply(target, user_id, MovementKind.MOVE_IN, quantity, warehouse=target_warehouse,
          note=note or f"Moved from {where_from}", project_id=target_project_id)
    return target


def delete_item(item: InventoryItem, user_id: int) -> None:
    """Remove an item for good, with its stock and history. The audit log keeps a record."""
    audit(user_id, item, "inventory.item_deleted", {"item": item.name, "quantity": q2(item.quantity_on_hand), "unit": item.unit})
    InventoryStock.query.filter_by(item_id=item.id).delete(synchronize_session=False)
    InventoryMovement.query.filter_by(item_id=item.id).delete(synchronize_session=False)
    db.session.delete(item)


# ---------- reading ----------


def stock_by_item(item_ids: list[int]) -> dict[int, list[dict]]:
    """Per item: [{warehouse_id, warehouse, quantity}] for the warehouses that hold some of it."""
    if not item_ids:
        return {}
    rows = (
        db.session.query(InventoryStock, Warehouse)
        .join(Warehouse, Warehouse.id == InventoryStock.warehouse_id)
        .filter(InventoryStock.item_id.in_(item_ids), InventoryStock.quantity != 0)
        .order_by(Warehouse.name)
        .all()
    )
    out: dict[int, list[dict]] = {}
    for s, w in rows:
        out.setdefault(s.item_id, []).append({"warehouse_id": w.id, "warehouse": w.name, "quantity": q2(s.quantity)})
    return out


def item_to_dict(item: InventoryItem, currency: str, stock: Optional[list[dict]] = None) -> dict:
    stock = stock if stock is not None else stock_by_item([item.id]).get(item.id, [])
    in_warehouses = sum((Decimal(s["quantity"]) for s in stock), Decimal("0"))
    return {
        "id": item.id,
        "project_id": item.project_id,
        "name": item.name,
        "sku": item.sku,
        "unit": item.unit,
        "unit_cost": q2(item.unit_cost),
        "currency": currency,
        "quantity_on_hand": q2(item.quantity_on_hand),
        "reorder_level": q2(item.reorder_level),
        "location": item.location,
        "description": item.description,
        "archived": item.archived,
        "stock_value": q2(metrics.stock_value(item.quantity_on_hand, item.unit_cost)),
        "low_stock": not item.archived and metrics.is_low_stock(item.quantity_on_hand, item.reorder_level),
        "stock": stock,
        "not_in_warehouse": q2(item.quantity_on_hand - in_warehouses),
    }


def warehouse_to_dict(w: Warehouse, contents: Optional[dict] = None) -> dict:
    contents = contents or {"item_count": 0, "units": "0.00", "value": "0.00"}
    return {
        "id": w.id,
        "project_id": w.project_id,
        "name": w.name,
        "address": w.address,
        "lat": w.lat,
        "lng": w.lng,
        "notes": w.notes,
        **contents,
    }


def warehouse_contents(warehouse_ids: list[int]) -> dict[int, dict]:
    if not warehouse_ids:
        return {}
    rows = (
        db.session.query(InventoryStock, InventoryItem)
        .join(InventoryItem, InventoryItem.id == InventoryStock.item_id)
        .filter(InventoryStock.warehouse_id.in_(warehouse_ids), InventoryStock.quantity != 0)
        .all()
    )
    out = {wid: {"item_count": 0, "units": Decimal("0"), "value": Decimal("0")} for wid in warehouse_ids}
    for s, item in rows:
        c = out[s.warehouse_id]
        c["item_count"] += 1
        c["units"] += s.quantity
        c["value"] += metrics.stock_value(s.quantity, item.unit_cost) or 0
    return {wid: {"item_count": c["item_count"], "units": q2(c["units"]), "value": q2(metrics.q(c["value"]))}
            for wid, c in out.items()}
