"""The assistant drafts stock changes; a person confirms them through /inventory/changes."""
from datetime import date

from app.extensions import db
from app.models import AuditLog, InventoryItem, InventoryMovement, Notification, Role, User
from app.services import ai_tools

from .test_inventory import add_item
from .test_projects import add_member, create_project, make_org


def ctx(client_email: str, org_id: int):
    user = User.query.filter_by(email=client_email).one()
    return ai_tools.ToolContext(user_id=user.id, organization_id=org_id, today=date(2026, 10, 30))


def setup(client):
    h, org_id = make_org(client)
    paper = add_item(client, h, org_id, name="Printer paper A4", unit="box", quantity="4", reorder_level="6",
                     sku="PAP-A4").get_json()["item"]
    chair = add_item(client, h, org_id, name="Office chair", unit="pcs", quantity="8", reorder_level=None).get_json()["item"]
    pid = create_project(client, h, org_id, name="Office move to Casablanca").get_json()["project"]["id"]
    return h, org_id, paper, chair, pid


def apply(client, h, org_id, changes):
    return client.post(f"/api/organizations/{org_id}/inventory/changes", json={"changes": changes}, headers=h)


# ---------- lookup ----------


def test_find_items_by_name_sku_or_location(client):
    h, org_id, paper, chair, _ = setup(client)
    c = ctx("owner@example.com", org_id)
    r = ai_tools.find_inventory_items(c, {"query": "chair"})
    assert [i["name"] for i in r["items"]] == ["Office chair"]
    assert r["items"][0]["on_hand"] == "8.00" and r["items"][0]["unit"] == "pcs"
    assert [i["name"] for i in ai_tools.find_inventory_items(c, {"query": "pap-a4"})["items"]] == ["Printer paper A4"]
    assert len(ai_tools.find_inventory_items(c, {})["items"]) == 2
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    add_item(client, other_h, other_org, name="Office chair deluxe")
    assert [i["name"] for i in ai_tools.find_inventory_items(c, {"query": "chair"})["items"]] == ["Office chair"]


# ---------- drafts ----------


def test_draft_resolves_names_and_previews_quantities(client):
    h, org_id, paper, chair, pid = setup(client)
    r = ai_tools.propose_stock_changes(ctx("owner@example.com", org_id), {"changes": [
        {"kind": "receive", "item": "printer paper", "quantity": 20},
        {"kind": "issue", "item": "office chair", "quantity": 3, "project": "office move"},
        {"kind": "issue", "item": "Office chair", "quantity": 2},
        {"kind": "adjust", "item": "PAP-A4", "quantity": -1, "note": "Water damage"},
        {"kind": "create", "item": "Whiteboard markers", "unit": "box", "quantity": 5, "reorder_level": 2},
    ]})
    assert r["status"] == "draft_not_saved" and r["problems"] == [] and r["needs_manager"] == []
    lines = r["proposal"]["lines"]
    assert [(l["kind"], l["item_id"], l["on_hand_before"], l["on_hand_after"]) for l in lines] == [
        ("receive", paper["id"], "4.00", "24.00"),
        ("issue", chair["id"], "8.00", "5.00"),
        ("issue", chair["id"], "5.00", "3.00"),  # follows on from the line before
        ("adjust", paper["id"], "24.00", "23.00"),
        ("create", None, "0.00", "5.00"),
    ]
    assert (lines[1]["project_id"], lines[1]["project_name"]) == (pid, "Office move to Casablanca")
    assert lines[0]["low_after"] is False and lines[0]["unit"] == "box"
    assert r["proposal"]["can_apply"] is True
    # Nothing was saved.
    assert InventoryMovement.query.count() == 2 and InventoryItem.query.count() == 2


def test_draft_reports_problems_per_line(client):
    h, org_id, paper, chair, pid = setup(client)
    add_item(client, h, org_id, name="Office chair arm", quantity="1")
    r = ai_tools.propose_stock_changes(ctx("owner@example.com", org_id), {"changes": [
        {"kind": "receive", "item": "Projector", "quantity": 1},
        {"kind": "issue", "item": "Printer paper A4", "quantity": 10},
        {"kind": "adjust", "item": "Office chair", "quantity": -1},
        {"kind": "receive", "item": "office", "quantity": 1},
        {"kind": "create", "item": "office chair"},
        {"kind": "issue", "item": "Office chair", "quantity": 1, "project": "Nonexistent"},
        {"kind": "issue", "item": "Projector", "quantity": 1},
        {"kind": "receive", "item": "Office chair", "quantity": 0},
    ]})
    lines = r["proposal"]["lines"]
    errors = [l["error"] for l in lines]
    # Stock arriving for an untracked item becomes a "new item" line, with the delivery as opening stock.
    assert (lines[0]["kind"], lines[0]["name"], lines[0]["on_hand_after"]) == ("create", "Projector", "1.00")
    assert errors == [
        None,
        "Only 4.00 box on hand.",
        "Say why the stock is being adjusted.",
        "Several items match: Office chair, Office chair arm. Say which one.",
        "An item called Office chair already exists. Receive stock into it instead.",
        "No active project called Nonexistent.",
        "No item called Projector in General stock.",
        "Give a quantity greater than zero.",
    ]
    assert len(r["problems"]) == 7 and r["proposal"]["can_apply"] is True


def test_draft_marks_lines_a_contributor_cannot_confirm(client):
    h, org_id, paper, chair, pid = setup(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    r = ai_tools.propose_stock_changes(ctx("c@example.com", org_id), {"changes": [
        {"kind": "receive", "item": "Office chair", "quantity": 2},
        {"kind": "adjust", "item": "Office chair", "quantity": -1, "note": "Broken"},
        {"kind": "create", "item": "Stapler"},
    ]})
    assert [l["allowed"] for l in r["proposal"]["lines"]] == [True, False, False]
    assert r["needs_manager"] == ["Office chair", "Stapler"]
    assert r["proposal"]["can_apply"] is True  # the receive line can still go through


def test_draft_needs_at_least_one_line(client):
    h, org_id, *_ = setup(client)
    try:
        ai_tools.propose_stock_changes(ctx("owner@example.com", org_id), {"changes": []})
    except ai_tools.ToolError as e:
        assert "at least one" in str(e)
    else:
        raise AssertionError("expected ToolError")


# ---------- confirming ----------


def test_apply_saves_every_line_with_history_and_notifications(client):
    h, org_id, paper, chair, pid = setup(client)
    add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    r = apply(client, h, org_id, [
        {"kind": "receive", "item_id": paper["id"], "quantity": "20", "note": "Delivery 31 Oct"},
        {"kind": "issue", "item_id": chair["id"], "quantity": "3", "project_id": pid},
        {"kind": "adjust", "item_id": paper["id"], "quantity": "-19", "note": "Water damage"},
        {"kind": "create", "name": "Whiteboard markers", "unit": "box", "quantity": "5", "reorder_level": "2",
         "unit_cost": "45"},
    ])
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["applied"] == 4
    on_hand = {i["name"]: i["quantity_on_hand"] for i in body["items"]}
    assert on_hand == {"Printer paper A4": "5.00", "Office chair": "5.00", "Whiteboard markers": "5.00"}
    kinds = [m.kind.value for m in InventoryMovement.query.order_by(InventoryMovement.id)]
    # Two opening stocks from setup, then the four confirmed lines (the new item's opening stock is a count).
    assert kinds == ["count", "count", "receive", "issue", "adjust", "count"]
    assert InventoryMovement.query.filter_by(project_id=pid).one().quantity_delta == -3
    assert AuditLog.query.filter_by(action="inventory.item_created").count() == 3
    # Paper dropped to its reorder level: managers hear about it, as with the Stock page.
    assert Notification.query.filter_by(kind="low_stock").count() >= 1


def test_apply_is_all_or_nothing(client):
    h, org_id, paper, chair, pid = setup(client)
    r = apply(client, h, org_id, [
        {"kind": "receive", "item_id": paper["id"], "quantity": "20"},
        {"kind": "issue", "item_id": chair["id"], "quantity": "50"},
    ])
    assert r.status_code == 409
    err = r.get_json()["error"]
    assert err["details"] == {"line": 1, "field": "quantity"} and err["message"] == "Only 8.00 pcs on hand."
    assert db.session.get(InventoryItem, paper["id"]).quantity_on_hand == 4  # the first line was not kept


def test_apply_checks_lines_again(client):
    h, org_id, paper, chair, pid = setup(client)
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    secret = add_item(client, other_h, other_org, name="Secret").get_json()["item"]
    cases = [
        ([{"kind": "receive", "item_id": secret["id"], "quantity": "1"}], 404),
        ([{"kind": "adjust", "item_id": paper["id"], "quantity": "-1"}], 400),  # no reason
        ([{"kind": "receive", "item_id": paper["id"], "quantity": "-1"}], 400),
        ([{"kind": "create", "name": "printer paper a4"}], 409),
        ([{"kind": "explode", "item_id": paper["id"], "quantity": "1"}], 400),
        ([], 400),
    ]
    for changes, status in cases:
        assert apply(client, h, org_id, changes).status_code == status, changes


def test_apply_respects_roles(client):
    h, org_id, paper, chair, pid = setup(client)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    v = add_member(client, org_id, "v@example.com", Role.VIEWER)
    assert apply(client, c, org_id, [{"kind": "receive", "item_id": paper["id"], "quantity": "1"}]).status_code == 201
    r = apply(client, c, org_id, [{"kind": "create", "name": "Stapler"}])
    assert r.status_code == 403 and r.get_json()["error"]["details"] == {"line": 0}
    assert apply(client, v, org_id, [{"kind": "receive", "item_id": paper["id"], "quantity": "1"}]).status_code == 403
    outsider_h, _ = make_org(client, email="out@example.com", name="Out")
    assert apply(client, outsider_h, org_id, [{"kind": "receive", "item_id": paper["id"], "quantity": "1"}]).status_code == 404


def test_apply_errors_follow_the_language(client):
    h, org_id, paper, chair, pid = setup(client)
    r = client.post(
        f"/api/organizations/{org_id}/inventory/changes",
        json={"changes": [{"kind": "issue", "item_id": chair["id"], "quantity": "50"}]},
        headers={**h, "Accept-Language": "fr"},
    )
    assert r.get_json()["error"]["message"] == "Seulement 8.00 pcs en stock."


# ---------- project inventories, warehouses, transfers, moves, deletes ----------


def scoped_setup(client):
    h, org_id, paper, chair, pid = setup(client)
    wh = lambda name, **kw: client.post(f"/api/organizations/{org_id}/warehouses", json={"name": name, **kw}, headers=h).get_json()["warehouse"]
    casa = wh("Casablanca depot", project_id=pid)
    tangier = wh("Tangier store", project_id=pid)
    desk = add_item(client, h, org_id, name="Desk", unit="pcs", quantity="10", reorder_level=None,
                    project_id=pid, warehouse_id=casa["id"]).get_json()["item"]
    return h, org_id, paper, chair, pid, casa, tangier, desk


def test_draft_in_a_project_inventory_with_warehouses(client):
    h, org_id, paper, chair, pid, casa, tangier, desk = scoped_setup(client)
    r = ai_tools.propose_stock_changes(ctx("owner@example.com", org_id), {"changes": [
        {"kind": "transfer", "inventory": "office move", "item": "desk", "quantity": 4,
         "from_warehouse": "casablanca", "to_warehouse": "tangier"},
        {"kind": "receive", "inventory": "Office move to Casablanca", "item": "Desk", "quantity": 2, "warehouse": "Tangier store"},
        {"kind": "move", "item": "Printer paper A4", "quantity": 3, "to_inventory": "Office move"},
        {"kind": "issue", "inventory": "Office move", "item": "Desk", "quantity": 7, "warehouse": "Casablanca depot"},
        {"kind": "delete", "item": "Office chair"},
        {"kind": "create", "inventory": "Office move", "item": "Cable ties", "quantity": 100, "warehouse": "Tangier store"},
    ]})
    lines = r["proposal"]["lines"]
    assert [l["error"] for l in lines] == [None, None, None, "Only 6.00 pcs in Casablanca depot.", None, None]
    t = lines[0]
    assert (t["inventory_project_id"], t["warehouse_name"], t["to_warehouse_name"], t["on_hand_after"]) == (
        pid, "Casablanca depot", "Tangier store", "10.00")
    assert (lines[1]["warehouse_id"], lines[1]["on_hand_after"]) == (tangier["id"], "12.00")
    m = lines[2]
    assert (m["inventory_name"], m["to_project_id"], m["to_inventory_name"], m["on_hand_after"]) == (
        "General stock", pid, "Office move to Casablanca", "1.00")
    assert (lines[4]["kind"], lines[4]["on_hand_before"], lines[4]["on_hand_after"]) == ("delete", "8.00", "0.00")
    assert (lines[5]["inventory_project_id"], lines[5]["warehouse_name"]) == (pid, "Tangier store")


def test_draft_names_unknown_inventories_and_warehouses(client):
    h, org_id, *_ = scoped_setup(client)
    r = ai_tools.propose_stock_changes(ctx("owner@example.com", org_id), {"changes": [
        {"kind": "receive", "inventory": "Moon base", "item": "Desk", "quantity": 1},
        {"kind": "receive", "inventory": "Office move", "item": "Desk", "quantity": 1, "warehouse": "Rabat"},
        {"kind": "transfer", "inventory": "Office move", "item": "Desk", "quantity": 1, "from_warehouse": "Tangier",
         "to_warehouse": "Tangier"},
        {"kind": "move", "item": "Office chair", "quantity": 1, "to_inventory": "General stock"},
    ]})
    assert [l["error"] for l in r["proposal"]["lines"]] == [
        "No active project called Moon base.",
        "No warehouse called Rabat in Office move to Casablanca.",
        "Choose two different places.",
        "Choose a different inventory.",
    ]


def test_apply_scoped_lines(client):
    h, org_id, paper, chair, pid, casa, tangier, desk = scoped_setup(client)
    r = apply(client, h, org_id, [
        {"kind": "transfer", "item_id": desk["id"], "quantity": "4", "warehouse_id": casa["id"], "to_warehouse_id": tangier["id"]},
        {"kind": "move", "item_id": paper["id"], "quantity": "3", "to_project_id": pid, "to_warehouse_id": tangier["id"]},
        {"kind": "create", "name": "Cable ties", "quantity": "100", "inventory_project_id": pid, "warehouse_id": tangier["id"]},
        {"kind": "delete", "item_id": chair["id"]},
    ])
    assert r.status_code == 201, r.get_json()
    listed = client.get(f"/api/organizations/{org_id}/inventory?scope={pid}", headers=h).get_json()["items"]
    by_name = {i["name"]: i for i in listed}
    assert {s["warehouse"]: s["quantity"] for s in by_name["Desk"]["stock"]} == {"Casablanca depot": "6.00", "Tangier store": "4.00"}
    assert by_name["Printer paper A4"]["quantity_on_hand"] == "3.00"
    assert by_name["Cable ties"]["stock"][0]["warehouse"] == "Tangier store"
    assert db.session.get(InventoryItem, chair["id"]) is None
    # A warehouse from another inventory is refused, and the whole batch with it.
    general_wh = client.post(f"/api/organizations/{org_id}/warehouses", json={"name": "HQ"}, headers=h).get_json()["warehouse"]
    r = apply(client, h, org_id, [
        {"kind": "receive", "item_id": desk["id"], "quantity": "1"},
        {"kind": "receive", "item_id": desk["id"], "quantity": "1", "warehouse_id": general_wh["id"]},
    ])
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"line": 1, "field": "warehouse_id"}
    assert db.session.get(InventoryItem, desk["id"]).quantity_on_hand == 10


def test_contributors_can_transfer_but_not_move_or_delete(client):
    h, org_id, paper, chair, pid, casa, tangier, desk = scoped_setup(client)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    r = ai_tools.propose_stock_changes(ctx("c@example.com", org_id), {"changes": [
        {"kind": "transfer", "inventory": "Office move", "item": "Desk", "quantity": 1, "from_warehouse": "Casablanca",
         "to_warehouse": "Tangier"},
        {"kind": "move", "item": "Office chair", "quantity": 1, "to_inventory": "Office move"},
        {"kind": "delete", "item": "Office chair"},
    ]})
    assert [l["allowed"] for l in r["proposal"]["lines"]] == [True, False, False]
    assert apply(client, c, org_id, [{"kind": "delete", "item_id": chair["id"]}]).status_code == 403


def test_lookup_tools_know_inventories_and_warehouses(client):
    h, org_id, paper, chair, pid, casa, tangier, desk = scoped_setup(client)
    c = ctx("owner@example.com", org_id)
    r = ai_tools.find_inventory_items(c, {"query": "desk"})
    assert [(i["name"], i["inventory"], i["by_warehouse"], i["not_in_a_warehouse"]) for i in r["items"]] == [
        ("Desk", "Office move to Casablanca", {"Casablanca depot": "10.00"}, "0.00"),
    ]
    assert [i["name"] for i in ai_tools.find_inventory_items(c, {"inventory": "General stock"})["items"]] == [
        "Office chair", "Printer paper A4",
    ]
    # Models send null for "not in a warehouse"; it means the same as leaving the field out.
    schema = ai_tools.TOOLS["propose_stock_changes"][2]["properties"]["changes"]["items"]["properties"]
    assert schema["warehouse"]["type"] == ["string", "null"] and schema["kind"]["type"] == "string"
    r = ai_tools.propose_stock_changes(c, {"changes": [
        {"kind": "transfer", "inventory": "Office move inventory", "item": "Desk", "quantity": 4,
         "warehouse": "Casablanca depot", "to_warehouse": "Tangier store", "note": None},
        {"kind": "receive", "item": "Printer paper A4", "quantity": 1, "warehouse": None},
    ]})
    assert r["problems"] == []
    # People (and models) say "the X inventory"; the trailing word is ignored when nothing else matches.
    assert ai_tools.find_inventory_items(c, {"inventory": "Office move inventory"})["inventory"] == "Office move to Casablanca"
    w = ai_tools.list_warehouses(c, {"inventory": "office move"})
    assert [(x["name"], x["items"]) for x in w["warehouses"]] == [
        ("Casablanca depot", ["Desk: 10.00 pcs"]), ("Tangier store", []),
    ]
    try:
        ai_tools.find_inventory_items(c, {"inventory": "Moon base"})
    except ai_tools.ToolError as e:
        assert "No project called Moon base" in str(e)
    else:
        raise AssertionError("expected ToolError")
