"""Average pump prices for Morocco from the OpenVan.camp fuel price API.

https://openvan.camp/en/developers: free, no key, data under CC BY 4.0 (credit "OpenVan.camp" with a link wherever
the prices are shown). It publishes a national average per fuel, updated weekly; Moroccan prices are revised on
the 1st and 16th of each month, so right after a revision the average can be a few days behind. Prices are
averages: the pump price is what counts, and organizations can enter their own (city) prices, which win.

One request returns every country (about 200 KB). The API asks for at most one call per 10 minutes; we cache
for CACHE_HOURS and the daily update calls it once a day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

import requests
from flask import current_app

from ..extensions import db
from ..models import FuelPrice, FuelType, Organization

API_URL = "https://openvan.camp/api/fuel/prices"
BASE_URL = "https://openvan.camp/"  # linked wherever the prices are credited (CC BY 4.0)
SOURCE = "openvan"
# Rows written by any automatic source we've used; the daily update keeps them current and replaces them.
AUTO_SOURCES = (SOURCE, "teraedge")
SOURCE_LABEL = "OpenVan.camp"
LICENSE = "CC BY 4.0"
COUNTRY = "MA"
CACHE_HOURS = 6
TIMEOUT_SECONDS = 20
# Plausible pump prices in MAD per litre; anything outside is treated as bad data.
PRICE_RANGE = (Decimal("5"), Decimal("40"))

UNREACHABLE = "Couldn't reach OpenVan.camp. Try again later or enter prices by hand."
NO_PRICES = "OpenVan.camp didn't return usable prices for Morocco. Try again later or enter prices by hand."


class FuelSyncError(Exception):
    """The source couldn't be read or understood; nothing was changed."""


@dataclass
class CityPrices:
    city: str  # "" for the national average
    diesel: Optional[Decimal]
    petrol: Optional[Decimal]


@dataclass
class Snapshot:
    prices: list[CityPrices]
    fetched_at: datetime  # when we read it
    as_of: date  # the date of the source's data


_cache: Optional[Snapshot] = None


def _price(value: object) -> Optional[Decimal]:
    try:
        price = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return price if PRICE_RANGE[0] <= price <= PRICE_RANGE[1] else None


def parse(payload: dict) -> tuple[Optional[Decimal], Optional[Decimal], Optional[date]]:
    """(diesel, petrol, data date) for Morocco from the API response; None where missing or implausible."""
    country = (payload.get("data") or {}).get(COUNTRY) if payload.get("success") else None
    if not isinstance(country, dict) or country.get("is_excluded"):
        return None, None, None
    prices = country.get("prices") or {}
    currencies = country.get("currencies") or {}
    units = country.get("units") or {}

    def pick(*keys: str) -> Optional[Decimal]:
        for key in keys:
            value = prices.get(key)
            if value is None:
                continue
            if currencies.get(key, country.get("currency")) != "MAD" or units.get(key, country.get("unit")) != "liter":
                return None
            return _price(value)
        return None

    as_of = None
    for stamp in (country.get("fetched_at"), (payload.get("meta") or {}).get("updated_at")):
        try:
            as_of = datetime.fromisoformat(str(stamp).replace(" ", "T")).date()
            break
        except ValueError:
            continue
    return pick("diesel", "diesel_regular"), pick("gasoline", "gasoline_regular"), as_of


def fetch(force: bool = False) -> Snapshot:
    """Read Morocco's averages (cached for CACHE_HOURS). Raises FuelSyncError when there's nothing usable."""
    global _cache
    now = datetime.now(timezone.utc)
    if not force and _cache and (now - _cache.fetched_at).total_seconds() < CACHE_HOURS * 3600:
        return _cache
    user_agent = current_app.config.get(
        "FUEL_SYNC_USER_AGENT", "BusinessProjectAssistance/1.0 (fuel price sync; contact: site owner)"
    )
    try:
        r = requests.get(API_URL, params={"source": "business-project-assistance"},
                         headers={"User-Agent": user_agent, "Accept": "application/json"}, timeout=TIMEOUT_SECONDS)
        if r.status_code != 200:
            current_app.logger.warning("Fuel sync: %s returned HTTP %s", API_URL, r.status_code)
            raise FuelSyncError(UNREACHABLE)
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        current_app.logger.warning("Fuel sync: %s failed (%s)", API_URL, type(e).__name__)
        raise FuelSyncError(UNREACHABLE) from e
    diesel, petrol, as_of = parse(payload if isinstance(payload, dict) else {})
    if diesel is None and petrol is None:
        raise FuelSyncError(NO_PRICES)
    _cache = Snapshot([CityPrices("", diesel, petrol)], now, as_of or now.date())
    return _cache


def clear_cache() -> None:
    global _cache
    _cache = None


def apply(organization_id: int, user_id: int, snapshot: Snapshot, today=None, keep_manual: bool = False) -> int:
    """Write the snapshot into the organization's price table (source "openvan"). Returns rows written.

    The caller commits. Only for organizations whose default currency is MAD (the source's currency).
    Automatic prices for cities the snapshot doesn't cover (from the previous source) are removed, so they
    can't outrank the fresh average. keep_manual: leave prices someone typed in alone (the daily update).
    `today` is unused (kept for callers); the price date is the source's own date.
    """
    org = db.session.get(Organization, organization_id)
    if org.default_currency != "MAD":
        raise FuelSyncError(f"OpenVan.camp publishes prices in MAD; this organization uses {org.default_currency}.")
    rows = FuelPrice.query.filter_by(organization_id=organization_id).all()
    existing = {(p.city.lower(), p.fuel_type): p for p in rows}
    cities = {cp.city.lower() for cp in snapshot.prices}
    written = 0
    for cp in snapshot.prices:
        for fuel, value in ((FuelType.DIESEL, cp.diesel), (FuelType.PETROL, cp.petrol)):
            if value is None:
                continue
            row = existing.get((cp.city.lower(), fuel))
            if keep_manual and row is not None and row.source not in AUTO_SOURCES:
                continue
            if row is None:
                row = FuelPrice(organization_id=organization_id, city=cp.city, fuel_type=fuel)
                db.session.add(row)
            row.price_per_litre, row.currency, row.as_of = value, "MAD", snapshot.as_of
            row.updated_by, row.source, row.fetched_at = user_id, SOURCE, snapshot.fetched_at
            written += 1
    for row in rows:
        if row.source in AUTO_SOURCES and row.city.lower() not in cities:
            db.session.delete(row)
    return written
