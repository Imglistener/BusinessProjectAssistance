"""Changes the assistant drafts (propose_actions): each confirmed line is sent to the app's own API as is, so these
tests send the drafted requests through the test client, exactly as the browser does after "Confirm"."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Expense, Milestone, Project, Role, Task, TaskStatus, Trip, User
from app.services import action_plans, ai_tools

from .test_ai import ask, fake, say  # noqa: F401  (fixture)
from .test_ai import call as tool_call
from .test_projects import add_member, create_project, make_org


def ctx(email: str, org_id: int):
    user = User.query.filter_by(email=email).one()
    return ai_tools.ToolContext(user_id=user.id, organization_id=org_id, today=date(2026, 11, 11))


def setup(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, name="Office move", budget="60000.00").get_json()["project"]["id"]
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    c_user = User.query.filter_by(email="c@example.com").one()
    c_user.first_name, c_user.last_name = "Salma", "Bennani"  # the helper names everyone Alex Doe
    db.session.commit()
    c_id = c_user.id
    task = client.post(f"/api/projects/{pid}/tasks", json={"title": "Book movers", "assignee_id": c_id}, headers=h).get_json()["task"]
    other = client.post(f"/api/projects/{pid}/tasks", json={"title": "Order desks"}, headers=h).get_json()["task"]
    ms = client.post(f"/api/projects/{pid}/milestones", json={"title": "Keys handed over", "due_date": "2026-11-20"},
                     headers=h).get_json()["milestone"]
    exp = client.post(f"/api/projects/{pid}/expenses", json={"category": "Travel", "amount": "300.00",
                      "expense_date": "2026-11-02"}, headers=h).get_json()["expense"]
    trip = client.post(f"/api/projects/{pid}/trips", json={"title": "Furniture pickup", "destination": "Tangier",
                       "start_date": "2026-11-15", "end_date": "2026-11-15"}, headers=h).get_json()["trip"]
    return dict(h=h, org=org_id, pid=pid, contributor=contributor, task=task, other=other, ms=ms, exp=exp, trip=trip)


def draft(email, org_id, actions):
    return ai_tools.propose_actions(ctx(email, org_id), {"actions": actions})["proposal"]


def confirm(client, headers, line):
    r = line["request"]
    return client.open(f"/api{r['path']}", method=r["method"], json=r["body"], headers=headers)


def test_every_action_kind_drafts_a_request_the_api_accepts(client, monkeypatch):
    from app.services import fuel_sync
    s = setup(client)
    monkeypatch.setattr(fuel_sync, "fetch", lambda force=False: fuel_sync.Snapshot(
        [fuel_sync.CityPrices("", None, None)], __import__("datetime").datetime.now(), date(2026, 11, 10)))
    actions = [
        {"kind": "update_task", "task_id": s["task"]["id"], "status": "done"},
        {"kind": "create_task", "project": "office move", "title": "Label boxes", "due_date": "2026-11-18",
         "priority": "high", "assignee": "Alex Doe", "milestone": "Keys handed over"},
        {"kind": "update_milestone", "milestone_id": s["ms"]["id"], "status": "done", "due_date": "2026-11-21"},
        {"kind": "create_milestone", "project_id": s["pid"], "title": "Team moved in", "due_date": "2026-11-30"},
        {"kind": "add_expense", "project": "Office move", "category": "Movers", "amount": 1500,
         "expense_date": "2026-11-10", "trip_id": s["trip"]["id"]},
        {"kind": "void_expense", "expense_id": s["exp"]["id"]},
        {"kind": "create_trip", "project": "Office move", "title": "Site visit", "destination": "Rabat",
         "start_date": "2026-11-25", "end_date": "2026-11-25"},
        {"kind": "update_trip", "trip_id": s["trip"]["id"], "status": "booked"},
        {"kind": "update_project", "project": "Office move", "budget": 65000, "status": "on_hold"},
        {"kind": "set_fuel_price", "fuel_type": "diesel", "price_per_litre": 16.5, "city": "Casablanca"},
        {"kind": "mark_notifications_read"},
        {"kind": "delete_milestone", "milestone_id": s["ms"]["id"]},
        {"kind": "archive_project", "project": "Office move"},
    ]
    d = draft("owner@example.com", s["org"], actions)
    assert [l["error"] for l in d["lines"]] == [None] * len(actions), d["lines"]
    assert all(l["allowed"] for l in d["lines"])
    for line in d["lines"]:
        r = confirm(client, s["h"], line)
        assert r.status_code in (200, 201, 204), (line["kind"], r.get_json())

    assert db.session.get(Task, s["task"]["id"]).status == TaskStatus.DONE
    new_task = Task.query.filter_by(title="Label boxes").one()
    assert new_task.priority.value == "high" and new_task.due_date == date(2026, 11, 18)
    assert db.session.get(Expense, s["exp"]["id"]).status.value == "voided"
    assert db.session.get(Trip, s["trip"]["id"]).status.value == "booked"
    assert db.session.get(Project, s["pid"]).status.value == "archived"
    assert db.session.get(Milestone, s["ms"]["id"]) is None


def test_changes_list_before_and_after(client):
    s = setup(client)
    d = draft("owner@example.com", s["org"], [{"kind": "update_task", "task_id": s["task"]["id"], "status": "done",
                                                "priority": "high"}])
    line = d["lines"][0]
    assert line["target"] == "Book movers" and line["project_name"] == "Office move"
    assert line["changes"] == [{"field": "status", "before": "todo", "after": "done"},
                               {"field": "priority", "before": "medium", "after": "high"}]
    assert line["request"] == {"method": "PATCH", "path": f"/tasks/{s['task']['id']}",
                               "body": {"status": "done", "priority": "high"}}


def test_restore_then_change_an_archived_project(client):
    s = setup(client)
    client.post(f"/api/projects/{s['pid']}/archive", headers=s["h"])
    d = draft("owner@example.com", s["org"], [
        {"kind": "update_task", "task_id": s["task"]["id"], "status": "done"},
        {"kind": "restore_project", "project": "Office move"},
        {"kind": "archive_project", "project": "Office move"},
    ])
    assert d["lines"][0]["error"] == action_plans.ARCHIVED
    assert d["lines"][1]["error"] is None and d["lines"][1]["request"]["body"] == {"status": "active"}
    assert d["lines"][2]["error"] == action_plans.ALREADY_ARCHIVED


@pytest.mark.parametrize(
    "action, error",
    [
        ({"kind": "launch_rocket"}, "Unknown action: launch_rocket."),
        ({"kind": "update_task", "task_id": 99999, "status": "done"}, "Task not found."),
        ({"kind": "update_task", "task_id": "TASK", "status": "done"}, "Task not found."),
        ({"kind": "create_task", "project": "Moon base", "title": "x"}, "No project called Moon base."),
        ({"kind": "create_task", "project": "Office move"}, "Missing title."),
        ({"kind": "create_task", "project": "Office move", "title": "x", "assignee": "Nobody"}, "No member called Nobody."),
        ({"kind": "create_task", "project": "Office move", "title": "x", "due_date": "next week"},
         "Not a valid date: next week. Use YYYY-MM-DD."),
        ({"kind": "add_expense", "project": "Office move", "category": "x", "amount": -5, "expense_date": "2026-11-01"},
         "The amount must be a positive number."),
        ({"kind": "update_project", "project": "Office move", "status": "exploded"}, "Not a valid status: exploded."),
        ({"kind": "update_project", "project": "Office move"}, "Nothing to change."),
        ({"kind": "restore_project", "project": "Office move"}, "This project isn't archived."),
    ],
)
def test_problems_are_reported_per_line(client, action, error):
    s = setup(client)
    line = draft("owner@example.com", s["org"], [action])["lines"][0]
    assert line["error"] == error and line["request"] is None and not line["allowed"]


def test_records_of_another_organization_are_not_found(client):
    s = setup(client)
    other_h, other_org = make_org(client, email="rival@example.com", name="Rival")
    other_pid = create_project(client, other_h, other_org, name="Secret").get_json()["project"]["id"]
    secret = client.post(f"/api/projects/{other_pid}/tasks", json={"title": "Secret"}, headers=other_h).get_json()["task"]
    lines = draft("owner@example.com", s["org"], [
        {"kind": "update_task", "task_id": secret["id"], "status": "done"},
        {"kind": "archive_project", "project_id": other_pid},
        {"kind": "archive_project", "project": "Secret"},
    ])["lines"]
    assert [l["error"] for l in lines] == ["Task not found.", "Missing project.", "No project called Secret."]


def test_contributor_permissions_match_the_api(client):
    s = setup(client)
    lines = draft("c@example.com", s["org"], [
        {"kind": "update_task", "task_id": s["task"]["id"], "status": "done"},  # assigned to them: allowed
        {"kind": "update_task", "task_id": s["task"]["id"], "title": "Renamed"},  # only status: not allowed
        {"kind": "update_task", "task_id": s["other"]["id"], "status": "done"},  # not theirs
        {"kind": "create_task", "project": "Office move", "title": "Mine"},
        {"kind": "void_expense", "expense_id": s["exp"]["id"]},  # added by the owner
        {"kind": "archive_project", "project": "Office move"},
        {"kind": "refresh_fuel_prices"},
        {"kind": "mark_notifications_read"},
    ])["lines"]
    assert [l["allowed"] for l in lines] == [True, False, False, True, False, False, False, True]
    # And the API agrees with the lines the card blocks and allows.
    assert confirm(client, s["contributor"], lines[0]).status_code == 200
    assert confirm(client, s["contributor"], lines[2]).status_code == 403
    assert confirm(client, s["contributor"], lines[5]).status_code == 403


def test_lookup_tools_give_the_ids_actions_need(client):
    s = setup(client)
    c = ctx("owner@example.com", s["org"])
    tasks = ai_tools.find_tasks(c, {"project_id": s["pid"], "query": "movers"})["tasks"]
    assert tasks == [{"task_id": s["task"]["id"], "title": "Book movers", "status": "todo", "priority": "medium",
                      "due_date": None, "overdue": False, "assignee": "Salma Bennani", "milestone": None}]
    assert ai_tools.find_expenses(c, {"project_id": s["pid"]})["expenses"][0]["expense_id"] == s["exp"]["id"]
    assert {m["name"] for m in ai_tools.list_members(c, {})["members"]} == {"Alex Doe", "Salma Bennani"}
    summary = ai_tools.get_project_summary(c, {"project_id": s["pid"]})
    assert summary["milestones"][0]["milestone_id"] == s["ms"]["id"]


def test_chat_returns_action_drafts_with_translated_problems(client, fake):  # noqa: F811
    s = setup(client)
    fake(tool_call("propose_actions", actions=[{"kind": "update_task", "task_id": s["task"]["id"], "status": "done"},
                                               {"kind": "create_task", "project": "Moon base", "title": "x"}]),
         say("Draft ready."))
    r = ask(client, {**s["h"], "Accept-Language": "fr"}, s["org"], message="Marque la tâche comme faite")
    body = r.get_json()
    lines = body["action_proposals"][0]["lines"]
    assert lines[0]["request"]["path"] == f"/tasks/{s['task']['id']}"
    assert lines[1]["error"] == "Aucun projet nommé Moon base."
    assert db.session.get(Task, s["task"]["id"]).status == TaskStatus.TODO  # nothing saved by the assistant
