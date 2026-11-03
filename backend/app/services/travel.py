"""Reference data and lookups for trip fuel estimates. The arithmetic itself lives in services.metrics.

Consumption figures are typical real-world ranges (litres per 100 km, mixed driving) for common vehicle
classes; they are planning figures, not manufacturer specs. Users can override them per trip.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from ..extensions import db
from ..models import FuelPrice, FuelType, Organization
from . import metrics
from .projects import org_today

# Straight-line distance x this factor approximates road distance when no route is available.
ROAD_FACTOR = Decimal("1.3")
STALE_PRICE_DAYS = 30


@dataclass(frozen=True)
class VehicleProfile:
    key: str
    label: str
    fuel: FuelType
    l_per_100km_low: Decimal
    l_per_100km_high: Decimal


VEHICLES: dict[str, VehicleProfile] = {
    v.key: v
    for v in (
        VehicleProfile("motorcycle", "Motorcycle / scooter", FuelType.PETROL, Decimal("2.5"), Decimal("4.0")),
        VehicleProfile("small_car_petrol", "Small car (petrol)", FuelType.PETROL, Decimal("5.0"), Decimal("6.5")),
        VehicleProfile("small_car_diesel", "Small car (diesel)", FuelType.DIESEL, Decimal("4.0"), Decimal("5.5")),
        VehicleProfile("sedan_petrol", "Sedan (petrol)", FuelType.PETROL, Decimal("6.5"), Decimal("8.5")),
        VehicleProfile("sedan_diesel", "Sedan (diesel)", FuelType.DIESEL, Decimal("5.0"), Decimal("6.5")),
        VehicleProfile("suv_petrol", "SUV (petrol)", FuelType.PETROL, Decimal("8.0"), Decimal("11.0")),
        VehicleProfile("suv_diesel", "SUV (diesel)", FuelType.DIESEL, Decimal("6.5"), Decimal("8.5")),
        VehicleProfile("van_diesel", "Van (diesel)", FuelType.DIESEL, Decimal("7.5"), Decimal("10.0")),
        VehicleProfile("pickup_diesel", "Pickup (diesel)", FuelType.DIESEL, Decimal("8.0"), Decimal("11.0")),
        VehicleProfile("minibus_diesel", "Minibus (diesel)", FuelType.DIESEL, Decimal("10.0"), Decimal("14.0")),
    )
}
DEFAULT_VEHICLE = "sedan_diesel"

# Approximate city-centre coordinates, for picking places without a map key.
CITIES: dict[str, tuple[float, float]] = {
    "Agadir": (30.4278, -9.5981),
    "Beni Mellal": (32.3373, -6.3498),
    "Casablanca": (33.5731, -7.5898),
    "Dakhla": (23.6848, -15.9580),
    "El Jadida": (33.2316, -8.5007),
    "Essaouira": (31.5085, -9.7595),
    "Fes": (34.0181, -5.0078),
    "Kenitra": (34.2610, -6.5802),
    "Laayoune": (27.1253, -13.1625),
    "Marrakech": (31.6295, -7.9811),
    "Meknes": (33.8935, -5.5473),
    "Nador": (35.1740, -2.9287),
    "Ouarzazate": (30.9189, -6.8934),
    "Oujda": (34.6814, -1.9086),
    "Rabat": (34.0209, -6.8416),
    "Safi": (32.2994, -9.2372),
    "Tangier": (35.7595, -5.8340),
    "Tetouan": (35.5785, -5.3684),
}


def city_for(place: Optional[str]) -> Optional[str]:
    """The known city named in a place label ("Casa Port, Casablanca" -> "Casablanca"), if any."""
    if not place:
        return None
    lowered = place.lower()
    for name in CITIES:
        if name.lower() in lowered:
            return name
    return None


@dataclass
class PriceLookup:
    price: Optional[FuelPrice]
    matched_city: Optional[str]  # None when the organization default ("any city") was used
    stale: bool


def fuel_price(organization_id: int, city: Optional[str], fuel: FuelType, today: date) -> PriceLookup:
    rows = FuelPrice.query.filter_by(organization_id=organization_id, fuel_type=fuel).all()
    by_city = {r.city.lower(): r for r in rows}
    row = by_city.get((city or "").lower()) if city else None
    matched = row.city if row else None
    if row is None:
        row = by_city.get("")
    stale = row is not None and (today - row.as_of).days > STALE_PRICE_DAYS
    return PriceLookup(row, matched, stale)


class EstimateUnavailable(ValueError):
    """Data the estimate needs is missing; the message says what to add."""


def _m(v) -> Optional[str]:
    return None if v is None else f"{Decimal(v):.2f}"


def estimate_fuel(
    *,
    organization_id: int,
    currency: str,
    one_way_km,
    distance_source: str,
    vehicle_type: Optional[str],
    vehicle_count: int,
    round_trip: bool,
    city: Optional[str],
    today: date,
    l_per_100km: Optional[Decimal] = None,
    distance_variance_pct: Decimal = Decimal("10"),
) -> dict:
    """A fuel cost range with every input and assumption spelled out, for the UI and the assistant."""
    if one_way_km is None or Decimal(one_way_km) <= 0:
        raise EstimateUnavailable("Set the trip's start and finish (or the distance) first.")
    profile = VEHICLES.get(vehicle_type or DEFAULT_VEHICLE)
    if profile is None:
        raise EstimateUnavailable(f"Unknown vehicle type '{vehicle_type}'.")
    lookup = fuel_price(organization_id, city, profile.fuel, today)
    if lookup.price is None:
        raise EstimateUnavailable(
            f"No {profile.fuel.value} price is set for {city}. Add one under Settings, Fuel prices."
            if city
            else f"No {profile.fuel.value} price is set for this organization. Add one under Settings, Fuel prices."
        )
    low, high = (l_per_100km, l_per_100km) if l_per_100km else (profile.l_per_100km_low, profile.l_per_100km_high)
    est = metrics.fuel_estimate(
        one_way_km, low, high, lookup.price.price_per_litre,
        round_trip=round_trip, vehicles=vehicle_count, distance_variance_pct=distance_variance_pct,
    )
    source_label = {
        "route": "road route from the map",
        "straight_line": f"straight-line distance x {ROAD_FACTOR} (no road route available)",
        "manual": "distance entered by hand",
    }.get(distance_source, distance_source)
    price_city = lookup.matched_city or "organization default (no price for this city)"
    km = f"{Decimal(one_way_km):.1f}"
    price = f"{_m(lookup.price.price_per_litre)} {lookup.price.currency}"
    as_of = lookup.price.as_of.isoformat()
    fuel = profile.fuel.value
    # Whole sentences (no fragments glued together) so each one can be translated (see app/i18n.py).
    assumptions = [
        f"Distance: {km} km one way ({source_label}), driven both ways."
        if round_trip
        else f"Distance: {km} km one way ({source_label}).",
        f"Vehicle: {profile.label}, {low}-{high} L/100 km (your figure)."
        if l_per_100km
        else f"Vehicle: {profile.label}, {low}-{high} L/100 km (typical range).",
        "1 vehicle." if vehicle_count == 1 else f"{vehicle_count} vehicles.",
        f"Fuel: {fuel} at {price}/L ({price_city}, as of {as_of}, national average from OpenVan.camp, CC BY 4.0), "
        "+/-3% for station differences."
        if lookup.price.source == "openvan"
        else f"Fuel: {fuel} at {price}/L ({price_city}, as of {as_of}, average from prix-gasoil-maroc.teraedge.ma), "
        "+/-3% for station differences."
        if lookup.price.source == "teraedge"  # rows from the previous source, until the next update
        else f"Fuel: {fuel} at {price}/L ({price_city}, as of {as_of}, entered by your team), +/-3% for station differences.",
        f"Up to {distance_variance_pct}% extra distance for detours and traffic in the high estimate.",
    ]
    warnings = []
    if lookup.stale:
        warnings.append(f"The fuel price is more than {STALE_PRICE_DAYS} days old; update it for a better estimate.")
    if distance_source == "straight_line":
        warnings.append("The distance is a straight-line approximation; real road distance may differ.")
    if lookup.price.currency != currency:
        warnings.append(f"The fuel price is in {lookup.price.currency} but the project uses {currency}.")
    return {
        "currency": lookup.price.currency,
        "vehicle": {"type": profile.key, "label": profile.label, "fuel": profile.fuel.value,
                    "l_per_100km_low": str(low), "l_per_100km_high": str(high)},
        "vehicle_count": vehicle_count,
        "round_trip": round_trip,
        "one_way_km": f"{Decimal(one_way_km):.1f}",
        "total_km": f"{est.distance_km:.1f}",
        "distance_source": distance_source,
        "fuel_price": {"price_per_litre": _m(lookup.price.price_per_litre), "city": lookup.matched_city,
                       "as_of": lookup.price.as_of.isoformat(), "stale": lookup.stale},
        "litres": {"low": _m(est.litres_low), "expected": _m(est.litres_expected), "high": _m(est.litres_high)},
        "cost": {"low": _m(est.cost_low), "expected": _m(est.cost_expected), "high": _m(est.cost_high)},
        "assumptions": assumptions,
        "warnings": warnings,
    }


def estimate_for_trip(trip, project, overrides: dict) -> dict:
    """Shared by the trip endpoint and the assistant tool. Raises EstimateUnavailable when data is missing."""
    org = db.session.get(Organization, project.organization_id)
    vehicle_type = overrides.get("vehicle_type") or trip.vehicle_type
    count = overrides.get("vehicle_count") or trip.vehicle_count or 1
    round_trip = overrides["round_trip"] if overrides.get("round_trip") is not None else (
        True if trip.round_trip is None else trip.round_trip
    )
    city = overrides.get("fuel_city") or trip.fuel_city or city_for(trip.origin) or city_for(trip.destination)
    return estimate_fuel(
        organization_id=project.organization_id,
        currency=project.currency,
        one_way_km=trip.distance_km,
        distance_source=trip.distance_source or "manual",
        vehicle_type=vehicle_type,
        vehicle_count=count,
        round_trip=round_trip,
        city=city,
        today=org_today(org.timezone),
        l_per_100km=overrides.get("l_per_100km"),
        distance_variance_pct=overrides.get("distance_variance_pct", Decimal("10")),
    )
