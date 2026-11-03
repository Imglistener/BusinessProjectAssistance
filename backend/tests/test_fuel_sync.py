import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import requests

from app.cli import fuel_prices_sync
from app.extensions import db
from app.models import AuditLog, FuelPrice, FuelType, Role
from app.services import fuel_sync

from .test_projects import add_member, make_org

# Trimmed real response from https://openvan.camp/api/fuel/prices (2026-11-03): Morocco plus one other country.
API = json.loads((Path(__file__).parent / "fixtures" / "openvan_prices.json").read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.fixture()
def fake_site(monkeypatch):
    """The OpenVan API, served from the fixture. Tests may edit `state["payload"]` or `state["status"]`."""
    state = {"payload": json.loads(json.dumps(API)), "status": 200, "calls": []}

    def get(url, params=None, headers=None, timeout=None):
        state["calls"].append((url, params, headers.get("User-Agent")))
        return FakeResponse(state["status"], state["payload"])

    monkeypatch.setattr(requests, "get", get)
    fuel_sync.clear_cache()
    yield state
    fuel_sync.clear_cache()


def test_parser_reads_the_real_response():
    assert fuel_sync.parse(API) == (Decimal("15.88"), Decimal("15.57"), date(2026, 10, 31))


@pytest.mark.parametrize(
    "change",
    [
        lambda ma: ma["prices"].update(diesel=1.2, gasoline=99),  # implausible
        lambda ma: ma["currencies"].update(diesel="EUR", gasoline="EUR"),  # wrong currency
        lambda ma: ma["units"].update(diesel="gallon", gasoline="gallon"),
        lambda ma: ma.update(is_excluded=True),
    ],
)
def test_parser_rejects_bad_values(change):
    payload = json.loads(json.dumps(API))
    change(payload["data"]["MA"])
    assert fuel_sync.parse(payload)[:2] == (None, None)


def test_parser_handles_missing_country_or_failure():
    assert fuel_sync.parse({"success": False}) == (None, None, None)
    assert fuel_sync.parse({"success": True, "data": {}}) == (None, None, None)


def test_sync_endpoint_writes_the_national_average_and_credits_the_source(client, fake_site):
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    prices = {(p["city"], p["fuel_type"]): p for p in body["prices"]}
    assert set(prices) == {(None, "diesel"), (None, "petrol")}
    assert prices[(None, "diesel")]["price_per_litre"] == "15.88"
    assert prices[(None, "petrol")]["price_per_litre"] == "15.57"
    assert prices[(None, "diesel")]["source"] == "openvan"
    assert prices[(None, "diesel")]["as_of"] == "2026-10-31"  # the source's date, not today
    assert body["sync"] == {"source": "OpenVan.camp", "url": "https://openvan.camp/", "license": "CC BY 4.0",
                            "available": True}
    url, params, ua = fake_site["calls"][0]
    assert url == fuel_sync.API_URL and params == {"source": "business-project-assistance"}
    assert "BusinessProjectAssistance" in ua
    assert AuditLog.query.filter_by(action="fuel_price.synced").one().meta["rows"] == 2

    # Cached: a second sync doesn't call the API again.
    client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert len(fake_site["calls"]) == 1


def test_switching_from_the_old_source_replaces_its_city_prices(client, fake_site):
    h, org_id = make_org(client)
    # Rows left by the previous source (national + a city) and a price typed in for Rabat.
    old = datetime(2026, 10, 1, tzinfo=timezone.utc)
    owner_id = client.get("/api/auth/me", headers=h).get_json()["user"]["id"]
    for city, source in (("", "teraedge"), ("Casablanca", "teraedge"), ("Rabat", "manual")):
        db.session.add(FuelPrice(organization_id=org_id, city=city, fuel_type=FuelType.DIESEL,
                                 price_per_litre=Decimal("14.00"), currency="MAD", as_of=old.date(),
                                 updated_by=owner_id, source=source, fetched_at=old if source != "manual" else None))
    db.session.commit()

    client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    rows = {(p.city, p.fuel_type): p for p in FuelPrice.query.filter_by(organization_id=org_id)}
    assert rows[("", FuelType.DIESEL)].source == "openvan"
    assert rows[("", FuelType.DIESEL)].price_per_litre == Decimal("15.88")
    assert ("Casablanca", FuelType.DIESEL) not in rows  # stale city price from the old source
    assert rows[("Rabat", FuelType.DIESEL)].price_per_litre == Decimal("14.00")  # typed in: kept


def test_manual_price_edit_marks_row_manual(client, fake_site):
    h, org_id = make_org(client)
    client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    r = client.put(f"/api/organizations/{org_id}/fuel-prices", json={"fuel_type": "diesel", "price_per_litre": "13.90"}, headers=h)
    assert r.get_json()["price"]["source"] == "manual"


def test_estimate_assumptions_credit_the_source(client, fake_site):
    h, org_id = make_org(client)
    pid = client.post(f"/api/organizations/{org_id}/projects", json={"name": "P"}, headers=h).get_json()["project"]["id"]
    client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    tid = client.post(f"/api/projects/{pid}/trips", json={"title": "T", "destination": "Rabat", "start_date": "2026-11-10",
                      "end_date": "2026-11-10", "distance_km": "90", "distance_source": "manual"}, headers=h).get_json()["trip"]["id"]
    e = client.get(f"/api/trips/{tid}/fuel-estimate", headers=h).get_json()["estimate"]
    assert any("OpenVan.camp, CC BY 4.0" in a and "2026-10-31" in a for a in e["assumptions"])
    fr = client.get(f"/api/trips/{tid}/fuel-estimate", headers={**h, "Accept-Language": "fr"}).get_json()["estimate"]
    assert any("moyenne nationale d'OpenVan.camp" in a for a in fr["assumptions"])


@pytest.mark.parametrize("failure", ["down", "http", "not json"])
def test_failures_change_nothing(client, fake_site, monkeypatch, failure):
    if failure == "down":
        def boom(*a, **k):
            raise requests.ConnectionError()
        monkeypatch.setattr(requests, "get", boom)
    elif failure == "http":
        fake_site["status"] = 503
    else:
        fake_site["payload"] = None
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "fuel_sync_failed"
    assert r.get_json()["error"]["message"] == fuel_sync.UNREACHABLE
    assert FuelPrice.query.count() == 0


def test_no_usable_prices_is_reported_in_the_users_language(client, fake_site):
    fake_site["payload"]["data"].pop("MA")
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers={**h, "Accept-Language": "fr"})
    assert r.status_code == 502 and "n'a pas renvoyé de prix utilisables" in r.get_json()["error"]["message"]


def test_permissions_and_currency(client, fake_site):
    h, org_id = make_org(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    assert client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=viewer).status_code == 403
    eur = client.post("/api/organizations", json={"name": "EU", "default_currency": "EUR"}, headers=h).get_json()["organization"]["id"]
    r = client.post(f"/api/organizations/{eur}/fuel-prices/sync", headers=h)
    assert r.status_code == 502 and "uses EUR" in r.get_json()["error"]["message"]


def test_cli_updates_all_mad_organizations(client, fake_site, app):
    make_org(client)
    make_org(client, email="b@example.com", name="B")
    result = app.test_cli_runner().invoke(fuel_prices_sync)
    assert result.exit_code == 0, result.output
    assert "Updated 2 organization(s)" in result.output
    assert FuelPrice.query.filter_by(source="openvan").count() == 4
