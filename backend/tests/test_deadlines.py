from datetime import date, timedelta

from app.extensions import db
from app.models import Milestone, Role, Task, TaskStatus, User

from .test_projects import add_member, create_project, make_org


def deadlines(client, h, org_id):
    r = client.get(f"/api/organizations/{org_id}/deadlines", headers=h)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def task(pid, title, due=None, status=TaskStatus.TODO, assignee=None):
    db.session.add(Task(project_id=pid, title=title, due_date=due, status=status, assignee_id=assignee))
    db.session.commit()


def test_overdue_and_upcoming_across_projects(client):
    h, org_id = make_org(client)
    a = create_project(client, h, org_id, name="Alpha").get_json()["project"]["id"]
    b = create_project(client, h, org_id, name="Beta").get_json()["project"]["id"]
    today = date.today()
    task(a, "Late", today - timedelta(days=3))
    task(b, "Soon", today + timedelta(days=2))
    task(a, "Too far", today + timedelta(days=30))
    task(a, "Done late", today - timedelta(days=5), TaskStatus.DONE)
    task(a, "No date")
    db.session.add(Milestone(project_id=b, title="Launch", due_date=today + timedelta(days=2), status="open"))
    db.session.add(Milestone(project_id=b, title="Shipped", due_date=today - timedelta(days=1), status="done"))
    db.session.commit()

    body = deadlines(client, h, org_id)
    got = [(i["kind"], i["title"], i["project_name"], i["overdue"], i["days_until_due"]) for i in body["items"]]
    # Oldest first; on the same day, milestones before tasks.
    assert got == [
        ("task", "Late", "Alpha", True, -3),
        ("milestone", "Launch", "Beta", False, 2),
        ("task", "Soon", "Beta", False, 2),
    ]
    assert body["item_count"] == 3 and body["horizon_days"] == 14


def test_archived_projects_are_left_out(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    task(pid, "Late", date.today() - timedelta(days=1))
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert deadlines(client, h, org_id)["items"] == []


def test_my_tasks(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    other = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    me = User.query.filter_by(email="owner@example.com").one().id
    them = User.query.filter_by(email="c@example.com").one().id
    task(pid, "Mine later", date.today() + timedelta(days=60), assignee=me)
    task(pid, "Mine undated", assignee=me)
    task(pid, "Mine soon", date.today() + timedelta(days=1), assignee=me)
    task(pid, "Mine done", date.today(), TaskStatus.DONE, assignee=me)
    task(pid, "Theirs", date.today(), assignee=them)

    body = deadlines(client, h, org_id)
    assert [t["title"] for t in body["my_tasks"]] == ["Mine soon", "Mine later", "Mine undated"]
    assert body["my_task_count"] == 3
    assert [t["title"] for t in deadlines(client, other, org_id)["my_tasks"]] == ["Theirs"]


def test_permissions(client):
    h, org_id = make_org(client)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    assert client.get(f"/api/organizations/{org_id}/deadlines", headers=outsider).status_code == 404
    assert client.get(f"/api/organizations/{org_id}/deadlines").status_code == 401


def test_empty_organization(client):
    h, org_id = make_org(client)
    body = deadlines(client, h, org_id)
    assert body["items"] == [] and body["my_tasks"] == []
