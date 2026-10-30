from decimal import Decimal

from app.models import Notification, Role, User

from .test_expenses import post_expense, setup_project
from .test_inventory import add_item, move
from .test_members import invite
from .test_projects import add_member, make_org
from .helpers import auth_headers


def inbox(client, h, query=""):
    return client.get(f"/api/notifications{query}", headers=h).get_json()


def uid(email):
    return User.query.filter_by(email=email).one().id


def test_task_assignment_notifies_assignee_not_actor(client):
    h, org_id, pid = setup_project(client)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    tid = client.post(f"/api/projects/{pid}/tasks", json={"title": "Book venue", "assignee_id": uid("c@example.com"), "due_date": "2026-11-20"}, headers=h).get_json()["task"]["id"]
    body = inbox(client, c)
    assert body["unread_count"] == 1
    n = body["notifications"][0]
    assert (n["kind"], n["title"], n["link"], n["organization_name"]) == (
        "task_assigned", "New task for you: Book venue", f"/app/projects/{pid}", "Acme",
    )
    assert "Due 20 Nov 2026" in n["body"]
    # Assigning to yourself: no notification. Re-assigning: the new person hears about it.
    client.patch(f"/api/tasks/{tid}", json={"assignee_id": uid("owner@example.com")}, headers=h)
    assert inbox(client, h)["unread_count"] == 0


def test_over_budget_crossing_notifies_once(client):
    h, org_id, pid = setup_project(client, "1000")
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    post_expense(client, c, pid, amount="900")
    assert inbox(client, h)["unread_count"] == 0
    post_expense(client, c, pid, amount="200")  # crosses the line
    post_expense(client, c, pid, amount="50")  # already over: no repeat
    body = inbox(client, h)
    assert [n["kind"] for n in body["notifications"]] == ["project_over_budget"]
    assert inbox(client, c)["unread_count"] == 0  # the contributor isn't an owner


def test_editing_an_expense_over_the_line_notifies(client):
    h, org_id, pid = setup_project(client, "1000")
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    eid = post_expense(client, c, pid, amount="500").get_json()["expense"]["id"]
    client.patch(f"/api/expenses/{eid}", json={"amount": "1500"}, headers=c)
    assert [n["kind"] for n in inbox(client, h)["notifications"]] == ["project_over_budget"]


def test_trip_travelers_are_notified(client):
    h, org_id, pid = setup_project(client)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    v = add_member(client, org_id, "v@example.com", Role.VIEWER)
    r = client.post(f"/api/projects/{pid}/trips", json={
        "title": "Visit", "destination": "Fes", "start_date": "2026-11-10", "end_date": "2026-11-11",
        "traveler_ids": [uid("owner@example.com"), uid("c@example.com")],
    }, headers=h)
    tid = r.get_json()["trip"]["id"]
    assert inbox(client, c)["notifications"][0]["link"] == f"/app/projects/{pid}/trips/{tid}"
    assert inbox(client, h)["unread_count"] == 0
    client.patch(f"/api/trips/{tid}", json={"traveler_ids": [uid("c@example.com"), uid("v@example.com")]}, headers=h)
    assert inbox(client, v)["unread_count"] == 1 and inbox(client, c)["unread_count"] == 1  # c not re-notified


def test_low_stock_notifies_managers_when_crossing(client):
    h, org_id = make_org(client)
    pm = add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    iid = add_item(client, h, org_id, quantity="12", reorder_level="10").get_json()["item"]["id"]
    move(client, c, iid, "issue", "1")  # 11: fine
    move(client, c, iid, "issue", "2")  # 9: low
    move(client, c, iid, "issue", "1")  # 8: still low, no repeat
    for who in (h, pm):
        assert [n["kind"] for n in inbox(client, who)["notifications"]] == ["low_stock"]
    assert inbox(client, c)["unread_count"] == 0
    assert "9.00 bag left" in inbox(client, pm)["notifications"][0]["body"]


def test_invite_accepted_notifies_inviter(client):
    owner, org_id = make_org(client)
    token = invite(client, owner, org_id).get_json()["token"]
    newcomer = auth_headers(client, email="new@example.com")
    client.post(f"/api/invitations/{token}/accept", headers=newcomer)
    assert inbox(client, owner)["notifications"][0]["kind"] == "invite_accepted"


def test_mark_read_and_scoping(client):
    h, org_id, pid = setup_project(client)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    for title in ("A", "B"):
        client.post(f"/api/projects/{pid}/tasks", json={"title": title, "assignee_id": uid("c@example.com")}, headers=h)
    notes = inbox(client, c)["notifications"]
    assert [n["title"] for n in notes] == ["New task for you: B", "New task for you: A"]

    other, _ = make_org(client, email="rival@example.com", name="Rival")
    assert client.post(f"/api/notifications/{notes[0]['id']}/read", headers=other).status_code == 404
    assert client.post(f"/api/notifications/{notes[0]['id']}/read", headers=c).status_code == 200
    assert inbox(client, c)["unread_count"] == 1
    assert len(inbox(client, c, "?unread_only=true")["notifications"]) == 1
    client.post("/api/notifications/read-all", headers=c)
    assert inbox(client, c)["unread_count"] == 0

    # After leaving the organization, its notifications disappear.
    client.post(f"/api/organizations/{org_id}/members/{uid('c@example.com')}/remove", headers=c)
    assert inbox(client, c)["notifications"] == []
    assert client.get("/api/notifications").status_code == 401


def test_removed_members_are_not_notified(client):
    h, org_id, pid = setup_project(client, "100")
    add_member(client, org_id, "co@example.com", Role.OWNER)
    client.post(f"/api/organizations/{org_id}/members/{uid('co@example.com')}/remove", headers=h)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    post_expense(client, c, pid, amount="200")
    assert Notification.query.filter_by(user_id=uid("co@example.com")).count() == 0
    assert Notification.query.filter_by(user_id=uid("owner@example.com")).count() == 1
