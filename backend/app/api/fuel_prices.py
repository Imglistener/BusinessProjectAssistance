"""Fuel prices the organization keeps for trip estimates. Managers edit; every member can read."""
from __future__ import annotations

from flask import jsonify
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import FuelPrice, FuelType, Organization
from ..services import fuel_sync
from ..services import projects as svc
from ..services.audit import log_action
from ..services.permissions import PROJECT_WRITE_ROLES, get_membership, require_role
from ..services.travel import STALE_PRICE_DAYS
from ..services.tokens import aware
from . import api_bp
from .auth import current_user
from .validation import get_json_body, optional_str, parse_date, parse_enum, parse_money


def price_to_dict(p: FuelPrice, today) -> dict:
    return {
        "id": p.id,
        "city": p.city or None,
        "fuel_type": p.fuel_type.value,
        "price_per_litre": f"{p.price_per_litre:.2f}",
        "currency": p.currency,
        "as_of": p.as_of.isoformat(),
        "stale": (today - p.as_of).days > STALE_PRICE_DAYS,
        "source": p.source or "manual",
        "fetched_at": aware(p.fetched_at).isoformat() if p.fetched_at else None,
    }


@api_bp.get("/organizations/<int:org_id>/fuel-prices")
@jwt_required()
def list_fuel_prices(org_id: int):
    user = current_user()
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    today = svc.org_today(org.timezone)
    rows = FuelPrice.query.filter_by(organization_id=org_id).all()
    rows.sort(key=lambda p: (p.city != "", p.city.lower(), p.fuel_type.value))
    return jsonify(
        prices=[price_to_dict(p, today) for p in rows],
        stale_after_days=STALE_PRICE_DAYS,
        sync={"source": fuel_sync.SOURCE_LABEL, "url": fuel_sync.BASE_URL, "available": org.default_currency == "MAD"},
    )


@api_bp.post("/organizations/<int:org_id>/fuel-prices/sync")
@jwt_required()
def sync_fuel_prices(org_id: int):
    """Update prices from prix-gasoil-maroc.teraedge.ma (national average + main cities). Cached for hours."""
    user = current_user()
    require_role(get_membership(org_id, user.id), *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, org_id)
    try:
        snapshot = fuel_sync.fetch()
        written = fuel_sync.apply(org_id, user.id, snapshot, svc.org_today(org.timezone))
    except fuel_sync.FuelSyncError as e:
        raise ApiError("fuel_sync_failed", str(e), 502)
    log_action(organization_id=org_id, actor_id=user.id, action="fuel_price.synced", entity_type="organization",
               entity_id=org_id, meta={"source": fuel_sync.SOURCE_LABEL, "rows": written})
    db.session.commit()
    return list_fuel_prices(org_id)


@api_bp.put("/organizations/<int:org_id>/fuel-prices")
@jwt_required()
def save_fuel_price(org_id: int):
    """Create or replace the price for (city, fuel type). Leave city empty for the default for any city."""
    user = current_user()
    require_role(get_membership(org_id, user.id), *PROJECT_WRITE_ROLES)
    org = db.session.get(Organization, org_id)
    data = get_json_body()
    city = optional_str(data, "city", max_len=80) or ""
    fuel = parse_enum(data, "fuel_type", FuelType)
    if fuel is None:
        raise ApiError("validation_error", "Choose petrol or diesel.", 400, {"field": "fuel_type"})
    price = parse_money(data, "price_per_litre", positive=True)
    if price > 1000:
        raise ApiError("validation_error", "That price per litre looks too high.", 400, {"field": "price_per_litre"})
    as_of = parse_date(data, "as_of") or svc.org_today(org.timezone)

    row = next(
        (p for p in FuelPrice.query.filter_by(organization_id=org_id, fuel_type=fuel) if p.city.lower() == city.lower()),
        None,
    )
    if row is None:
        row = FuelPrice(organization_id=org_id, city=city, fuel_type=fuel)
        db.session.add(row)
    old = None if row.price_per_litre is None else f"{row.price_per_litre:.2f}"
    row.price_per_litre, row.currency, row.as_of, row.updated_by = price, org.default_currency, as_of, user.id
    row.source, row.fetched_at = "manual", None
    db.session.flush()
    log_action(organization_id=org_id, actor_id=user.id, action="fuel_price.saved", entity_type="fuel_price",
               entity_id=row.id, meta={"city": city or None, "fuel_type": fuel.value, "price": [old, f"{price:.2f}"]})
    db.session.commit()
    return jsonify(price=price_to_dict(row, svc.org_today(org.timezone)))


@api_bp.delete("/fuel-prices/<int:price_id>")
@jwt_required()
def delete_fuel_price(price_id: int):
    user = current_user()
    row = db.session.get(FuelPrice, price_id)
    if row is None:
        raise ApiError("not_found", "Price not found.", 404)
    try:
        membership = get_membership(row.organization_id, user.id)
    except ApiError:
        raise ApiError("not_found", "Price not found.", 404)
    require_role(membership, *PROJECT_WRITE_ROLES)
    log_action(organization_id=row.organization_id, actor_id=user.id, action="fuel_price.deleted",
               entity_type="fuel_price", entity_id=row.id, meta={"city": row.city or None, "fuel_type": row.fuel_type.value})
    db.session.delete(row)
    db.session.commit()
    return jsonify(ok=True)
