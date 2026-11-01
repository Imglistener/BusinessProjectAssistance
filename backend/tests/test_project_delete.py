"""Deleting projects for good: owners only, everything about the project goes, stock history and audit stay."""
import os

from app.extensions import db
from app.models import (
    Attachment,
    AuditLog,
    Expense,
    InventoryMovement,
    Milestone,
    Notification,
    Project,
    Role,
    Task,
    Trip,
    TripItem,
    User,
)

from .test_attachments import upload
from .test_expenses import post_expense
from .test_inventory import add_item as add_stock_item, move
from .test_milestones import add_milestone
from .test_projects import add_member, create_project, make_org
from .test_trips import add_item as add_trip_item, new_trip


def full_project(client, h, org_id, name="Office move"):
    """A project with an expense and receipt, a milestone, a task, a trip with an itinerary item."""
    pid = create_project(client, h, org_id, name=name).get_json()["project"]["id"]
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    assert upload(client, h, eid).status_code == 201
    mid = add_milestone(client, h, pid).get_json()["milestone"]["id"]
    client.post(f"/api/projects/{pid}/tasks", json={"title": "Pack boxes", "milestone_id": mid}, headers=h)
    tid = new_trip(client, h, pid).get_json()["trip"]["id"]
    add_trip_item(client, h, tid)
    return pid


def preview(client, h, org_id, ids):
    return client.post(f"/api/organizations/{org_id}/projects/delete-preview", json={"project_ids": ids}, headers=h)


def delete_many(client, h, org_id, ids):
    return client.post(f"/api/organizations/{org_id}/projects/delete", json={"project_ids": ids}, headers=h)


def test_preview_counts_what_will_go(client):
    h, org_id = make_org(client)
    pid = full_project(client, h, org_id)
    r = preview(client, h, org_id, [pid])
    assert r.status_code == 200
    body = r.get_json()
    assert body["projects"] == [{"id": pid, "name": "Office move", "status": "planned"}]
    assert (body["expenses"], body["receipts"], body["tasks"], body["milestones"], body["trips"]) == (1, 1, 1, 1, 1)
    assert Project.query.count() == 1  # nothing changed


def test_delete_removes_the_project_and_everything_in_it(client, app):
    h, org_id = make_org(client)
    pid = full_project(client, h, org_id)
    keep = create_project(client, h, org_id, name="Keep me").get_json()["project"]["id"]
    stored = Attachment.query.one().stored_name
    path = os.path.join(app.config["UPLOAD_DIR"], stored)
    assert os.path.exists(path)
    # Stock issued to the project, and a notification pointing at it.
    item = add_stock_item(client, h, org_id).get_json()["item"]
    assert move(client, h, item["id"], "issue", "5", project_id=pid).status_code == 201
    owner = User.query.filter_by(email="owner@example.com").one()
    db.session.add(Notification(user_id=owner.id, organization_id=org_id, kind="x", title="t", link=f"/app/projects/{pid}"))
    db.session.commit()

    r = client.delete(f"/api/projects/{pid}", headers=h)
    assert r.status_code == 200 and r.get_json() == {"deleted": 1}

    assert db.session.get(Project, pid) is None and db.session.get(Project, keep) is not None
    for model in (Expense, Attachment, Task, Milestone, Trip, TripItem):
        assert model.query.count() == 0, model.__name__
    assert not os.path.exists(path)
    assert Notification.query.filter(Notification.link.like(f"/app/projects/{pid}%")).count() == 0
    # Stock history stays, detached, and says where the stock went.
    issue = InventoryMovement.query.filter_by(kind="issue").one()
    assert issue.project_id is None and issue.note == "Issued to deleted project Office move"
    assert listing_quantity(client, h, org_id) == "35.00"
    # The audit trail keeps earlier entries and records the deletion.
    assert AuditLog.query.filter_by(project_id=pid).count() == 0
    assert AuditLog.query.filter_by(action="project.created").count() == 2
    gone = AuditLog.query.filter_by(action="project.deleted").one()
    assert gone.meta["projects"] == [{"id": pid, "name": "Office move"}] and gone.meta["expenses"] == 1
    assert client.get(f"/api/projects/{pid}", headers=h).status_code == 404


def listing_quantity(client, h, org_id):
    return client.get(f"/api/organizations/{org_id}/inventory", headers=h).get_json()["items"][0]["quantity_on_hand"]


def test_delete_several_including_archived(client):
    h, org_id = make_org(client)
    a = full_project(client, h, org_id, name="A")
    b = create_project(client, h, org_id, name="B").get_json()["project"]["id"]
    c = create_project(client, h, org_id, name="C").get_json()["project"]["id"]
    client.post(f"/api/projects/{b}/archive", headers=h)
    r = delete_many(client, h, org_id, [a, b])
    assert r.status_code == 200 and r.get_json() == {"deleted": 2}
    assert [p.id for p in Project.query.all()] == [c]
    summary = client.get(f"/api/organizations/{org_id}/dashboard", headers=h).get_json()["summary"]
    assert summary["project_count"] == 1


def test_all_or_nothing_and_no_reaching_other_organizations(client):
    h, org_id = make_org(client)
    mine = create_project(client, h, org_id, name="Mine").get_json()["project"]["id"]
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    theirs = create_project(client, other_h, other_org, name="Theirs").get_json()["project"]["id"]
    assert delete_many(client, h, org_id, [mine, theirs]).status_code == 404
    assert Project.query.count() == 2
    assert client.delete(f"/api/projects/{theirs}", headers=h).status_code == 404
    assert preview(client, h, org_id, [theirs]).status_code == 404


def test_only_owners_can_delete(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    pm = add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    for who in (pm, c):
        assert client.delete(f"/api/projects/{pid}", headers=who).status_code == 403
        assert delete_many(client, who, org_id, [pid]).status_code == 403
        assert preview(client, who, org_id, [pid]).status_code == 403
    assert Project.query.count() == 1


def test_validation(client):
    h, org_id = make_org(client)
    for ids in ([], None, ["1"], [True]):
        assert delete_many(client, h, org_id, ids).status_code == 400, ids
