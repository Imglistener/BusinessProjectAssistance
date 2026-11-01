"""Project inventories, warehouses, stock per warehouse, transfers and moves between inventories."""
from app.extensions import db
from app.models import AuditLog, InventoryItem, InventoryMovement, InventoryStock, Role, Warehouse

from .test_projects import add_member, create_project, make_org


def setup(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, name="Office move").get_json()["project"]["id"]
    return h, org_id, pid


def new_item(client, h, org_id, **body):
    data = {"name": "Office chair", "unit": "pcs", "unit_cost": "100", **body}
    r = client.post(f"/api/organizations/{org_id}/inventory", json=data, headers=h)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["item"]


def new_warehouse(client, h, org_id, **body):
    data = {"name": "Casablanca depot", "address": "Ain Sebaa, Casablanca", "lat": 33.6, "lng": -7.53, **body}
    r = client.post(f"/api/organizations/{org_id}/warehouses", json=data, headers=h)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["warehouse"]


def listing(client, h, org_id, scope="general"):
    return client.get(f"/api/organizations/{org_id}/inventory?scope={scope}", headers=h).get_json()


def move(client, h, item_id, **body):
    return client.post(f"/api/inventory/{item_id}/movements", json=body, headers=h)


def item_stock(client, h, org_id, item_id, scope):
    return next(i for i in listing(client, h, org_id, scope)["items"] if i["id"] == item_id)


# ---------- inventories ----------


def test_each_project_has_its_own_inventory(client):
    h, org_id, pid = setup(client)
    general = new_item(client, h, org_id, name="Printer paper", quantity="10")
    mine = new_item(client, h, org_id, name="Desk", quantity="4", project_id=pid)
    assert mine["project_id"] == pid and general["project_id"] is None
    assert [i["name"] for i in listing(client, h, org_id)["items"]] == ["Printer paper"]
    project_list = listing(client, h, org_id, pid)
    assert [i["name"] for i in project_list["items"]] == ["Desk"]
    assert project_list["scope"] == {"project_id": pid, "project_name": "Office move"}
    assert project_list["summary"]["stock_value"] == "400.00"
    assert len(listing(client, h, org_id, "all")["items"]) == 2
    s = client.get(f"/api/projects/{pid}/inventory-summary", headers=h).get_json()["summary"]
    assert (s["item_count"], s["stock_value"], s["warehouse_count"]) == (1, "400.00", 0)


def test_scope_must_be_one_of_the_organizations_projects(client):
    h, org_id, pid = setup(client)
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    theirs = create_project(client, other_h, other_org).get_json()["project"]["id"]
    assert client.get(f"/api/organizations/{org_id}/inventory?scope={theirs}", headers=h).status_code == 404
    assert client.get(f"/api/organizations/{org_id}/inventory?scope=nonsense", headers=h).status_code == 400
    r = client.post(f"/api/organizations/{org_id}/inventory", json={"name": "X", "project_id": theirs}, headers=h)
    assert r.status_code == 400
    client.post(f"/api/projects/{pid}/archive", headers=h)
    r = client.post(f"/api/organizations/{org_id}/inventory", json={"name": "X", "project_id": pid}, headers=h)
    assert r.status_code == 409


def test_issuing_from_a_project_inventory_counts_as_its_materials(client):
    h, org_id, pid = setup(client)
    desk = new_item(client, h, org_id, name="Desk", quantity="4", project_id=pid)
    assert move(client, h, desk["id"], kind="issue", quantity="1").status_code == 201
    materials = client.get(f"/api/projects/{pid}/materials", headers=h).get_json()["materials"]
    assert [(m["name"], m["quantity"]) for m in materials] == [("Desk", "1.00")]


# ---------- warehouses ----------


def test_warehouse_crud_and_scope(client):
    h, org_id, pid = setup(client)
    w = new_warehouse(client, h, org_id, project_id=pid)
    assert (w["project_id"], w["lat"], w["lng"], w["item_count"]) == (pid, 33.6, -7.53, 0)
    company = new_warehouse(client, h, org_id, name="Head office store")
    listed = client.get(f"/api/organizations/{org_id}/warehouses?scope={pid}", headers=h).get_json()["warehouses"]
    assert [x["name"] for x in listed] == ["Casablanca depot"]
    assert [x["name"] for x in listing(client, h, org_id)["warehouses"]] == ["Head office store"]
    r = client.patch(f"/api/warehouses/{w['id']}", json={"name": "Ain Sebaa depot", "lat": None, "lng": None}, headers=h)
    assert r.status_code == 200 and (r.get_json()["warehouse"]["name"], r.get_json()["warehouse"]["lat"]) == ("Ain Sebaa depot", None)
    for bad in ({"name": ""}, {"lat": 33}, {"lat": 120, "lng": 0}, {"lat": "x", "lng": 1}):
        assert client.patch(f"/api/warehouses/{w['id']}", json=bad, headers=h).status_code == 400, bad
    assert client.delete(f"/api/warehouses/{company['id']}", headers=h).status_code == 200
    assert AuditLog.query.filter_by(action="warehouse.deleted").count() == 1


def test_stock_per_warehouse(client):
    h, org_id, pid = setup(client)
    a = new_warehouse(client, h, org_id, name="Casablanca", project_id=pid)
    b = new_warehouse(client, h, org_id, name="Tangier", project_id=pid)
    chair = new_item(client, h, org_id, quantity="20", warehouse_id=a["id"], project_id=pid)
    assert chair["stock"] == [{"warehouse_id": a["id"], "warehouse": "Casablanca", "quantity": "20.00"}]
    assert chair["not_in_warehouse"] == "0.00"
    assert move(client, h, chair["id"], kind="receive", quantity="5", warehouse_id=b["id"]).status_code == 201
    assert move(client, h, chair["id"], kind="receive", quantity="2").status_code == 201  # not in a warehouse
    got = item_stock(client, h, org_id, chair["id"], pid)
    assert got["quantity_on_hand"] == "27.00" and got["not_in_warehouse"] == "2.00"
    assert {s["warehouse"]: s["quantity"] for s in got["stock"]} == {"Casablanca": "20.00", "Tangier": "5.00"}
    # Taking more than a place holds is refused, with the place named.
    r = move(client, h, chair["id"], kind="issue", quantity="6", warehouse_id=b["id"])
    assert r.status_code == 409 and r.get_json()["error"]["message"] == "Only 5.00 pcs in Tangier."
    r = move(client, h, chair["id"], kind="issue", quantity="3")
    assert r.status_code == 409 and "Choose the warehouse" in r.get_json()["error"]["message"]
    assert move(client, h, chair["id"], kind="issue", quantity="3", warehouse_id=a["id"]).status_code == 201
    # A warehouse from another inventory can't be used.
    other = new_warehouse(client, h, org_id, name="Elsewhere")
    assert move(client, h, chair["id"], kind="receive", quantity="1", warehouse_id=other["id"]).status_code == 400
    contents = {w["name"]: w for w in listing(client, h, org_id, pid)["warehouses"]}
    assert (contents["Casablanca"]["units"], contents["Casablanca"]["value"]) == ("17.00", "1700.00")


def test_transfers_between_warehouses(client):
    h, org_id, pid = setup(client)
    a = new_warehouse(client, h, org_id, name="Casablanca", project_id=pid)
    b = new_warehouse(client, h, org_id, name="Tangier", project_id=pid)
    chair = new_item(client, h, org_id, quantity="10", warehouse_id=a["id"], project_id=pid)
    url = f"/api/inventory/{chair['id']}/transfers"
    r = client.post(url, json={"quantity": "4", "from_warehouse_id": a["id"], "to_warehouse_id": b["id"]}, headers=h)
    assert r.status_code == 201
    assert r.get_json()["item"]["quantity_on_hand"] == "10.00"
    assert {s["warehouse"]: s["quantity"] for s in r.get_json()["item"]["stock"]} == {"Casablanca": "6.00", "Tangier": "4.00"}
    assert (r.get_json()["movement"]["warehouse"], r.get_json()["movement"]["to_warehouse"]) == ("Casablanca", "Tangier")
    r = client.post(url, json={"quantity": "1", "from_warehouse_id": b["id"], "to_warehouse_id": None}, headers=h)
    assert r.status_code == 201 and r.get_json()["item"]["not_in_warehouse"] == "1.00"
    assert client.post(url, json={"quantity": "50", "from_warehouse_id": a["id"], "to_warehouse_id": b["id"]}, headers=h).status_code == 409
    assert client.post(url, json={"quantity": "1", "from_warehouse_id": a["id"], "to_warehouse_id": a["id"]}, headers=h).status_code == 400


def test_counts_per_warehouse(client):
    h, org_id, pid = setup(client)
    a = new_warehouse(client, h, org_id, name="Casablanca", project_id=pid)
    chair = new_item(client, h, org_id, quantity="10", warehouse_id=a["id"], project_id=pid)
    move(client, h, chair["id"], kind="receive", quantity="3")
    r = client.post(f"/api/organizations/{org_id}/inventory/counts", json={"counts": [
        {"item_id": chair["id"], "warehouse_id": a["id"], "counted": "8"},
        {"item_id": chair["id"], "counted": "3"},
    ]}, headers=h)
    assert r.status_code == 200, r.get_json()
    assert [(x["warehouse"], x["expected"], x["difference"]) for x in r.get_json()["results"]] == [
        ("Casablanca", "10.00", "-2.00"), (None, "3.00", "0.00"),
    ]
    assert item_stock(client, h, org_id, chair["id"], pid)["quantity_on_hand"] == "11.00"


def test_moving_stock_between_inventories(client):
    h, org_id, pid = setup(client)
    depot = new_warehouse(client, h, org_id, name="Site store", project_id=pid)
    paper = new_item(client, h, org_id, name="Printer paper", unit="box", quantity="30")
    url = f"/api/inventory/{paper['id']}/move"
    r = client.post(url, json={"to_project_id": pid, "quantity": "12", "to_warehouse_id": depot["id"]}, headers=h)
    assert r.status_code == 201, r.get_json()
    target = r.get_json()["target"]
    assert (target["project_id"], target["name"], target["quantity_on_hand"]) == (pid, "Printer paper", "12.00")
    assert target["stock"][0]["warehouse"] == "Site store"
    assert r.get_json()["item"]["quantity_on_hand"] == "18.00"
    # Again: the same project item is used, not a second one.
    client.post(url, json={"to_project_id": pid, "quantity": "3"}, headers=h)
    assert InventoryItem.query.filter_by(project_id=pid).count() == 1
    assert item_stock(client, h, org_id, target["id"], pid)["quantity_on_hand"] == "15.00"
    kinds = [m.kind.value for m in InventoryMovement.query.filter_by(item_id=paper["id"]).order_by(InventoryMovement.id)]
    assert kinds == ["count", "move_out", "move_out"]
    # Back to General stock.
    r = client.post(f"/api/inventory/{target['id']}/move",
                    json={"to_project_id": None, "quantity": "5", "from_warehouse_id": depot["id"]}, headers=h)
    assert r.status_code == 201 and r.get_json()["target"]["id"] == paper["id"]
    assert item_stock(client, h, org_id, paper["id"], "general")["quantity_on_hand"] == "20.00"
    # Moves aren't "used on the project".
    assert client.get(f"/api/projects/{pid}/materials", headers=h).get_json()["materials"] == []
    # Same inventory, or a different unit in the target, is refused.
    assert client.post(url, json={"to_project_id": None, "quantity": "1"}, headers=h).status_code == 400
    new_item(client, h, org_id, name="Toner", unit="pcs", quantity="2", project_id=pid)
    toner = new_item(client, h, org_id, name="toner", unit="box", quantity="2")
    r = client.post(f"/api/inventory/{toner['id']}/move", json={"to_project_id": pid, "quantity": "1"}, headers=h)
    assert r.status_code == 409


def test_delete_item_and_warehouse_rules(client):
    h, org_id, pid = setup(client)
    w = new_warehouse(client, h, org_id, project_id=pid)
    chair = new_item(client, h, org_id, quantity="4", warehouse_id=w["id"], project_id=pid)
    assert client.delete(f"/api/warehouses/{w['id']}", headers=h).status_code == 409  # still holds stock
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    assert client.delete(f"/api/inventory/{chair['id']}", headers=c).status_code == 403
    assert client.delete(f"/api/inventory/{chair['id']}", headers=h).status_code == 200
    assert db.session.get(InventoryItem, chair["id"]) is None
    assert InventoryMovement.query.filter_by(item_id=chair["id"]).count() == 0
    assert InventoryStock.query.count() == 0
    assert AuditLog.query.filter_by(action="inventory.item_deleted").one().meta["item"] == "Office chair"
    assert client.delete(f"/api/warehouses/{w['id']}", headers=h).status_code == 200
    assert Warehouse.query.count() == 0


def test_contributors_use_stock_but_managers_organize_it(client):
    h, org_id, pid = setup(client)
    w = new_warehouse(client, h, org_id, project_id=pid)
    chair = new_item(client, h, org_id, quantity="4", project_id=pid)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    assert move(client, c, chair["id"], kind="receive", quantity="1", warehouse_id=w["id"]).status_code == 201
    assert client.post(f"/api/inventory/{chair['id']}/transfers",
                       json={"quantity": "1", "from_warehouse_id": w["id"]}, headers=c).status_code == 201
    assert client.post(f"/api/organizations/{org_id}/warehouses", json={"name": "X"}, headers=c).status_code == 403
    assert client.post(f"/api/inventory/{chair['id']}/move", json={"to_project_id": None, "quantity": "1"}, headers=c).status_code == 403


def test_deleting_a_project_removes_its_inventory_and_warehouses(client):
    h, org_id, pid = setup(client)
    w = new_warehouse(client, h, org_id, project_id=pid)
    new_item(client, h, org_id, name="Desk", quantity="2", warehouse_id=w["id"], project_id=pid)
    general = new_item(client, h, org_id, name="Paper", quantity="10")
    client.post(f"/api/inventory/{general['id']}/move", json={"to_project_id": pid, "quantity": "4"}, headers=h)
    preview = client.post(f"/api/organizations/{org_id}/projects/delete-preview", json={"project_ids": [pid]}, headers=h).get_json()
    assert (preview["inventory_items"], preview["warehouses"]) == (2, 1)
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code == 200
    assert [i.name for i in InventoryItem.query.all()] == ["Paper"]
    assert Warehouse.query.count() == 0 and InventoryStock.query.count() == 0
    # General stock keeps its history; the move out stays, noted.
    assert InventoryMovement.query.filter_by(item_id=general["id"], kind="move_out").one().project_id is None


# ---------- opening inventory when creating a project ----------


def test_new_project_can_start_with_an_inventory(client):
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/projects", json={"name": "Expo stand", "inventory": [
        {"name": "Roll-up banner", "unit": "pcs", "quantity": 4, "unit_cost": "350"},
        {"name": "Flyers", "unit": "box", "quantity": "10", "reorder_level": "2"},
    ]}, headers=h)
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["project"]["id"]
    items = {i["name"]: i for i in listing(client, h, org_id, pid)["items"]}
    assert (items["Roll-up banner"]["quantity_on_hand"], items["Roll-up banner"]["unit_cost"]) == ("4.00", "350.00")
    assert (items["Flyers"]["unit"], items["Flyers"]["reorder_level"]) == ("box", "2.00")


def test_opening_inventory_is_checked_and_all_or_nothing(client):
    h, org_id = make_org(client)
    for bad in ([{"unit": "pcs"}], [{"name": "A"}, {"name": "a"}], [{"name": "A", "quantity": -1}], "nope"):
        r = client.post(f"/api/organizations/{org_id}/projects", json={"name": "P", "inventory": bad}, headers=h)
        assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "inventory"}, bad
    assert client.get(f"/api/organizations/{org_id}/projects", headers=h).get_json()["projects"] == []


def test_plan_from_the_assistant_can_include_inventory(client):
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/projects/from-plan", json={
        "name": "Team retreat", "inventory": [{"name": "Name badges", "quantity": 30}],
    }, headers=h)
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["project"]["id"]
    assert [(i["name"], i["quantity_on_hand"], i["unit"]) for i in listing(client, h, org_id, pid)["items"]] == [
        ("Name badges", "30.00", "pcs"),
    ]
