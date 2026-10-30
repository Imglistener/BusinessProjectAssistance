"""Trip planning: trips on a project, their itinerary, travelers, and spend from linked expenses.

Contributors and above plan trips; managers or the trip's creator change or delete them. Money is in the
project's currency. Itinerary times are local "HH:MM" strings at the place they happen.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Expense, Organization, OrganizationMember, Project, Trip, TripItem, TripItemKind, TripStatus, User
from ..services import metrics
from ..services import projects as svc
from ..services import travel
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
        "route": {
            "origin": t.origin,
            "origin_lat": _coord(t.origin_lat),
            "origin_lng": _coord(t.origin_lng),
            "destination_lat": _coord(t.destination_lat),
            "destination_lng": _coord(t.destination_lng),
            "distance_km": None if t.distance_km is None else f"{Decimal(t.distance_km):.1f}",
            "distance_source": t.distance_source,
            "vehicle_type": t.vehicle_type,
            "vehicle_count": t.vehicle_count or 1,
            "round_trip": True if t.round_trip is None else t.round_trip,
            "fuel_city": t.fuel_city,
        },
    }
    if full:
        body["items"] = [item_to_dict(i) for i in sorted(items, key=_item_order)]
        body["expenses"] = [
            {"id": e.id, "category": e.category, "amount": _m(e.amount), "expense_date": e.expense_date.isoformat(),
             "description": e.description, "status": e.status.value}
            for e in sorted(expenses, key=lambda e: (e.expense_date, e.id))
        ]
    return body


def _coord(v) -> float | None:
    return None if v is None else float(v)


def _parse_coord(data: dict, field: str, limit: int):
    value = data.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ApiError("validation_error", "Coordinates must be numbers.", 400, {"field": field})
    try:
        d = Decimal(str(value)).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        raise ApiError("validation_error", "Coordinates must be numbers.", 400, {"field": field})
    if not -limit <= d <= limit:
        raise ApiError("validation_error", "Coordinates are out of range.", 400, {"field": field})
    return d


ROUTE_FIELDS = (
    "origin", "origin_lat", "origin_lng", "destination_lat", "destination_lng", "distance_km",
    "distance_source", "vehicle_type", "vehicle_count", "round_trip", "fuel_city",
)


def _route_changes(trip: Trip, data: dict) -> dict:
    """Validated route fields from the request; fills in a straight-line distance when only places are given."""
    if not any(k in data for k in ROUTE_FIELDS):
        return {}
    c: dict = {}
    if "origin" in data:
        c["origin"] = optional_str(data, "origin", max_len=200)
    for field, limit in (("origin_lat", 90), ("origin_lng", 180), ("destination_lat", 90), ("destination_lng", 180)):
        if field in data:
            c[field] = _parse_coord(data, field, limit)
    if "vehicle_type" in data:
        vt = data.get("vehicle_type") or None
        if vt is not None and vt not in travel.VEHICLES:
            raise ApiError("validation_error", "Unknown vehicle type.", 400, {"field": "vehicle_type"})
        c["vehicle_type"] = vt
    if "vehicle_count" in data:
        n = data.get("vehicle_count")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 50:
            raise ApiError("validation_error", "Vehicles must be a whole number from 1 to 50.", 400, {"field": "vehicle_count"})
        c["vehicle_count"] = n
    if "round_trip" in data:
        if not isinstance(data["round_trip"], bool):
            raise ApiError("validation_error", "Round trip must be true or false.", 400, {"field": "round_trip"})
        c["round_trip"] = data["round_trip"]
    if "fuel_city" in data:
        c["fuel_city"] = optional_str(data, "fuel_city", max_len=80)

    source = data.get("distance_source")
    if source not in (None, "", "route", "manual", "straight_line"):
        raise ApiError("validation_error", "Unknown distance source.", 400, {"field": "distance_source"})
    if data.get("distance_km") not in (None, "") and source in ("route", "manual"):
        km = parse_money({"distance_km": data["distance_km"]}, "distance_km", positive=True)
        if km > 20000:
            raise ApiError("validation_error", "That distance is too long.", 400, {"field": "distance_km"})
        c["distance_km"], c["distance_source"] = km.quantize(Decimal("0.1")), source
    else:
        coords = [c.get(k, getattr(trip, k)) for k in ("origin_lat", "origin_lng", "destination_lat", "destination_lng")]
        if all(v is not None for v in coords):
            straight = metrics.straight_line_km(*coords)
            c["distance_km"] = (straight * travel.ROAD_FACTOR).quantize(Decimal("0.1"))
            c["distance_source"] = "straight_line"
        elif "distance_km" in data and data["distance_km"] in (None, ""):
            c["distance_km"], c["distance_source"] = None, None
    return c


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
    for key, value in _route_changes(trip, data).items():
        setattr(trip, key, value)
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
    changes.update(_route_changes(trip, data))

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
        if field in ("title", "purpose", "destination") or field in ROUTE_FIELDS:
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


# ---------- fuel ----------


def _bool_arg(name: str):
    v = request.args.get(name)
    return None if v is None else v == "true"


@api_bp.get("/trips/<int:trip_id>/fuel-estimate")
@jwt_required()
def fuel_estimate(trip_id: int):
    """Query overrides (not saved): vehicle_type, vehicle_count, round_trip, l_per_100km, variance."""
    user = current_user()
    trip, project, _ = _trip_for_user(trip_id, user.id)
    overrides: dict = {"vehicle_type": request.args.get("vehicle_type") or None, "round_trip": _bool_arg("round_trip")}
    try:
        if request.args.get("vehicle_count"):
            overrides["vehicle_count"] = min(max(int(request.args["vehicle_count"]), 1), 50)
        if request.args.get("l_per_100km"):
            v = Decimal(request.args["l_per_100km"])
            if not Decimal("1") <= v <= Decimal("60"):
                raise ValueError
            overrides["l_per_100km"] = v
        if request.args.get("variance"):
            v = Decimal(request.args["variance"])
            if not Decimal("0") <= v <= Decimal("50"):
                raise ValueError
            overrides["distance_variance_pct"] = v
    except (ValueError, ArithmeticError):
        raise ApiError("validation_error", "Check the vehicle count, consumption (1-60 L/100 km) and variance (0-50%).", 400)
    if overrides["vehicle_type"] and overrides["vehicle_type"] not in travel.VEHICLES:
        raise ApiError("validation_error", "Unknown vehicle type.", 400, {"field": "vehicle_type"})
    try:
        return jsonify(estimate=travel.estimate_for_trip(trip, project, overrides))
    except travel.EstimateUnavailable as e:
        raise ApiError("estimate_unavailable", str(e), 409)


@api_bp.get("/travel/reference")
@jwt_required()
def travel_reference():
    current_user()
    return jsonify(
        vehicles=[
            {"type": v.key, "label": v.label, "fuel": v.fuel.value,
             "l_per_100km_low": str(v.l_per_100km_low), "l_per_100km_high": str(v.l_per_100km_high)}
            for v in travel.VEHICLES.values()
        ],
        default_vehicle=travel.DEFAULT_VEHICLE,
        cities=[{"name": n, "lat": lat, "lng": lng} for n, (lat, lng) in travel.CITIES.items()],
        road_factor=str(travel.ROAD_FACTOR),
    )


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
