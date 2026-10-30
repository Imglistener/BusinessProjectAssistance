from decimal import Decimal

from app.extensions import db
from app.models import AuditLog, InventoryItem, InventoryMovement, Role
from app.services import metrics

from .test_projects import add_member, create_project, make_org


def add_item(client, h, org_id, **overrides):
    body = {"name": "Cement bag 50kg", "unit": "bag", "unit_cost": "75.00", "reorder_level": "10", "quantity": "40"}
    body.update(overrides)
    return client.post(f"/api/organizations/{org_id}/inventory", json=body, headers=h)


def move(client, h, item_id, kind, quantity, **extra):
    return client.post(f"/api/inventory/{item_id}/movements", json={"kind": kind, "quantity": quantity, **extra}, headers=h)


def listing(client, h, org_id, query=""):
    return client.get(f"/api/organizations/{org_id}/inventory{query}", headers=h).get_json()


def test_create_with_opening_stock_and_value(client):
    h, org_id = make_org(client)
    r = add_item(client, h, org_id)
    assert r.status_code == 201
    item = r.get_json()["item"]
    assert (item["quantity_on_hand"], item["stock_value"], item["currency"], item["low_stock"]) == ("40.00", "3000.00", "MAD", False)
    [m] = InventoryMovement.query.all()
    assert (m.kind.value, m.quantity_delta, m.note) == ("count", Decimal("40.00"), "Opening stock")


def test_receive_issue_adjust_and_history(client):
    h, org_id = make_org(client)
    iid = add_item(client, h, org_id).get_json()["item"]["id"]
    assert move(client, h, iid, "receive", "10").get_json()["item"]["quantity_on_hand"] == "50.00"
    assert move(client, h, iid, "issue", "42.5").get_json()["item"]["quantity_on_hand"] == "7.50"
    r = move(client, h, iid, "adjust", "-1.5", note="Two bags torn")
    assert r.get_json()["item"]["quantity_on_hand"] == "6.00" and r.get_json()["item"]["low_stock"] is True

    hist = client.get(f"/api/inventory/{iid}/movements", headers=h).get_json()
    assert [(m["kind"], m["quantity_delta"], m["quantity_after"]) for m in hist["movements"]] == [
        ("adjust", "-1.50", "6.00"), ("issue", "-42.50", "7.50"), ("receive", "10.00", "50.00"), ("count", "40.00", "40.00"),
    ]
    assert hist["movements"][0]["created_by"] == "Alex Doe"


def test_cannot_issue_more_than_on_hand(client):
    h, org_id = make_org(client)
    iid = add_item(client, h, org_id, quantity="5").get_json()["item"]["id"]
    r = move(client, h, iid, "issue", "6")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "insufficient_stock"
    assert "Only 5.00 bag on hand" in r.get_json()["error"]["message"]
    assert move(client, h, iid, "adjust", "-6", note="x").status_code == 409


def test_movement_validation(client):
    h, org_id = make_org(client)
    iid = add_item(client, h, org_id).get_json()["item"]["id"]
    for kind, qty in [("receive", "0"), ("receive", "-2"), ("issue", "abc"), ("receive", "1.234"), ("teleport", "1")]:
        assert move(client, h, iid, kind, qty).status_code == 400, (kind, qty)
    assert move(client, h, iid, "adjust", "3").status_code == 400  # needs a reason
    assert client.patch(f"/api/inventory/{iid}", json={"quantity_on_hand": "999"}, headers=h).status_code == 400


def test_issue_to_project_shows_in_materials_and_activity(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    iid = add_item(client, h, org_id).get_json()["item"]["id"]
    assert move(client, h, iid, "issue", "4", project_id=pid).status_code == 201
    move(client, h, iid, "issue", "2", project_id=pid)
    mats = client.get(f"/api/projects/{pid}/materials", headers=h).get_json()
    assert mats["materials"] == [{"item_id": iid, "name": "Cement bag 50kg", "unit": "bag", "quantity": "6.00", "value": "450.00"}]
    assert mats["total_value"] == "450.00"
    acts = client.get(f"/api/projects/{pid}/activity", headers=h).get_json()["entries"]
    assert acts[0]["action"] == "inventory.issue" and acts[0]["meta"]["item"] == "Cement bag 50kg"

    other_org_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    foreign = create_project(client, other_org_h, other_org).get_json()["project"]["id"]
    assert move(client, h, iid, "issue", "1", project_id=foreign).status_code == 400


def test_stock_count_sets_quantities_and_reports_differences(client):
    h, org_id = make_org(client)
    a = add_item(client, h, org_id).get_json()["item"]["id"]
    b = add_item(client, h, org_id, name="Paint 20L", unit="tin", unit_cost="300", quantity="8").get_json()["item"]["id"]
    r = client.post(
        f"/api/organizations/{org_id}/inventory/counts",
        json={"counts": [{"item_id": a, "counted": "37"}, {"item_id": b, "counted": "8"}], "note": "Monthly count"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert [(x["name"], x["expected"], x["counted"], x["difference"]) for x in body["results"]] == [
        ("Cement bag 50kg", "40.00", "37.00", "-3.00"), ("Paint 20L", "8.00", "8.00", "0.00"),
    ]
    assert body["changed_count"] == 1 and body["value_change"] == "-225.00"
    assert db.session.get(InventoryItem, a).quantity_on_hand == Decimal("37.00")
    # Unchanged items get no movement.
    assert InventoryMovement.query.filter_by(item_id=b).count() == 1


def test_count_validation(client):
    h, org_id = make_org(client)
    a = add_item(client, h, org_id).get_json()["item"]["id"]
    url = f"/api/organizations/{org_id}/inventory/counts"
    assert client.post(url, json={"counts": []}, headers=h).status_code == 400
    assert client.post(url, json={"counts": [{"item_id": a, "counted": "1"}, {"item_id": a, "counted": "2"}]}, headers=h).status_code == 400
    assert client.post(url, json={"counts": [{"item_id": a, "counted": "-1"}]}, headers=h).status_code == 400
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    foreign = add_item(client, other_h, other_org).get_json()["item"]["id"]
    assert client.post(url, json={"counts": [{"item_id": foreign, "counted": "0"}]}, headers=h).status_code == 400


def test_list_search_low_stock_and_summary(client):
    h, org_id = make_org(client)
    add_item(client, h, org_id)
    add_item(client, h, org_id, name="Screws box", sku="SCR-100", unit_cost=None, quantity="2", reorder_level="5", location="Shelf B")
    old = add_item(client, h, org_id, name="Old drill", quantity="1").get_json()["item"]["id"]
    client.patch(f"/api/inventory/{old}", json={"archived": True}, headers=h)

    body = listing(client, h, org_id)
    assert [i["name"] for i in body["items"]] == ["Cement bag 50kg", "Screws box"]
    assert body["summary"] == {"item_count": 2, "low_stock_count": 1, "stock_value": "3000.00", "unpriced_item_count": 1, "currency": "MAD"}
    assert [i["name"] for i in listing(client, h, org_id, "?low_stock=true")["items"]] == ["Screws box"]
    assert [i["name"] for i in listing(client, h, org_id, "?q=scr-1")["items"]] == ["Screws box"]
    assert [i["name"] for i in listing(client, h, org_id, "?q=shelf")["items"]] == ["Screws box"]
    assert len(listing(client, h, org_id, "?include_archived=true")["items"]) == 3
    assert move(client, h, old, "receive", "1").status_code == 409


def test_permissions(client):
    h, org_id = make_org(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    iid = add_item(client, h, org_id).get_json()["item"]["id"]

    assert add_item(client, contributor, org_id).status_code == 403
    assert move(client, contributor, iid, "receive", "1").status_code == 201
    assert move(client, contributor, iid, "issue", "1").status_code == 201
    assert move(client, contributor, iid, "adjust", "1", note="found").status_code == 403
    assert client.patch(f"/api/inventory/{iid}", json={"name": "x"}, headers=contributor).status_code == 403
    assert move(client, viewer, iid, "receive", "1").status_code == 403
    assert listing(client, viewer, org_id)["items"][0]["id"] == iid
    assert client.get(f"/api/organizations/{org_id}/inventory", headers=outsider).status_code == 404
    assert move(client, outsider, iid, "receive", "1").status_code == 404
    assert client.get(f"/api/inventory/{iid}/movements", headers=outsider).status_code == 404


def test_edit_is_audited(client):
    h, org_id = make_org(client)
    iid = add_item(client, h, org_id).get_json()["item"]["id"]
    client.patch(f"/api/inventory/{iid}", json={"unit_cost": "80", "location": "Yard"}, headers=h)
    entry = AuditLog.query.filter_by(action="inventory.item_updated").one()
    assert entry.meta == {"unit_cost": ["75.00", "80.00"], "location": "changed"}


def test_stock_metrics():
    assert metrics.stock_value("2.5", "10.10") == Decimal("25.25")
    assert metrics.stock_value("3", None) is None
    assert metrics.is_low_stock("5", "5") is True
    assert metrics.is_low_stock("6", "5") is False
    assert metrics.is_low_stock("0", None) is False


def test_ai_inventory_tool(client):
    from app.services import ai_tools
    from datetime import date

    h, org_id = make_org(client)
    add_item(client, h, org_id, quantity="3")  # below reorder level 10
    add_item(client, h, org_id, name="Gloves", unit_cost=None, quantity="50", reorder_level=None)
    ctx = ai_tools.ToolContext(user_id=1, organization_id=org_id, today=date(2026, 10, 30))
    r = ai_tools.get_inventory_status(ctx, {})
    assert (r["item_count"], r["stock_value"], r["unpriced_item_count"], r["currency"]) == (2, "225.00", 1, "MAD")
    assert [i["name"] for i in r["low_stock"]] == ["Cement bag 50kg"]
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    add_item(client, other_h, other_org, name="Secret stock")
    assert "Secret stock" not in str(r)
