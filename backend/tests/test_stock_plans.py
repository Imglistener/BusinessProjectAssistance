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
        "No item called Projector. Create it first.",
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
