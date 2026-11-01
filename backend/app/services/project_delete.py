"""Deleting projects for good (owners only). Archiving stays the everyday way to put a project away.

What goes: the project, its expenses and receipt files, tasks, milestones, trips (itinerary, travelers),
its own inventory (items, their stock and history) and warehouses, project members, assistant conversations
about it, and notifications that link to it.
What stays: General stock's history (movements issued to the project are kept, detached, so quantities add up)
and the audit log (entries are detached; a "project.deleted" entry records who deleted what).
"""
from __future__ import annotations

from sqlalchemy import or_

from ..errors import ApiError
from ..extensions import db
from ..models import (
    AIConversation,
    AIMessage,
    Attachment,
    AuditLog,
    Expense,
    InventoryItem,
    InventoryMovement,
    InventoryStock,
    Milestone,
    Notification,
    Project,
    ProjectMember,
    Task,
    Trip,
    TripItem,
    Warehouse,
    trip_travelers,
)
from . import storage

MAX_AT_ONCE = 200


def load(organization_id: int, project_ids) -> list[Project]:
    """The organization's projects with these IDs; unknown or foreign IDs are a 404 for the whole request."""
    if (
        not isinstance(project_ids, list)
        or not project_ids
        or not all(isinstance(i, int) and not isinstance(i, bool) for i in project_ids)
    ):
        raise ApiError("validation_error", "Choose at least one project.", 400, {"field": "project_ids"})
    if len(project_ids) > MAX_AT_ONCE:
        raise ApiError("validation_error", f"Delete at most {MAX_AT_ONCE} projects at a time.", 400)
    ids = set(project_ids)
    projects = Project.query.filter(Project.id.in_(ids), Project.organization_id == organization_id).all()
    if len(projects) != len(ids):
        raise ApiError("not_found", "Project not found.", 404)
    return sorted(projects, key=lambda p: p.name.lower())


def summary(projects: list[Project]) -> dict:
    """What deleting these projects would remove, so the person can see it before confirming."""
    ids = [p.id for p in projects]
    expense_ids = db.session.query(Expense.id).filter(Expense.project_id.in_(ids))
    return {
        "projects": [{"id": p.id, "name": p.name, "status": p.status.value} for p in projects],
        "expenses": Expense.query.filter(Expense.project_id.in_(ids)).count(),
        "receipts": Attachment.query.filter(Attachment.expense_id.in_(expense_ids)).count(),
        "tasks": Task.query.filter(Task.project_id.in_(ids)).count(),
        "milestones": Milestone.query.filter(Milestone.project_id.in_(ids)).count(),
        "trips": Trip.query.filter(Trip.project_id.in_(ids)).count(),
        "stock_movements": InventoryMovement.query.join(InventoryItem, InventoryItem.id == InventoryMovement.item_id)
        .filter(InventoryMovement.project_id.in_(ids), InventoryItem.project_id.is_(None)).count(),
        "inventory_items": InventoryItem.query.filter(InventoryItem.project_id.in_(ids)).count(),
        "warehouses": Warehouse.query.filter(Warehouse.project_id.in_(ids)).count(),
    }


def delete(projects: list[Project], actor_id: int) -> list[str]:
    """Delete in the current transaction. Returns receipt files to remove once the transaction commits."""
    ids = [p.id for p in projects]
    names = {p.id: p.name for p in projects}
    counts = summary(projects)

    expense_ids = [e for (e,) in db.session.query(Expense.id).filter(Expense.project_id.in_(ids))]
    files = [a.stored_name for a in Attachment.query.filter(Attachment.expense_id.in_(expense_ids))] if expense_ids else []
    trip_ids = [t for (t,) in db.session.query(Trip.id).filter(Trip.project_id.in_(ids))]
    conversation_ids = [c for (c,) in db.session.query(AIConversation.id).filter(AIConversation.project_id.in_(ids))]

    gone = dict(synchronize_session=False)
    if expense_ids:
        Attachment.query.filter(Attachment.expense_id.in_(expense_ids)).delete(**gone)
    Expense.query.filter(Expense.project_id.in_(ids)).delete(**gone)
    Task.query.filter(Task.project_id.in_(ids)).delete(**gone)
    Milestone.query.filter(Milestone.project_id.in_(ids)).delete(**gone)
    if trip_ids:
        TripItem.query.filter(TripItem.trip_id.in_(trip_ids)).delete(**gone)
        db.session.execute(trip_travelers.delete().where(trip_travelers.c.trip_id.in_(trip_ids)))
        Trip.query.filter(Trip.id.in_(trip_ids)).delete(**gone)
    if conversation_ids:
        AIMessage.query.filter(AIMessage.conversation_id.in_(conversation_ids)).delete(**gone)
        AIConversation.query.filter(AIConversation.id.in_(conversation_ids)).delete(**gone)
    ProjectMember.query.filter(ProjectMember.project_id.in_(ids)).delete(**gone)

    # The project's own inventory and warehouses go with it.
    own_items = [i for (i,) in db.session.query(InventoryItem.id).filter(InventoryItem.project_id.in_(ids))]
    own_warehouses = [w for (w,) in db.session.query(Warehouse.id).filter(Warehouse.project_id.in_(ids))]
    if own_items:
        InventoryStock.query.filter(InventoryStock.item_id.in_(own_items)).delete(**gone)
        InventoryMovement.query.filter(InventoryMovement.item_id.in_(own_items)).delete(**gone)
        InventoryItem.query.filter(InventoryItem.id.in_(own_items)).delete(**gone)
    if own_warehouses:
        InventoryStock.query.filter(InventoryStock.warehouse_id.in_(own_warehouses)).delete(**gone)
        for col in (InventoryMovement.warehouse_id, InventoryMovement.to_warehouse_id):
            InventoryMovement.query.filter(col.in_(own_warehouses)).update({col: None}, **gone)
        Warehouse.query.filter(Warehouse.id.in_(own_warehouses)).delete(**gone)

    # Stock history stays; the movement just no longer points at a project.
    for m in InventoryMovement.query.filter(InventoryMovement.project_id.in_(ids)):
        m.note = ((m.note + " · ") if m.note else "") + f"Issued to deleted project {names[m.project_id]}"
        m.note = m.note[:500]
        m.project_id = None

    links = (
        [Notification.link == f"/app/projects/{i}" for i in ids]
        + [Notification.link.like(f"/app/projects/{i}/%") for i in ids]
        + [Notification.link == f"/app/inventory?scope={i}" for i in ids]
    )
    Notification.query.filter(or_(*links)).delete(**gone)
    AuditLog.query.filter(AuditLog.project_id.in_(ids)).update({AuditLog.project_id: None}, **gone)

    organization_id = projects[0].organization_id
    for p in projects:
        db.session.delete(p)
    db.session.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action="project.deleted",
            entity_type="project",
            entity_id=None,
            meta={
                "projects": [{"id": p.id, "name": p.name} for p in projects],
                **{k: v for k, v in counts.items() if k != "projects"},
            },
        )
    )
    return files


def remove_files(stored_names: list[str]) -> None:
    """After the commit: a missing file isn't an error (it may already be gone)."""
    for name in stored_names:
        try:
            storage.delete(name)
        except OSError:
            pass
