from app.cli import DEMO_EMAIL, demo_data
from app.models import Organization, Project, User


def test_demo_data_creates_a_usable_organization(app, client):
    runner = app.test_cli_runner()
    result = runner.invoke(demo_data)
    assert result.exit_code == 0, result.output
    assert "Demo data created" in result.output
    assert Organization.query.count() == 1 and Project.query.count() == 5

    token = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": "demo-password"}).get_json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    org_id = Organization.query.one().id
    projects = {p["name"]: p for p in client.get(f"/api/organizations/{org_id}/projects", headers=h).get_json()["projects"]}
    assert projects["Website redesign"]["over_budget"] is True
    assert projects["Office move to Casablanca"]["overdue_task_count"] == 2
    assert projects["Mobile app MVP"]["over_budget"] is False and "2025 rebrand" not in projects
    deadlines = client.get(f"/api/organizations/{org_id}/deadlines", headers=h).get_json()
    assert any(i["kind"] == "milestone" and i["overdue"] for i in deadlines["items"])

    # Running it again changes nothing.
    again = runner.invoke(demo_data)
    assert "already exists" in again.output and User.query.count() == 2
