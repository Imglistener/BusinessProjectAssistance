import json
from datetime import date

import pytest

from app.models import AuditLog, Milestone, Project, Role, Task
from app.services import ai_chat, ai_tools
from app.services.ai_provider import ProviderResponse, ToolCall
from app.services.plans import PlanError, validate_plan

from .test_ai import FakeProvider, ask
from .test_projects import add_member, make_org

TODAY = date(2026, 10, 31)

PLAN = {
    "name": "Ifrane team retreat",
    "description": "3-day retreat for 25 people, customer Atlas Bank.",
    "budget": 80000,
    "start_date": "2027-03-10",
    "end_date": "2027-03-12",
    "milestones": [{"title": "Venue booked", "due_date": "2027-01-15"}, {"title": "Retreat held", "due_date": "2027-03-12"}],
    "tasks": [
        {"title": "Shortlist hotels", "priority": "high", "due_date": "2026-12-01", "milestone": "Venue booked"},
        {"title": "Book coach", "milestone": "Unknown milestone"},
        {"title": "Plan activities", "priority": "low"},
    ],
}


def test_validate_plan_normalises():
    p = validate_plan(PLAN, default_currency="MAD", today=TODAY)
    assert (p["budget"], p["currency"], p["start_date"]) == ("80000.00", "MAD", "2027-03-10")
    assert [t["milestone"] for t in p["tasks"]] == ["Venue booked", None, None]  # unknown milestone dropped
    assert [t["priority"] for t in p["tasks"]] == ["high", "medium", "low"]


@pytest.mark.parametrize(
    "change,field",
    [
        ({"name": ""}, "name"),
        ({"budget": -5}, "budget"),
        ({"budget": "lots"}, "budget"),
        ({"end_date": "2027-03-01"}, "end_date"),
        ({"start_date": "10/03/2027"}, "start_date"),
        ({"start_date": "2040-01-01"}, "start_date"),
        ({"currency": "MADS"}, "currency"),
        ({"tasks": [{"title": "x", "priority": "urgent"}]}, "tasks"),
        ({"tasks": [{"title": "t"}] * 51}, "tasks"),
        ({"milestones": [{"title": "A"}, {"title": "a"}]}, "milestones"),
    ],
)
def test_validate_plan_rejects(change, field):
    with pytest.raises(PlanError) as e:
        validate_plan({**PLAN, **change}, default_currency="MAD", today=TODAY)
    assert e.value.field == field


def test_tool_returns_draft_and_creates_nothing(client):
    h, org_id = make_org(client)
    ctx = ai_tools.ToolContext(user_id=1, organization_id=org_id, today=TODAY)
    result, _, ok = ai_tools.run_tool(ctx, "propose_project", json.dumps(PLAN))
    assert ok and result["status"] == "draft_not_saved" and result["proposal"]["name"] == "Ifrane team retreat"
    assert Project.query.count() == 0
    bad, _, ok = ai_tools.run_tool(ctx, "propose_project", json.dumps({**PLAN, "budget": -1}))
    assert not ok and "positive" in bad["error"]


def test_chat_returns_the_proposal(client, monkeypatch):
    h, org_id = make_org(client)
    call = ProviderResponse(content=None, tool_calls=[ToolCall("p1", "propose_project", json.dumps(PLAN))])
    provider = FakeProvider(call, ProviderResponse(content="Here's a draft plan."))
    monkeypatch.setattr(ai_chat, "get_provider", lambda: provider)
    body = ask(client, h, org_id, message="Atlas Bank wants a 3-day retreat in Ifrane in March, 80k MAD.").get_json()
    assert [p["name"] for p in body["proposals"]] == ["Ifrane team retreat"]
    assert body["tool_trace"][0]["tool"] == "propose_project" and Project.query.count() == 0


def test_create_from_plan(client):
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/projects/from-plan", json=PLAN, headers=h)
    assert r.status_code == 201, r.get_json()
    p = r.get_json()["project"]
    assert (p["name"], p["budget"], p["status"], p["start_date"]) == ("Ifrane team retreat", "80000.00", "planned", "2027-03-10")
    assert [m.title for m in Milestone.query.order_by(Milestone.id)] == ["Venue booked", "Retreat held"]
    venue = Milestone.query.filter_by(title="Venue booked").one()
    assert Task.query.filter_by(title="Shortlist hotels").one().milestone_id == venue.id
    assert Task.query.count() == 3
    entry = AuditLog.query.filter_by(action="project.created").one()
    assert entry.meta["source"] == "assistant_plan" and entry.meta["tasks"] == 3


def test_create_from_plan_permissions_and_validation(client):
    h, org_id = make_org(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    url = f"/api/organizations/{org_id}/projects/from-plan"
    assert client.post(url, json=PLAN, headers=contributor).status_code == 403
    assert client.post(url, json=PLAN, headers=outsider).status_code == 404
    r = client.post(url, json={**PLAN, "end_date": "2027-01-01"}, headers=h)
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "end_date"}
    assert Project.query.filter_by(organization_id=org_id).count() == 0
