from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Role
from app.services import ai_tools, metrics
from app.services.calculator import CalculationError, calculate

from .test_expenses import post_expense, setup_project
from .test_projects import add_member, make_org

CASA = (33.5731, -7.5898)
MARRAKECH = (31.6295, -7.9811)


def set_price(client, h, org_id, price="12.50", fuel="diesel", city="", as_of=None):
    body = {"city": city, "fuel_type": fuel, "price_per_litre": price}
    if as_of:
        body["as_of"] = as_of
    return client.put(f"/api/organizations/{org_id}/fuel-prices", json=body, headers=h)


def new_trip(client, h, pid, **extra):
    body = {"title": "Site visit", "destination": "Marrakech", "start_date": "2026-11-10", "end_date": "2026-11-10"}
    body.update(extra)
    return client.post(f"/api/projects/{pid}/trips", json=body, headers=h)


# ---------- calculator ----------


@pytest.mark.parametrize(
    "expr,result",
    [
        ("(12500 - 9800) / 12500 * 100", "21.6"),
        ("0.1 + 0.2", "0.3"),
        ("round(10 / 3, 2)", "3.33"),
        ("max(1, 200, 3) - min(4, 5)", "196"),
        ("2 ** 10", "1024"),
        ("-5 + abs(-7)", "2"),
        ("100", "100"),
        ("1200 × 1.2", "1440"),
    ],
)
def test_calculator(expr, result):
    assert calculate(expr) == result


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo hi')",
        "open('x')",
        "a + 1",
        "[1, 2]",
        "1 / 0",
        "9 ** 999",
        "round(1, 2, 3)",
        "1" + " + 1" * 200,
        "",
        "lambda: 1",
        "(1).real",
    ],
)
def test_calculator_refuses(expr):
    with pytest.raises(CalculationError):
        calculate(expr)


# ---------- metrics ----------


def test_straight_line_distance():
    assert Decimal("200") < metrics.straight_line_km(*CASA, *MARRAKECH) < Decimal("225")
    assert metrics.straight_line_km(*CASA, *CASA) == Decimal("0.0")


def test_fuel_estimate_by_hand():
    # 100 km one way, round trip = 200 km; 5-7 L/100km; 12.00/L; +10% distance at the top; +/-3% price.
    e = metrics.fuel_estimate("100", "5", "7", "12", round_trip=True, vehicles=1)
    assert e.distance_km == Decimal("200.0")
    assert (e.litres_low, e.litres_high) == (Decimal("10.00"), Decimal("15.40"))  # 200*5/100; 220*7/100
    assert e.litres_expected == Decimal("12.60")  # 210 * 6 / 100
    assert (e.cost_low, e.cost_expected, e.cost_high) == (Decimal("116.40"), Decimal("151.20"), Decimal("190.34"))
    two = metrics.fuel_estimate("100", "5", "7", "12", round_trip=False, vehicles=2)
    assert two.litres_low == Decimal("10.00")  # 100 km x 2 vehicles
    with pytest.raises(ValueError):
        metrics.fuel_estimate("100", "5", "7", "12", round_trip=False, vehicles=0)


def test_vat():
    assert metrics.vat("1000", "20", "add") == {"net": Decimal("1000.00"), "vat": Decimal("200.00"), "gross": Decimal("1200.00")}
    assert metrics.vat("1200", "20", "extract") == {"net": Decimal("1000.00"), "vat": Decimal("200.00"), "gross": Decimal("1200.00")}


# ---------- trip route and estimate endpoint ----------


def test_route_from_coordinates_uses_straight_line_estimate(client):
    h, org_id, pid = setup_project(client)
    t = new_trip(client, h, pid, origin="Casablanca", origin_lat=CASA[0], origin_lng=CASA[1],
                 destination_lat=MARRAKECH[0], destination_lng=MARRAKECH[1], vehicle_type="van_diesel").get_json()["trip"]
    straight = metrics.straight_line_km(*CASA, *MARRAKECH)
    assert t["route"]["distance_source"] == "straight_line"
    assert Decimal(t["route"]["distance_km"]) == (straight * Decimal("1.3")).quantize(Decimal("0.1"))
    assert t["route"]["vehicle_type"] == "van_diesel" and t["route"]["round_trip"] is True


def test_route_distance_from_map_wins(client):
    h, _, pid = setup_project(client)
    t = new_trip(client, h, pid, origin_lat=CASA[0], origin_lng=CASA[1], destination_lat=MARRAKECH[0],
                 destination_lng=MARRAKECH[1], distance_km="241.6", distance_source="route").get_json()["trip"]
    assert (t["route"]["distance_km"], t["route"]["distance_source"]) == ("241.6", "route")


def test_route_validation(client):
    h, _, pid = setup_project(client)
    assert new_trip(client, h, pid, origin_lat=91, origin_lng=0).status_code == 400
    assert new_trip(client, h, pid, vehicle_type="rocket").status_code == 400
    assert new_trip(client, h, pid, vehicle_count=0).status_code == 400
    assert new_trip(client, h, pid, distance_km="-5", distance_source="manual").status_code == 400
    assert new_trip(client, h, pid, distance_source="teleport").status_code == 400


def test_fuel_estimate_endpoint(client):
    h, org_id, pid = setup_project(client)
    set_price(client, h, org_id, "12.00", city="Casablanca")
    tid = new_trip(client, h, pid, origin="Casablanca", distance_km="100", distance_source="manual",
                   vehicle_type="sedan_diesel").get_json()["trip"]["id"]
    e = client.get(f"/api/trips/{tid}/fuel-estimate", headers=h).get_json()["estimate"]
    # 200 km round trip, 5.0-6.5 L/100 km, 12.00/L.
    assert (e["total_km"], e["litres"]["low"], e["cost"]["low"]) == ("200.0", "10.00", "116.40")
    assert e["fuel_price"]["city"] == "Casablanca" and e["warnings"] == []
    assert any("Sedan (diesel)" in a for a in e["assumptions"])

    one_way = client.get(f"/api/trips/{tid}/fuel-estimate?round_trip=false&vehicle_count=2&l_per_100km=8", headers=h).get_json()["estimate"]
    assert (one_way["total_km"], one_way["litres"]["low"], one_way["litres"]["high"]) == ("100.0", "16.00", "17.60")
    assert client.get(f"/api/trips/{tid}/fuel-estimate?l_per_100km=999", headers=h).status_code == 400


def test_fuel_estimate_missing_data_and_warnings(client):
    h, org_id, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    r = client.get(f"/api/trips/{tid}/fuel-estimate", headers=h)
    assert r.status_code == 409 and "start and finish" in r.get_json()["error"]["message"]

    client.patch(f"/api/trips/{tid}", json={"distance_km": "50", "distance_source": "manual"}, headers=h)
    r = client.get(f"/api/trips/{tid}/fuel-estimate", headers=h)
    assert r.status_code == 409 and "No diesel price" in r.get_json()["error"]["message"]

    old = (date.today() - timedelta(days=45)).isoformat()
    set_price(client, h, org_id, "12.00", as_of=old)  # default for any city, but stale
    e = client.get(f"/api/trips/{tid}/fuel-estimate", headers=h).get_json()["estimate"]
    assert e["fuel_price"]["stale"] is True and e["fuel_price"]["city"] is None
    assert any("more than 30 days old" in w for w in e["warnings"])


def test_fuel_prices_api(client):
    h, org_id, _ = setup_project(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    assert set_price(client, h, org_id, "12.10", city="Rabat").status_code == 200
    assert set_price(client, h, org_id, "12.30", city="rabat").status_code == 200  # same city, replaced
    assert set_price(client, h, org_id, "14.00", fuel="petrol").status_code == 200
    prices = client.get(f"/api/organizations/{org_id}/fuel-prices", headers=viewer).get_json()["prices"]
    assert [(p["city"], p["fuel_type"], p["price_per_litre"]) for p in prices] == [(None, "petrol", "14.00"), ("Rabat", "diesel", "12.30")]
    assert set_price(client, viewer, org_id).status_code == 403
    assert set_price(client, h, org_id, "0").status_code == 400
    assert set_price(client, h, org_id, fuel="kerosene").status_code == 400
    assert client.get(f"/api/organizations/{org_id}/fuel-prices", headers=outsider).status_code == 404
    assert client.delete(f"/api/fuel-prices/{prices[0]['id']}", headers=outsider).status_code == 404
    assert client.delete(f"/api/fuel-prices/{prices[0]['id']}", headers=h).status_code == 200


def test_reference_data(client):
    h, _, _ = setup_project(client)
    ref = client.get("/api/travel/reference", headers=h).get_json()
    assert any(v["type"] == "van_diesel" for v in ref["vehicles"]) and any(c["name"] == "Rabat" for c in ref["cities"])


# ---------- AI tools ----------


def ctx(org_id):
    return ai_tools.ToolContext(user_id=1, organization_id=org_id, today=date.today())


def test_ai_calculation_tools(client):
    h, org_id, pid = setup_project(client, "1000")
    post_expense(client, h, pid, amount="900")
    assert ai_tools.run_tool(ctx(org_id), "calculate", '{"expression": "(1000 - 900) / 1000 * 100"}')[0]["result"] == "10"
    result, _, ok = ai_tools.run_tool(ctx(org_id), "calculate", '{"expression": "__import__(\'os\')"}')
    assert not ok and "error" in result
    v = ai_tools.run_tool(ctx(org_id), "vat", '{"amount": 1200, "mode": "extract"}')[0]
    assert (v["net"], v["vat"]) == ("1000.00", "200.00")
    w = ai_tools.run_tool(ctx(org_id), "budget_what_if", f'{{"project_id": {pid}, "additional_spend": 250}}')[0]
    assert w["after"] == {"actual": "1150.00", "remaining": "-150.00", "consumed_pct": "115.00", "over_budget": True}


def test_ai_fuel_tools(client):
    h, org_id, pid = setup_project(client)
    set_price(client, h, org_id, "12.00")
    tid = new_trip(client, h, pid, distance_km="100", distance_source="manual").get_json()["trip"]["id"]
    trip = ai_tools.run_tool(ctx(org_id), "estimate_trip_fuel_cost", f'{{"trip_id": {tid}}}')[0]
    assert trip["cost"]["low"] == "116.40" and trip["title"] == "Site visit"
    hypo = ai_tools.run_tool(ctx(org_id), "estimate_fuel_cost", '{"from_city": "Casablanca", "to_city": "Rabat", "vehicle_type": "van_diesel"}')[0]
    assert hypo["distance_source"] == "straight_line" and Decimal(hypo["one_way_km"]) > Decimal("100")
    bad, _, ok = ai_tools.run_tool(ctx(org_id), "estimate_fuel_cost", '{"from_city": "Atlantis", "to_city": "Rabat"}')
    assert not ok and "known cities" in bad["error"]
    # A trip in another organization can't be reached.
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    other_pid = client.post(f"/api/organizations/{other_org}/projects", json={"name": "X"}, headers=other_h).get_json()["project"]["id"]
    other_tid = new_trip(client, other_h, other_pid, distance_km="10", distance_source="manual").get_json()["trip"]["id"]
    res, _, ok = ai_tools.run_tool(ctx(org_id), "estimate_trip_fuel_cost", f'{{"trip_id": {other_tid}}}')
    assert not ok and res == {"error": "Project not found or not accessible."}
