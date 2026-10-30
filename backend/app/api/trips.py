"""Trip planning: trips on a project, their itinerary, travelers, and spend from linked expenses.

Contributors and above plan trips; managers or the trip's creator change or delete them. Money is in the
project's currency. Itinerary times are local "HH:MM" strings at the place they happen.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from flask import jsonify
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Expense, OrganizationMember, Project, Trip, TripItem, TripItemKind, TripStatus, User
from ..services import metrics
from ..services import projects as svc
from ..services.audit import log_action
from ..services.notifications import human_date, notify
from ..services.permissions import CONTRIBUTE_ROLES, PROJECT_WRITE_ROLES, require_role
from . import api_bp
from .auth import current_user
from .validation import get_json_body, optional_str, parse_date, parse_enum, parse_money, require_str

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_TRAVELERS = 50


def _m(v) -> str | None:
    return None if v is None else f"{Decimal(v):.2f}"


def item_to_dict(i: TripItem) -> dict:
    return {
        "id": i.id,
        "trip_id": i.trip_id,
        "kind": i.kind.value,
        "title": i.title,
        "date": i.date.isoformat(),
        "start_time": i.start_time,
        "end_time": i.end_time,
        "location": i.location,
        "confirmation": i.confirmation,
        "estimated_cost": _m(i.estimated_cost),
        "notes": i.notes,
    }


def trip_to_dict(t: Trip, project: Project, items: list[TripItem], expenses: list[Expense], *, full: bool = False) -> dict:
    estimated = metrics.sum_money(i.estimated_cost for i in items if i.estimated_cost is not None)
    actual = metrics.total_actual_expenses(expenses)
    body = {
        "id": t.id,
        "project_id": t.project_id,
        "title": t.title,
        "destination": t.destination,
        "purpose": t.purpose,
        "start_date": t.start_date.isoformat(),
        "end_date": t.end_date.isoformat(),
        "nights": (t.end_date - t.start_date).days,
        "status": t.status.value,
        "currency": project.currency,
        "budget": _m(t.budget),
        "estimated_cost": _m(estimated),
        "actual": _m(actual),
        "remaining": _m(metrics.remaining_budget(t.budget, actual)) if t.budget is not None else None,
        "over_budget": t.budget is not None and actual > t.budget,
        "travelers": [{"user_id": u.id, "name": f"{u.first_name} {u.last_name}"} for u in sorted(t.travelers, key=lambda u: u.first_name)],
        "item_count": len(items),
        "created_by": t.created_by,
    }
    if full:
        body["items"] = [item_to_dict(i) for i in sorted(items, key=_item_order)]
        body["expenses"] = [
            {"id": e.id, "category": e.category, "amount": _m(e.amount), "expense_date": e.expense_date.isoformat(),
             "description": e.description, "status": e.status.value}
            for e in sorted(expenses, key=lambda e: (e.expense_date, e.id))
        ]
    return body


def _item_order(i: TripItem):
    return (i.date, i.start_time is None, i.start_time or "", i.id)


def _load(trip: Trip):
    items = TripItem.query.filter_by(trip_id=trip.id).all()
    expenses = Expense.query.filter_by(trip_id=trip.id).all()
    return items, expenses


def _trip_for_user(trip_id: int, user_id: int):
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        raise ApiError("not_found", "Trip not found.", 404)
    try:
        project, membership = svc.get_project_for_user(trip.project_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Trip not found.", 404)
    return trip, project, membership


def _require_can_edit(trip: Trip, membership, user_id: int) -> None:
    if membership.role in PROJECT_WRITE_ROLES:
        return
    if membership.role in CONTRIBUTE_ROLES and trip.created_by == user_id:
        return
    raise ApiError("forbidden", "You do not have permission to do this.", 403)


def _audit(user_id: int, project: Project, action: str, trip: Trip, meta: dict) -> None:
    log_action(
        organization_id=project.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="trip",
        entity_id=trip.id,
        meta={"project_id": project.id, **meta},
    )


def _parse_time(data: dict, field: str):
    value = data.get(field)
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not TIME_RE.match(value.strip()):
        raise ApiError("validation_error", "Use a time like 09:30.", 400, {"field": field})
    return value.strip()


def _travelers(project: Project, data: dict) -> list[User] | None:
    if "traveler_ids" not in data:
        return None
    ids = data["traveler_ids"]
    if not isinstance(ids, list) or len(ids) > MAX_TRAVELERS or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ApiError("validation_error", "Travelers must be a list of members.", 400, {"field": "traveler_ids"})
    ids = set(ids)
    if not ids:
        return []
    members = {
        m.user_id
        for m in OrganizationMember.query.filter(
            OrganizationMember.organization_id == project.organization_id,
            OrganizationMember.status == "active",
            OrganizationMember.user_id.in_(ids),
        )
    }
    if members != ids:
        raise ApiError("validation_error", "Travelers must be members of this organization.", 400, {"field": "traveler_ids"})
    return User.query.filter(User.id.in_(ids)).all()


def _notify_travelers(trip: Trip, project: Project, user_ids, actor_id: int) -> None:
    notify(
        organization_id=project.organization_id,
        user_ids=user_ids,
        actor_id=actor_id,
        kind="trip_traveler",
        title=f"You're on a trip: {trip.title}",
        body=f"{trip.destination}, {human_date(trip.start_date)} to {human_date(trip.end_date)}.",
        link=f"/app/projects/{project.id}/trips/{trip.id}",
    )


def _check_dates(start: date, end: date) -> None:
    if end < start:
        raise ApiError("validation_error", "The trip can't end before it starts.", 400, {"field": "end_date"})


# ---------- trips ----------


@api_bp.get("/projects/<int:project_id>/trips")
@jwt_required()
def list_trips(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    trips = Trip.query.filter_by(project_id=project.id).order_by(Trip.start_date, Trip.id).all()
    ids = [t.id for t in trips]
    items = TripItem.query.filter(TripItem.trip_id.in_(ids)).all() if ids else []
    expenses = Expense.query.filter(Expense.trip_id.in_(ids)).all() if ids else []
    return jsonify(
        trips=[
            trip_to_dict(t, project, [i for i in items if i.trip_id == t.id], [e for e in expenses if e.trip_id == t.id])
            for t in trips
        ]
    )


@api_bp.post("/projects/<int:project_id>/trips")
@jwt_required()
def create_trip(project_id: int):
    user = current_user()
    project, membership = svc.get_project_for_user(project_id, user.id)
    require_role(membership, *CONTRIBUTE_ROLES)
    svc.require_active_project(project)
    data = get_json_body()
    start = parse_date(data, "start_date", required=True)
    end = parse_date(data, "end_date", required=True)
    _check_dates(start, end)
    trip = Trip(
        project_id=project.id,
        title=require_str(data, "title", max_len=200),
        destination=require_str(data, "destination", max_len=200),
        purpose=optional_str(data, "purpose", max_len=5000),
        start_date=start,
        end_date=end,
        status=parse_enum(data, "status", TripStatus, TripStatus.PLANNED),
        budget=parse_money(data, "budget", required=False),
        created_by=user.id,
    )
    travelers = _travelers(project, data)
    trip.travelers = travelers if travelers is not None else [user]
    db.session.add(trip)
    db.session.flush()
    _audit(user.id, project, "trip.created", trip, {"destination": trip.destination, "start_date": start.isoformat()})
    _notify_travelers(trip, project, [u.id for u in trip.travelers], user.id)
    db.session.commit()
    return jsonify(trip=trip_to_dict(trip, project, [], [], full=True)), 201


@api_bp.get("/trips/<int:trip_id>")
@jwt_required()
def get_trip(trip_id: int):
    user = current_user()
    trip, project, membership = _trip_for_user(trip_id, user.id)
    items, expenses = _load(trip)
    body = trip_to_dict(trip, project, items, expenses, full=True)
    body["project_name"] = project.name
    body["project_status"] = project.status.value
    body["can_edit"] = project.status.value != "archived" and (
        membership.role in PROJECT_WRITE_ROLES or (membership.role in CONTRIBUTE_ROLES and trip.created_by == user.id)
    )
    return jsonify(trip=body)


@api_bp.patch("/trips/<int:trip_id>")
@jwt_required()
def update_trip(trip_id: int):
    user = current_user()
    trip, project, membership = _trip_for_user(trip_id, user.id)
    _require_can_edit(trip, membership, user.id)
    svc.require_active_project(project)
    data = get_json_body()

    changes: dict = {}
    for field, max_len in (("title", 200), ("destination", 200)):
        if field in data:
            changes[field] = require_str(data, field, max_len=max_len)
    if "purpose" in data:
        changes["purpose"] = optional_str(data, "purpose", max_len=5000)
    if "start_date" in data:
        changes["start_date"] = parse_date(data, "start_date", required=True)
    if "end_date" in data:
        changes["end_date"] = parse_date(data, "end_date", required=True)
    if "status" in data:
        status = parse_enum(data, "status", TripStatus)
        if status is None:
            raise ApiError("validation_error", "Status can't be empty.", 400, {"field": "status"})
        changes["status"] = status
    if "budget" in data:
        changes["budget"] = parse_money(data, "budget", required=False)

    start, end = changes.get("start_date", trip.start_date), changes.get("end_date", trip.end_date)
    _check_dates(start, end)
    items, _ = _load(trip)
    outside = [i for i in items if not start <= i.date <= end]
    if outside:
        raise ApiError(
            "itinerary_outside_dates",
            f"{len(outside)} itinerary {'item is' if len(outside) == 1 else 'items are'} outside the new dates. Move or remove them first.",
            409,
            {"field": "start_date" if any(i.date < start for i in outside) else "end_date"},
        )

    meta = {}
    for field, new in changes.items():
        old = getattr(trip, field)
        if old == new:
            continue
        setattr(trip, field, new)
        if field in ("title", "purpose", "destination"):
            meta[field] = "changed"
        else:
            meta[field] = [v.value if hasattr(v, "value") else (v.isoformat() if hasattr(v, "isoformat") else _m(v)) for v in (old, new)]
    travelers = _travelers(project, data)
    if travelers is not None and {u.id for u in travelers} != {u.id for u in trip.travelers}:
        added = {u.id for u in travelers} - {u.id for u in trip.travelers}
        trip.travelers = travelers
        _notify_travelers(trip, project, added, user.id)
        meta["travelers"] = "changed"
    if meta:
        _audit(user.id, project, "trip.updated", trip, meta)
        db.session.commit()
    items, expenses = _load(trip)
    return jsonify(trip=trip_to_dict(trip, project, items, expenses, full=True))


@api_bp.delete("/trips/<int:trip_id>")
@jwt_required()
def delete_trip(trip_id: int):
    user = current_user()
    trip, project, membership = _trip_for_user(trip_id, user.id)
    _require_can_edit(trip, membership, user.id)
    svc.require_active_project(project)
    unlinked = Expense.query.filter_by(trip_id=trip.id).update({"trip_id": None})
    TripItem.query.filter_by(trip_id=trip.id).delete()
    trip.travelers = []
    _audit(user.id, project, "trip.deleted", trip, {"title": trip.title, "unlinked_expenses": unlinked})
    db.session.delete(trip)
    db.session.commit()
    return jsonify(ok=True)


# ---------- itinerary ----------


def _item_fields(data: dict, trip: Trip, *, creating: bool) -> dict:
    fields: dict = {}
    if creating or "kind" in data:
        kind = parse_enum(data, "kind", TripItemKind)
        if kind is None:
            raise ApiError("validation_error", "Choose what kind of item this is.", 400, {"field": "kind"})
        fields["kind"] = kind
    if creating or "title" in data:
        fields["title"] = require_str(data, "title", max_len=200)
    if creating or "date" in data:
        d = parse_date(data, "date", required=True)
        if not trip.start_date <= d <= trip.end_date:
            raise ApiError("validation_error", "The date must be within the trip.", 400, {"field": "date"})
        fields["date"] = d
    for key in ("start_time", "end_time"):
        if creating or key in data:
            fields[key] = _parse_time(data, key)
    for key, max_len in (("location", 200), ("confirmation", 100), ("notes", 5000)):
        if creating or key in data:
            fields[key] = optional_str(data, key, max_len=max_len)
    if creating or "estimated_cost" in data:
        fields["estimated_cost"] = parse_money(data, "estimated_cost", required=False)
    return fields


@api_bp.post("/trips/<int:trip_id>/items")
@jwt_required()
def add_trip_item(trip_id: int):
    user = current_user()
    trip, project, membership = _trip_for_user(trip_id, user.id)
    _require_can_edit(trip, membership, user.id)
    svc.require_active_project(project)
    item = TripItem(trip_id=trip.id, **_item_fields(get_json_body(), trip, creating=True))
    db.session.add(item)
    db.session.flush()
    _audit(user.id, project, "trip.item_added", trip, {"kind": item.kind.value, "item": item.title})
    db.session.commit()
    return jsonify(item=item_to_dict(item)), 201


def _trip_item_for_user(item_id: int, user_id: int):
    item = db.session.get(TripItem, item_id)
    if item is None:
        raise ApiError("not_found", "Itinerary item not found.", 404)
    try:
        trip, project, membership = _trip_for_user(item.trip_id, user_id)
    except ApiError:
        raise ApiError("not_found", "Itinerary item not found.", 404)
    _require_can_edit(trip, membership, user_id)
    svc.require_active_project(project)
    return item, trip, project


@api_bp.patch("/trip-items/<int:item_id>")
@jwt_required()
def update_trip_item(item_id: int):
    user = current_user()
    item, trip, project = _trip_item_for_user(item_id, user.id)
    for key, value in _item_fields(get_json_body(), trip, creating=False).items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(item=item_to_dict(item))


@api_bp.delete("/trip-items/<int:item_id>")
@jwt_required()
def delete_trip_item(item_id: int):
    user = current_user()
    item, trip, project = _trip_item_for_user(item_id, user.id)
    _audit(user.id, project, "trip.item_removed", trip, {"kind": item.kind.value, "item": item.title})
    db.session.delete(item)
    db.session.commit()
    return jsonify(ok=True)


def check_trip(project: Project, trip_id) -> None:
    """For expenses: the trip must belong to the same project."""
    if trip_id is None:
        return
    trip = db.session.get(Trip, trip_id)
    if trip is None or trip.project_id != project.id:
        raise ApiError("validation_error", "Trip must belong to this project.", 400, {"field": "trip_id"})
