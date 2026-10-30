from decimal import Decimal
from pathlib import Path

import pytest
import requests

from app.cli import fuel_prices_sync
from app.models import AuditLog, FuelPrice, Role
from app.services import fuel_sync

from .test_projects import add_member, make_org

FIXTURES = Path(__file__).parent / "fixtures"
HOME = (FIXTURES / "teraedge_home.html").read_text(encoding="utf-8")
CASA = (FIXTURES / "teraedge_casablanca.html").read_text(encoding="utf-8")


def city_page(diesel, petrol, city="Rabat"):
    return f"""<h3>Moyenne à {city}</h3><div><span>Gazole</span><span>{diesel}</span><span>DH</span>
    <span>Essence</span><span>{petrol}</span><span>DH</span></div>"""


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


@pytest.fixture()
def fake_site(monkeypatch):
    pages = {"/": HOME, "/prix-gasoil-casablanca": CASA, "/prix-gasoil-rabat": city_page("14,52", "15.44")}
    calls = []

    def get(self, url, timeout):
        path = url.replace(fuel_sync.BASE_URL, "") or "/"
        calls.append((path, self.headers.get("User-Agent")))
        return FakeResponse(200, pages[path]) if path in pages else FakeResponse(404)

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(fuel_sync, "REQUEST_GAP_SECONDS", 0)
    fuel_sync.clear_cache()
    yield pages, calls
    fuel_sync.clear_cache()


def test_parser_reads_the_real_pages():
    assert fuel_sync.parse_average(HOME) == (Decimal("14.46"), Decimal("15.39"))
    assert fuel_sync.parse_average(CASA) == (Decimal("14.46"), Decimal("15.39"))
    assert fuel_sync.parse_average(city_page("14,52", "15.44")) == (Decimal("14.52"), Decimal("15.44"))


def test_parser_rejects_implausible_or_missing_values():
    assert fuel_sync.parse_average(city_page("1.20", "99.00")) == (None, None)
    assert fuel_sync.parse_average("<p>Nothing here</p>") == (None, None)


def test_sync_endpoint_writes_prices_and_credits_source(client, fake_site, app):
    _, calls = fake_site
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert r.status_code == 200, r.get_json()
    prices = {(p["city"], p["fuel_type"]): p for p in r.get_json()["prices"]}
    assert prices[(None, "diesel")]["price_per_litre"] == "14.46"
    assert prices[("Rabat", "petrol")]["price_per_litre"] == "15.44"
    assert prices[("Casablanca", "diesel")]["source"] == "teraedge"
    assert ("Tangier", "diesel") not in prices  # 404: skipped, not fatal
    assert all("BusinessProjectAssistance" in ua for _, ua in calls)
    assert AuditLog.query.filter_by(action="fuel_price.synced").one().meta["rows"] == 6

    # Cached: a second sync doesn't hit the site again.
    n = len(calls)
    client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert len(calls) == n


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
    assert any("prix-gasoil-maroc.teraedge.ma" in a for a in e["assumptions"])


def test_site_down_changes_nothing(client, monkeypatch):
    def boom(self, url, timeout):
        raise requests.ConnectionError()

    monkeypatch.setattr(requests.Session, "get", boom)
    fuel_sync.clear_cache()
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "fuel_sync_failed"
    assert FuelPrice.query.count() == 0


def test_layout_change_is_detected(client, fake_site):
    pages, _ = fake_site
    pages["/"] = "<html><body>Redesigned</body></html>"
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h)
    assert r.status_code == 502 and "layout changed" in r.get_json()["error"]["message"]


def test_permissions_and_currency(client, fake_site):
    h, org_id = make_org(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    assert client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=viewer).status_code == 403
    eur = client.post("/api/organizations", json={"name": "EU", "default_currency": "EUR"}, headers=h).get_json()["organization"]["id"]
    r = client.post(f"/api/organizations/{eur}/fuel-prices/sync", headers=h)
    assert r.status_code == 502 and "MAD" in r.get_json()["error"]["message"]


def test_cli_updates_all_mad_organizations(client, fake_site, app):
    make_org(client)
    make_org(client, email="b@example.com", name="B")
    result = app.test_cli_runner().invoke(fuel_prices_sync)
    assert result.exit_code == 0, result.output
    assert "Updated 2 organization(s)" in result.output
    assert FuelPrice.query.filter_by(source="teraedge").count() == 12
