from app.extensions import db
from app.models import AuditLog, Expense, Role, Trip, TripItem, User

from .test_expenses import post_expense, setup_project
from .test_projects import add_member, make_org


def new_trip(client, h, pid, **overrides):
    body = {
        "title": "Client visit", "destination": "Marrakech", "start_date": "2026-11-10",
        "end_date": "2026-11-12", "budget": "6000",
    }
    body.update(overrides)
    return client.post(f"/api/projects/{pid}/trips", json=body, headers=h)


def add_item(client, h, tid, **overrides):
    body = {"kind": "train", "title": "Train to Marrakech", "date": "2026-11-10", "start_time": "08:15",
            "end_time": "11:00", "estimated_cost": "450", "confirmation": "ONCF-123"}
    body.update(overrides)
    return client.post(f"/api/trips/{tid}/items", json=body, headers=h)


def test_create_trip_with_creator_as_traveler(client):
    h, _, pid = setup_project(client)
    r = new_trip(client, h, pid)
    assert r.status_code == 201
    t = r.get_json()["trip"]
    assert (t["nights"], t["status"], t["budget"], t["currency"]) == (2, "planned", "6000.00", "MAD")
    assert [x["name"] for x in t["travelers"]] == ["Alex Doe"]
    assert AuditLog.query.filter_by(action="trip.created").one().project_id == pid


def test_itinerary_order_estimate_and_actual_spend(client):
    h, _, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    add_item(client, h, tid, kind="hotel", title="Riad", date="2026-11-10", start_time=None, estimated_cost="2400")
    add_item(client, h, tid)
    add_item(client, h, tid, kind="meeting", title="Kick-off", date="2026-11-11", start_time="10:00", estimated_cost=None)
    post_expense(client, h, pid, category="Travel", amount="520", expense_date="2026-11-10", trip_id=tid)
    eid = post_expense(client, h, pid, category="Travel", amount="999", expense_date="2026-11-11", trip_id=tid).get_json()["expense"]["id"]
    client.post(f"/api/expenses/{eid}/void", headers=h)

    t = client.get(f"/api/trips/{tid}", headers=h).get_json()["trip"]
    # Same day: timed items first, in time order; untimed last.
    assert [i["title"] for i in t["items"]] == ["Train to Marrakech", "Riad", "Kick-off"]
    assert (t["estimated_cost"], t["actual"], t["remaining"], t["over_budget"]) == ("2850.00", "520.00", "5480.00", False)
    assert len(t["expenses"]) == 2 and t["can_edit"] is True
    # Trip spend is part of the project spend.
    assert client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]["actual"] == "520.00"


def test_item_validation(client):
    h, _, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    assert add_item(client, h, tid, date="2026-11-13").status_code == 400  # outside trip
    assert add_item(client, h, tid, start_time="8:15").status_code == 400
    assert add_item(client, h, tid, start_time="24:00").status_code == 400
    assert add_item(client, h, tid, kind="spaceship").status_code == 400
    assert add_item(client, h, tid, title="").status_code == 400


def test_trip_date_change_cannot_strand_items(client):
    h, _, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    add_item(client, h, tid, date="2026-11-12")
    r = client.patch(f"/api/trips/{tid}", json={"end_date": "2026-11-11"}, headers=h)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "itinerary_outside_dates"
    assert client.patch(f"/api/trips/{tid}", json={"end_date": "2026-11-09"}, headers=h).status_code == 400
    ok = client.patch(f"/api/trips/{tid}", json={"end_date": "2026-11-14", "status": "booked"}, headers=h)
    assert ok.status_code == 200 and ok.get_json()["trip"]["status"] == "booked"
    entry = AuditLog.query.filter_by(action="trip.updated").one()
    assert entry.meta["status"] == ["planned", "booked"] and entry.meta["end_date"] == ["2026-11-12", "2026-11-14"]


def test_travelers_must_be_members(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    cid = User.query.filter_by(email="c@example.com").one().id
    outsider_h, _ = make_org(client, email="rival@example.com", name="Rival")
    oid = User.query.filter_by(email="rival@example.com").one().id
    tid = new_trip(client, h, pid, traveler_ids=[cid]).get_json()["trip"]["id"]
    assert [x["user_id"] for x in client.get(f"/api/trips/{tid}", headers=h).get_json()["trip"]["travelers"]] == [cid]
    assert client.patch(f"/api/trips/{tid}", json={"traveler_ids": [oid]}, headers=h).status_code == 400
    assert client.patch(f"/api/trips/{tid}", json={"traveler_ids": "me"}, headers=h).status_code == 400


def test_expense_trip_must_be_same_project(client):
    h, org_id, pid = setup_project(client)
    other = client.post(f"/api/organizations/{org_id}/projects", json={"name": "Other"}, headers=h).get_json()["project"]["id"]
    foreign_trip = new_trip(client, h, other).get_json()["trip"]["id"]
    r = post_expense(client, h, pid, trip_id=foreign_trip)
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "trip_id"}
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    assert client.patch(f"/api/expenses/{eid}", json={"trip_id": foreign_trip}, headers=h).status_code == 400


def test_delete_trip_keeps_expenses(client):
    h, _, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    add_item(client, h, tid)
    eid = post_expense(client, h, pid, trip_id=tid).get_json()["expense"]["id"]
    assert client.delete(f"/api/trips/{tid}", headers=h).status_code == 200
    assert Trip.query.count() == 0 and TripItem.query.count() == 0
    assert db.session.get(Expense, eid).trip_id is None
    assert AuditLog.query.filter_by(action="trip.deleted").one().meta["unlinked_expenses"] == 1


def test_permissions(client):
    h, org_id, pid = setup_project(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    other_contributor = add_member(client, org_id, "c2@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")

    own = new_trip(client, contributor, pid).get_json()["trip"]["id"]
    assert add_item(client, contributor, own).status_code == 201
    assert add_item(client, other_contributor, own).status_code == 403
    assert client.patch(f"/api/trips/{own}", json={"title": "x"}, headers=h).status_code == 200  # managers can
    assert new_trip(client, viewer, pid).status_code == 403
    assert client.get(f"/api/trips/{own}", headers=viewer).get_json()["trip"]["can_edit"] is False
    assert client.get(f"/api/trips/{own}", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/trips", headers=outsider).status_code == 404


def test_archived_project_trips_are_read_only(client):
    h, _, pid = setup_project(client)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    iid = add_item(client, h, tid).get_json()["item"]["id"]
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert new_trip(client, h, pid).status_code == 409
    assert client.patch(f"/api/trips/{tid}", json={"title": "x"}, headers=h).status_code == 409
    assert client.patch(f"/api/trip-items/{iid}", json={"title": "x"}, headers=h).status_code == 409
    assert client.get(f"/api/trips/{tid}", headers=h).get_json()["trip"]["can_edit"] is False


def test_list_trips(client):
    h, _, pid = setup_project(client)
    new_trip(client, h, pid, title="Later", start_date="2026-12-01", end_date="2026-12-02")
    new_trip(client, h, pid, title="Sooner")
    trips = client.get(f"/api/projects/{pid}/trips", headers=h).get_json()["trips"]
    assert [t["title"] for t in trips] == ["Sooner", "Later"] and "items" not in trips[0]


def test_upcoming_trip_on_dashboard_and_in_ai_summary(client):
    from datetime import date, timedelta

    from app.services import ai_tools

    h, org_id, pid = setup_project(client)
    start = date.today() + timedelta(days=3)
    new_trip(client, h, pid, start_date=start.isoformat(), end_date=(start + timedelta(days=1)).isoformat())
    new_trip(client, h, pid, title="Cancelled", status="cancelled",
             start_date=start.isoformat(), end_date=start.isoformat())
    items = client.get(f"/api/organizations/{org_id}/deadlines", headers=h).get_json()["items"]
    assert [(i["kind"], i["title"]) for i in items] == [("trip", "Client visit (Marrakech)")]

    ctx = ai_tools.ToolContext(user_id=1, organization_id=org_id, today=date.today())
    trips = ai_tools.get_project_summary(ctx, {"project_id": pid})["trips"]
    assert [(t["title"], t["budget"], t["actual"]) for t in trips] == [("Client visit", "6000.00", "0.00"), ("Cancelled", "6000.00", "0.00")]
