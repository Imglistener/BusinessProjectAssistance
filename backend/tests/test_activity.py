from app.models import AuditLog, Role
from app.services.audit import project_id_for

from .test_expenses import post_expense, setup_project
from .test_projects import add_member, create_project, make_org


def activity(client, h, pid, query=""):
    r = client.get(f"/api/projects/{pid}/activity{query}", headers=h)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_activity_lists_project_changes_newest_first(client):
    h, org_id, pid = setup_project(client)
    eid = post_expense(client, h, pid, category="Travel", amount="99.90").get_json()["expense"]["id"]
    tid = client.post(f"/api/projects/{pid}/tasks", json={"title": "Book venue"}, headers=h).get_json()["task"]["id"]
    client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=h)
    client.patch(f"/api/projects/{pid}", json={"budget": "2000"}, headers=h)

    body = activity(client, h, pid)
    actions = [e["action"] for e in body["entries"]]
    assert actions == ["project.updated", "task.updated", "task.created", "expense.created", "project.created"]
    by_action = {e["action"]: e for e in body["entries"]}
    assert by_action["task.updated"]["label"] == "Book venue"
    assert by_action["task.updated"]["meta"] == {"status": ["todo", "done"]}
    assert by_action["expense.created"]["label"] == "Travel, 99.90 MAD" and by_action["expense.created"]["entity_id"] == eid
    assert by_action["project.updated"]["meta"] == {"budget": ["1000.00", "2000.00"]}
    assert all(e["actor"] == "Alex Doe" for e in body["entries"])
    assert "project_id" not in by_action["expense.created"]["meta"]
    assert body["entries"][0]["at"].endswith("+00:00")


def test_other_projects_and_org_events_are_excluded(client):
    h, org_id, pid = setup_project(client)
    other = create_project(client, h, org_id, name="Other").get_json()["project"]["id"]
    post_expense(client, h, other)
    add_member(client, org_id, "v@example.com", Role.VIEWER)
    actions = [e["action"] for e in activity(client, h, pid)["entries"]]
    assert actions == ["project.created"]


def test_assignee_names_are_resolved(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    members = client.get(f"/api/organizations/{org_id}/members", headers=h).get_json()["members"]
    cid = next(m["user_id"] for m in members if m["role"] == "contributor")
    tid = client.post(f"/api/projects/{pid}/tasks", json={"title": "T"}, headers=h).get_json()["task"]["id"]
    client.patch(f"/api/tasks/{tid}", json={"assignee_id": cid}, headers=h)
    body = activity(client, h, pid)
    assert body["entries"][0]["meta"]["assignee_id"] == [None, cid]
    assert body["people"][str(cid)] == "Alex Doe"


def test_pagination_and_deleted_records(client):
    h, _, pid = setup_project(client)
    mid = client.post(f"/api/projects/{pid}/milestones", json={"title": "M"}, headers=h).get_json()["milestone"]["id"]
    client.delete(f"/api/milestones/{mid}", headers=h)
    body = activity(client, h, pid, "?limit=1")
    assert body["total"] == 3 and len(body["entries"]) == 1
    assert body["entries"][0]["action"] == "milestone.deleted" and body["entries"][0]["label"] is None
    assert activity(client, h, pid, "?limit=1&offset=2")["entries"][0]["action"] == "project.created"
    assert client.get(f"/api/projects/{pid}/activity?limit=x", headers=h).status_code == 400


def test_permissions(client):
    h, org_id, pid = setup_project(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    assert client.get(f"/api/projects/{pid}/activity", headers=viewer).status_code == 200
    assert client.get(f"/api/projects/{pid}/activity", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/activity").status_code == 401


def test_project_id_rule():
    assert project_id_for("project", 7, None) == 7
    assert project_id_for("task", 3, {"project_id": 7}) == 7
    assert project_id_for("organization_member", 3, {"user_id": 9}) is None
    assert project_id_for("expense", 3, {"project_id": "7"}) is None


def test_org_level_entries_have_no_project(client):
    make_org(client)
    assert AuditLog.query.filter_by(action="organization.created").one().project_id is None
