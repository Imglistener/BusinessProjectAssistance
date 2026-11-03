"""Average pump prices read from prix-gasoil-maroc.teraedge.ma (Prix Carburant Maroc).

The site is a free, community-reported price service. Its robots.txt allows general crawlers
(Content-Signal: ai-train=no, use=reference); we only read the published averages into the
organization's price table, credit the source wherever prices are shown, never train on them, and
keep traffic minimal: a handful of pages, one second apart, cached for CACHE_HOURS for every
organization. Prices are community-reported and indicative; the pump price is what counts.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Optional

import requests
from flask import current_app

from ..extensions import db
from ..models import FuelPrice, FuelType, Organization

BASE_URL = "https://prix-gasoil-maroc.teraedge.ma"
SOURCE = "teraedge"
SOURCE_LABEL = "prix-gasoil-maroc.teraedge.ma"
CACHE_HOURS = 6
REQUEST_GAP_SECONDS = 1.0
TIMEOUT_SECONDS = 15
# Plausible pump prices in MAD per litre; anything outside is treated as a parsing problem.
PRICE_RANGE = (Decimal("5"), Decimal("40"))

# Page path -> our city name ("" = national average, used as the default for any city).
PAGES: dict[str, str] = {
    "/": "",
    "/prix-gasoil-casablanca": "Casablanca",
    "/prix-gasoil-rabat": "Rabat",
    "/prix-gasoil-marrakech": "Marrakech",
    "/prix-gasoil-tanger": "Tangier",
    "/prix-gasoil-agadir": "Agadir",
}


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
    fetched_at: datetime


_cache: Optional[Snapshot] = None


def _text_lines(html: str) -> list[str]:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", html)
    return [unescape(line).strip() for line in text.split("\n") if line.strip()]


def _price(line: str) -> Optional[Decimal]:
    m = re.fullmatch(r"(\d{1,2}[.,]\d{1,2})(\s*(DH|MAD)(/L)?)?", line.strip(), flags=re.I)
    if not m:
        return None
    try:
        value = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return value if PRICE_RANGE[0] <= value <= PRICE_RANGE[1] else None


def parse_average(html: str) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """(diesel, petrol) from the "Moyenne ..." block: the first price after "Gazole" and after "Essence"."""
    lines = _text_lines(html)
    start = next((i for i, line in enumerate(lines) if line.lower().startswith("moyenne")), None)
    if start is None:
        return None, None
    block = lines[start : start + 20]

    def after(label: str) -> Optional[Decimal]:
        for i, line in enumerate(block):
            if line.lower() == label:
                for nxt in block[i + 1 : i + 4]:
                    price = _price(nxt)
                    if price is not None:
                        return price
        return None

    return after("gazole"), after("essence")


def _get(session: requests.Session, path: str) -> str:
    r = session.get(f"{BASE_URL}{path}", timeout=TIMEOUT_SECONDS)
    if r.status_code != 200:
        raise FuelSyncError(f"{SOURCE_LABEL} returned HTTP {r.status_code} for {path}")
    return r.text


def fetch(force: bool = False) -> Snapshot:
    """Read the averages (cached for CACHE_HOURS). Raises FuelSyncError if even the national page fails."""
    global _cache
    now = datetime.now(timezone.utc)
    if not force and _cache and now - _cache.fetched_at < timedelta(hours=CACHE_HOURS):
        return _cache

    session = requests.Session()
    session.headers["User-Agent"] = current_app.config.get(
        "FUEL_SYNC_USER_AGENT", "BusinessProjectAssistance/1.0 (fuel price sync; contact: site owner)"
    )
    prices: list[CityPrices] = []
    for n, (path, city) in enumerate(PAGES.items()):
        if n:
            time.sleep(REQUEST_GAP_SECONDS)
        try:
            diesel, petrol = parse_average(_get(session, path))
        except (requests.RequestException, FuelSyncError) as e:
            if city == "":
                raise FuelSyncError(f"Couldn't read {SOURCE_LABEL}: {type(e).__name__}") from e
            current_app.logger.warning("Fuel sync: skipped %s (%s)", path, type(e).__name__)
            continue
        if city == "" and diesel is None and petrol is None:
            raise FuelSyncError(f"The {SOURCE_LABEL} page layout changed; no prices found.")
        if diesel is not None or petrol is not None:
            prices.append(CityPrices(city, diesel, petrol))
    _cache = Snapshot(prices, now)
    return _cache


def clear_cache() -> None:
    global _cache
    _cache = None


def apply(organization_id: int, user_id: int, snapshot: Snapshot, today, keep_manual: bool = False) -> int:
    """Write the snapshot into the organization's price table (source "teraedge"). Returns rows written.

    The caller commits. Only for organizations whose default currency is MAD (the source's currency).
    keep_manual: leave prices someone typed in alone (the automatic daily update uses this).
    """
    org = db.session.get(Organization, organization_id)
    if org.default_currency != "MAD":
        raise FuelSyncError(f"{SOURCE_LABEL} publishes prices in MAD; this organization uses {org.default_currency}.")
    existing = {(p.city.lower(), p.fuel_type): p for p in FuelPrice.query.filter_by(organization_id=organization_id)}
    written = 0
    for cp in snapshot.prices:
        for fuel, value in ((FuelType.DIESEL, cp.diesel), (FuelType.PETROL, cp.petrol)):
            if value is None:
                continue
            row = existing.get((cp.city.lower(), fuel))
            if keep_manual and row is not None and row.source != SOURCE:
                continue
            if row is None:
                row = FuelPrice(organization_id=organization_id, city=cp.city, fuel_type=fuel)
                db.session.add(row)
            row.price_per_litre, row.currency, row.as_of = value, "MAD", today
            row.updated_by, row.source, row.fetched_at = user_id, SOURCE, snapshot.fetched_at
            written += 1
    return written
