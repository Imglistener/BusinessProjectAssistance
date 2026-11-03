from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import FuelPrice, FuelType
from app.services import fuel_schedule, fuel_sync

from .test_fuel_sync import fake_site  # noqa: F401  (fixture)
from .test_projects import make_org


@pytest.fixture(autouse=True)
def fresh_state():
    fuel_schedule.reset_for_tests()
    yield
    fuel_schedule.reset_for_tests()


def synced_org(client, h=None):
    """An organization that already uses the automatic prices (synced once)."""
    h, org_id = make_org(client) if h is None else h
    assert client.post(f"/api/organizations/{org_id}/fuel-prices/sync", headers=h).status_code == 200
    return h, org_id


def age_prices(hours):
    for row in FuelPrice.query.filter_by(source=fuel_sync.SOURCE):
        row.fetched_at = datetime.now(timezone.utc) - timedelta(hours=hours)
    db.session.commit()


def test_nothing_happens_while_prices_are_fresh(client, app, fake_site):  # noqa: F811
    _, calls = fake_site
    synced_org(client)
    n = len(calls)
    assert fuel_schedule.run_if_due(app) is None
    assert len(calls) == n


def test_day_old_prices_are_updated_but_typed_in_prices_stay(client, app, fake_site):  # noqa: F811
    pages, calls = fake_site
    h, org_id = synced_org(client)
    # Someone typed their own Rabat diesel price.
    r = client.put(f"/api/organizations/{org_id}/fuel-prices", headers=h,
                   json={"city": "Rabat", "fuel_type": "diesel", "price_per_litre": "13.00"})
    assert r.status_code == 200, r.get_json()
    age_prices(25)
    pages["/"] = pages["/"].replace("14,46", "14,99").replace("14.46", "14.99")

    assert fuel_schedule.run_if_due(app) == 1
    rows = {(p.city, p.fuel_type): p for p in FuelPrice.query.filter_by(organization_id=org_id)}
    assert rows[("", FuelType.DIESEL)].price_per_litre == Decimal("14.99")
    assert rows[("", FuelType.DIESEL)].fetched_at is not None
    assert rows[("Rabat", FuelType.DIESEL)].price_per_litre == Decimal("13.00")
    assert rows[("Rabat", FuelType.DIESEL)].source == "manual"
    assert fuel_schedule.run_if_due(app) is None  # fresh again


def test_organizations_that_never_synced_are_left_alone(client, app, fake_site):  # noqa: F811
    _, calls = fake_site
    make_org(client)  # MAD, but never used the automatic prices
    assert fuel_schedule.run_if_due(app) is None
    assert calls == []
    assert FuelPrice.query.count() == 0


def test_a_failed_read_waits_before_retrying(client, app, fake_site, monkeypatch):  # noqa: F811
    synced_org(client)
    age_prices(30)

    def down(force=False):
        raise fuel_sync.FuelSyncError("site down")

    monkeypatch.setattr(fuel_sync, "fetch", down)
    now = datetime.now(timezone.utc)
    assert fuel_schedule.run_if_due(app, now) is None
    attempts = []
    monkeypatch.setattr(fuel_sync, "fetch", lambda force=False: attempts.append(1) or down())
    assert fuel_schedule.run_if_due(app, now + timedelta(hours=1)) is None
    assert attempts == []  # still waiting
    fuel_schedule.run_if_due(app, now + timedelta(hours=4))
    assert attempts == [1]


def test_first_request_starts_the_thread_once(client, app, monkeypatch):
    started = []
    monkeypatch.setattr(fuel_schedule.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: started.append(kw["name"])})())
    client.get("/api/health")
    assert started == []  # disabled in tests
    app.config["FUEL_AUTO_SYNC"] = True
    client.get("/api/health")
    client.get("/api/health")
    assert started == ["fuel-auto-sync"]
