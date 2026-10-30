from datetime import date, timedelta

from app.models import AuditLog, Role, Task, User

from .helpers import auth_headers
from .test_projects import add_member, create_project, make_org


def setup_project(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    return h, org_id, pid


def post_task(client, headers, pid, **overrides):
    body = {"title": "Draft wireframes"}
    body.update(overrides)
    return client.post(f"/api/projects/{pid}/tasks", json=body, headers=headers)


def user_id(email):
    return User.query.filter_by(email=email).one().id


DAYS_AGO_2 = (date.today() - timedelta(days=2)).isoformat()  # two days avoids timezone edge cases
IN_10_DAYS = (date.today() + timedelta(days=10)).isoformat()


# ---------- create ----------


def test_create_task_defaults(client):
    h, _, pid = setup_project(client)
    r = post_task(client, h, pid, description="First pass")
    assert r.status_code == 201
    t = r.get_json()["task"]
    assert t["status"] == "todo" and t["priority"] == "medium"
    assert t["due_date"] is None and t["assignee_id"] is None and t["is_overdue"] is False
    assert r.get_json()["project"]["task_completion_pct"] == "0.00"


def test_create_task_with_assignee_and_audit(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    cid = user_id("c@example.com")
    r = post_task(client, h, pid, assignee_id=cid, priority="high", due_date=IN_10_DAYS)
    t = r.get_json()["task"]
    assert t["assignee_id"] == cid and t["assignee_name"] == "Alex Doe" and t["priority"] == "high"
    entry = AuditLog.query.filter_by(action="task.created", entity_id=t["id"]).one()
    assert entry.meta == {"project_id": pid, "priority": "high", "assignee_id": cid}


def test_assignee_must_belong_to_the_organization(client):
    h, _, pid = setup_project(client)
    auth_headers(client, email="stranger@example.com")
    r = post_task(client, h, pid, assignee_id=user_id("stranger@example.com"))
    assert r.status_code == 400 and r.get_json()["error"]["details"]["field"] == "assignee_id"
    assert post_task(client, h, pid, assignee_id=99999).status_code == 400
    assert post_task(client, h, pid, assignee_id="1").status_code == 400
    assert post_task(client, h, pid, assignee_id=True).status_code == 400
    assert Task.query.count() == 0


def test_task_validation(client):
    h, _, pid = setup_project(client)
    for override in ({"title": ""}, {"title": "x" * 201}, {"priority": "urgent"}, {"status": "later"}, {"due_date": "tomorrow"}):
        r = post_task(client, h, pid, **override)
        assert r.status_code == 400, override
    assert Task.query.count() == 0


def test_task_created_as_done_gets_completed_at(client):
    h, _, pid = setup_project(client)
    t = post_task(client, h, pid, status="done").get_json()["task"]
    assert t["completed_at"] is not None


# ---------- permissions ----------


def test_roles_and_isolation(client):
    h, org_id, pid = setup_project(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider = auth_headers(client, email="out@example.com")

    assert post_task(client, contributor, pid).status_code == 201
    assert post_task(client, viewer, pid).status_code == 403
    assert post_task(client, outsider, pid).status_code == 404
    url = f"/api/projects/{pid}/tasks"
    assert client.get(url, headers=viewer).status_code == 200
    assert client.get(url, headers=outsider).status_code == 404
    tid = Task.query.first().id
    assert client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=outsider).status_code == 404
    assert client.patch("/api/tasks/99999", json={}, headers=outsider).status_code == 404
    assert client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=viewer).status_code == 403


def test_contributor_can_only_change_status_of_own_tasks(client):
    h, org_id, pid = setup_project(client)
    c1 = add_member(client, org_id, "c1@example.com", Role.CONTRIBUTOR)
    c2 = add_member(client, org_id, "c2@example.com", Role.CONTRIBUTOR)
    mine = post_task(client, h, pid, assignee_id=user_id("c1@example.com")).get_json()["task"]["id"]
    unassigned = post_task(client, h, pid).get_json()["task"]["id"]

    assert client.patch(f"/api/tasks/{mine}", json={"status": "in_progress"}, headers=c1).status_code == 200
    # Not their task, or a field beyond status.
    assert client.patch(f"/api/tasks/{mine}", json={"status": "done"}, headers=c2).status_code == 403
    assert client.patch(f"/api/tasks/{unassigned}", json={"status": "done"}, headers=c1).status_code == 403
    for body in ({"title": "x"}, {"assignee_id": user_id("c2@example.com")}, {"status": "done", "priority": "high"}):
        assert client.patch(f"/api/tasks/{mine}", json=body, headers=c1).status_code == 403, body
    # Owners can edit anything.
    assert client.patch(f"/api/tasks/{mine}", json={"title": "Renamed"}, headers=h).status_code == 200


# ---------- list ----------


def test_list_sorted_by_due_date_with_undated_last(client):
    h, _, pid = setup_project(client)
    post_task(client, h, pid, title="undated")
    post_task(client, h, pid, title="later", due_date=IN_10_DAYS)
    post_task(client, h, pid, title="sooner", due_date=DAYS_AGO_2)
    titles = [t["title"] for t in client.get(f"/api/projects/{pid}/tasks", headers=h).get_json()["tasks"]]
    assert titles == ["sooner", "later", "undated"]


def test_list_filters_and_overdue_flag(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    cid = user_id("c@example.com")
    post_task(client, h, pid, title="late", due_date=DAYS_AGO_2, assignee_id=cid)
    post_task(client, h, pid, title="finished late", due_date=DAYS_AGO_2, status="done")
    post_task(client, h, pid, title="dropped", due_date=DAYS_AGO_2, status="cancelled")
    post_task(client, h, pid, title="future", due_date=IN_10_DAYS)

    url = f"/api/projects/{pid}/tasks"
    tasks = {t["title"]: t for t in client.get(url, headers=h).get_json()["tasks"]}
    assert tasks["late"]["is_overdue"] is True
    assert not tasks["finished late"]["is_overdue"] and not tasks["dropped"]["is_overdue"]
    assert not tasks["future"]["is_overdue"]

    overdue = client.get(url + "?overdue=true", headers=h).get_json()["tasks"]
    assert [t["title"] for t in overdue] == ["late"]
    assert [t["title"] for t in client.get(url + "?status=done", headers=h).get_json()["tasks"]] == ["finished late"]
    assert [t["title"] for t in client.get(f"{url}?assignee_id={cid}", headers=h).get_json()["tasks"]] == ["late"]
    assert client.get(url + "?status=nope", headers=h).status_code == 400
    assert client.get(url + "?assignee_id=x", headers=h).status_code == 400


# ---------- update ----------


def test_status_changes_drive_completed_at_and_project_metrics(client):
    h, _, pid = setup_project(client)
    t1 = post_task(client, h, pid).get_json()["task"]["id"]
    post_task(client, h, pid)

    r = client.patch(f"/api/tasks/{t1}", json={"status": "done"}, headers=h)
    assert r.get_json()["task"]["completed_at"] is not None
    assert r.get_json()["project"]["task_completion_pct"] == "50.00"

    r = client.patch(f"/api/tasks/{t1}", json={"status": "in_progress"}, headers=h)
    assert r.get_json()["task"]["completed_at"] is None
    assert r.get_json()["project"]["task_completion_pct"] == "0.00"


def test_cancelled_tasks_leave_the_completion_percentage(client):
    h, _, pid = setup_project(client)
    post_task(client, h, pid, status="done")
    t2 = post_task(client, h, pid).get_json()["task"]["id"]
    r = client.patch(f"/api/tasks/{t2}", json={"status": "cancelled"}, headers=h)
    assert r.get_json()["project"]["task_completion_pct"] == "100.00"


def test_overdue_count_flows_into_project_and_dashboard(client):
    h, org_id, pid = setup_project(client)
    post_task(client, h, pid, due_date=DAYS_AGO_2)
    assert client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]["overdue_task_count"] == 1
    summary = client.get(f"/api/organizations/{org_id}/dashboard", headers=h).get_json()["summary"]
    assert summary["overdue_task_count"] == 1


def test_update_audits_status_and_assignee_changes(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    cid = user_id("c@example.com")
    tid = post_task(client, h, pid).get_json()["task"]["id"]
    r = client.patch(
        f"/api/tasks/{tid}",
        json={"status": "in_progress", "assignee_id": cid, "title": "New title", "due_date": IN_10_DAYS},
        headers=h,
    )
    assert r.status_code == 200
    meta = AuditLog.query.filter_by(action="task.updated", entity_id=tid).one().meta
    assert meta["status"] == ["todo", "in_progress"]
    assert meta["assignee_id"] == [None, cid]
    assert meta["due_date"] == [None, IN_10_DAYS]
    assert meta["title"] == "changed"


def test_unassign_and_noop_update(client):
    h, org_id, pid = setup_project(client)
    add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    tid = post_task(client, h, pid, assignee_id=user_id("c@example.com")).get_json()["task"]["id"]
    r = client.patch(f"/api/tasks/{tid}", json={"assignee_id": None}, headers=h)
    assert r.get_json()["task"]["assignee_id"] is None
    before = AuditLog.query.filter_by(action="task.updated").count()
    client.patch(f"/api/tasks/{tid}", json={"assignee_id": None}, headers=h)
    assert AuditLog.query.filter_by(action="task.updated").count() == before


def test_update_validation(client):
    h, _, pid = setup_project(client)
    tid = post_task(client, h, pid).get_json()["task"]["id"]
    for body in ({"title": ""}, {"status": None}, {"priority": None}, {"status": "later"}, {"due_date": "nope"}, {"assignee_id": 99999}):
        assert client.patch(f"/api/tasks/{tid}", json=body, headers=h).status_code == 400, body


def test_archived_project_blocks_task_changes(client):
    h, _, pid = setup_project(client)
    tid = post_task(client, h, pid).get_json()["task"]["id"]
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert post_task(client, h, pid).status_code == 409
    assert client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=h).status_code == 409
