from datetime import date, timedelta
from types import SimpleNamespace as NS

from app.extensions import db
from app.models import AuditLog, Milestone, Role, Task
from app.services import ai_tools, metrics

from .test_expenses import setup_project
from .test_projects import add_member, create_project, make_org


def add_milestone(client, h, pid, **overrides):
    body = {"title": "Beta launch", "due_date": "2026-12-01"}
    body.update(overrides)
    return client.post(f"/api/projects/{pid}/milestones", json=body, headers=h)


def add_task(client, h, pid, **body):
    return client.post(f"/api/projects/{pid}/tasks", json={"title": "Task", **body}, headers=h)


def milestones(client, h, pid):
    return client.get(f"/api/projects/{pid}/milestones", headers=h).get_json()["milestones"]


def test_create_and_track_completion(client):
    h, _, pid = setup_project(client)
    r = add_milestone(client, h, pid)
    assert r.status_code == 201
    m = r.get_json()["milestone"]
    assert (m["status"], m["task_count"], m["task_completion_pct"]) == ("open", 0, None)

    t1 = add_task(client, h, pid, milestone_id=m["id"]).get_json()["task"]
    add_task(client, h, pid, milestone_id=m["id"])
    add_task(client, h, pid, milestone_id=m["id"], status="cancelled")  # not eligible
    add_task(client, h, pid)  # not linked
    assert t1["milestone_id"] == m["id"]
    client.patch(f"/api/tasks/{t1['id']}", json={"status": "done"}, headers=h)

    [row] = milestones(client, h, pid)
    assert (row["task_count"], row["done_task_count"], row["task_completion_pct"]) == (3, 1, "50.00")
    assert AuditLog.query.filter_by(action="milestone.created").count() == 1


def test_order_overdue_and_status(client):
    h, _, pid = setup_project(client)
    past = (date.today() - timedelta(days=3)).isoformat()
    add_milestone(client, h, pid, title="No date", due_date=None)
    late = add_milestone(client, h, pid, title="Late", due_date=past).get_json()["milestone"]
    add_milestone(client, h, pid, title="Later", due_date="2099-01-01")
    rows = milestones(client, h, pid)
    assert [r["title"] for r in rows] == ["Late", "Later", "No date"]
    assert [r["is_overdue"] for r in rows] == [True, False, False]

    r = client.patch(f"/api/milestones/{late['id']}", json={"status": "done"}, headers=h)
    assert r.get_json()["milestone"]["is_overdue"] is False
    entry = AuditLog.query.filter_by(action="milestone.updated").one()
    assert entry.meta["status"] == ["open", "done"]
    assert client.patch(f"/api/milestones/{late['id']}", json={"status": "finished"}, headers=h).status_code == 400


def test_delete_unlinks_tasks(client):
    h, _, pid = setup_project(client)
    mid = add_milestone(client, h, pid).get_json()["milestone"]["id"]
    tid = add_task(client, h, pid, milestone_id=mid).get_json()["task"]["id"]
    assert client.delete(f"/api/milestones/{mid}", headers=h).status_code == 200
    assert Milestone.query.count() == 0
    task = db.session.get(Task, tid)
    assert task is not None and task.milestone_id is None
    assert AuditLog.query.filter_by(action="milestone.deleted").one().meta["unlinked_tasks"] == 1


def test_task_milestone_must_be_in_same_project(client):
    h, org_id, pid = setup_project(client)
    other_pid = create_project(client, h, org_id, name="Other").get_json()["project"]["id"]
    foreign = add_milestone(client, h, other_pid).get_json()["milestone"]["id"]
    r = add_task(client, h, pid, milestone_id=foreign)
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "milestone_id"}
    tid = add_task(client, h, pid).get_json()["task"]["id"]
    assert client.patch(f"/api/tasks/{tid}", json={"milestone_id": foreign}, headers=h).status_code == 400
    assert client.patch(f"/api/tasks/{tid}", json={"milestone_id": 99999}, headers=h).status_code == 400


def test_permissions(client):
    h, org_id, pid = setup_project(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    mid = add_milestone(client, h, pid).get_json()["milestone"]["id"]

    assert len(milestones(client, viewer, pid)) == 1
    assert add_milestone(client, contributor, pid).status_code == 403
    assert client.patch(f"/api/milestones/{mid}", json={"status": "done"}, headers=contributor).status_code == 403
    assert client.delete(f"/api/milestones/{mid}", headers=viewer).status_code == 403
    assert client.get(f"/api/projects/{pid}/milestones", headers=outsider).status_code == 404
    assert client.patch(f"/api/milestones/{mid}", json={"title": "x"}, headers=outsider).status_code == 404


def test_archived_project_is_read_only(client):
    h, _, pid = setup_project(client)
    mid = add_milestone(client, h, pid).get_json()["milestone"]["id"]
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert add_milestone(client, h, pid).status_code == 409
    assert client.patch(f"/api/milestones/{mid}", json={"status": "done"}, headers=h).status_code == 409
    assert client.delete(f"/api/milestones/{mid}", headers=h).status_code == 409
    assert client.get(f"/api/projects/{pid}/milestones", headers=h).status_code == 200


def test_validation(client):
    h, _, pid = setup_project(client)
    assert add_milestone(client, h, pid, title="").status_code == 400
    assert add_milestone(client, h, pid, due_date="01/12/2026").status_code == 400


def test_is_milestone_overdue():
    today = date(2026, 10, 30)
    assert metrics.is_milestone_overdue(NS(status="open", due_date=date(2026, 10, 29)), today) is True
    assert metrics.is_milestone_overdue(NS(status="open", due_date=today), today) is False
    assert metrics.is_milestone_overdue(NS(status="done", due_date=date(2026, 1, 1)), today) is False
    assert metrics.is_milestone_overdue(NS(status="open", due_date=None), today) is False


def test_ai_summary_includes_milestones(client):
    h, org_id, pid = setup_project(client)
    mid = add_milestone(client, h, pid, due_date="2026-10-01").get_json()["milestone"]["id"]
    tid = add_task(client, h, pid, milestone_id=mid).get_json()["task"]["id"]
    client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=h)
    ctx = ai_tools.ToolContext(user_id=1, organization_id=org_id, today=date(2026, 10, 30))
    [m] = ai_tools.get_project_summary(ctx, {"project_id": pid})["milestones"]
    assert m == {
        "title": "Beta launch", "due_date": "2026-10-01", "status": "open", "overdue": True,
        "linked_tasks": 1, "task_completion_pct": "100.00",
    }

