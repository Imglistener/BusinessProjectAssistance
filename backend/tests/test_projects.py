from datetime import date, timedelta

from app.extensions import db
from app.models import (
    AuditLog,
    Expense,
    ExpenseStatus,
    OrganizationMember,
    Project,
    Role,
    Task,
    TaskStatus,
    User,
)

from .helpers import auth_headers
from .test_organizations import create_org


def make_org(client, email="owner@example.com", name="Acme"):
    headers = auth_headers(client, email=email)
    org_id = create_org(client, headers, name).get_json()["organization"]["id"]
    return headers, org_id


def add_member(client, org_id, email, role):
    """Create a user and attach them to the organization with the given role."""
    headers = auth_headers(client, email=email)
    user = User.query.filter_by(email=email).one()
    db.session.add(OrganizationMember(organization_id=org_id, user_id=user.id, role=role))
    db.session.commit()
    return headers


def create_project(client, headers, org_id, **overrides):
    body = {"name": "Website redesign", "budget": "12500.00"}
    body.update(overrides)
    return client.post(f"/api/organizations/{org_id}/projects", json=body, headers=headers)


def add_expense(project_id, amount, status=ExpenseStatus.VALID, day=None):
    user = User.query.first()
    db.session.add(
        Expense(
            project_id=project_id,
            created_by=user.id,
            category="Design",
            amount=amount,
            expense_date=day or date.today(),
            status=status,
        )
    )
    db.session.commit()


def add_task(project_id, status, due=None):
    db.session.add(Task(project_id=project_id, title="t", status=status, due_date=due))
    db.session.commit()


# ---------- create ----------


def test_owner_creates_project_with_org_currency_default(client):
    h, org_id = make_org(client)
    r = create_project(client, h, org_id, description="New site", start_date="2026-11-01", end_date="2026-12-15")
    assert r.status_code == 201
    p = r.get_json()["project"]
    assert p["budget"] == "12500.00" and p["actual"] == "0.00" and p["remaining"] == "12500.00"
    assert p["currency"] == "MAD" and p["status"] == "planned"
    assert p["consumed_pct"] == "0.00" and p["over_budget"] is False


def test_create_writes_audit_entry(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    entry = AuditLog.query.filter_by(action="project.created", entity_id=pid).one()
    assert entry.organization_id == org_id and entry.meta["budget"] == "12500.00"


def test_budget_is_optional_and_zero_budget_has_no_percentage(client):
    h, org_id = make_org(client)
    p = create_project(client, h, org_id, budget=None).get_json()["project"]
    assert p["budget"] == "0.00" and p["consumed_pct"] is None


def test_create_validation(client):
    h, org_id = make_org(client)
    bad = [
        {"name": ""},
        {"budget": "-5"},
        {"budget": "abc"},
        {"budget": "10.999"},
        {"budget": True},
        {"budget": "NaN"},
        {"budget": "1e30"},
        {"currency": "MADD"},
        {"start_date": "01/11/2026"},
        {"start_date": "2026-12-01", "end_date": "2026-11-01"},
        {"status": "finished"},
    ]
    for override in bad:
        r = create_project(client, h, org_id, **override)
        assert r.status_code == 400, override
        assert r.get_json()["error"]["code"] == "validation_error"
    assert Project.query.count() == 0


def test_numeric_budget_accepted(client):
    h, org_id = make_org(client)
    assert create_project(client, h, org_id, budget=1500).get_json()["project"]["budget"] == "1500.00"


def test_requires_auth(client):
    _, org_id = make_org(client)
    assert client.post(f"/api/organizations/{org_id}/projects", json={"name": "x"}).status_code == 401


# ---------- permissions ----------


def test_roles_for_writing(client):
    h, org_id = make_org(client)
    pm = add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)

    assert create_project(client, pm, org_id).status_code == 201
    for headers in (contributor, viewer):
        r = create_project(client, headers, org_id)
        assert r.status_code == 403
        assert r.get_json()["error"]["code"] == "forbidden"

    pid = Project.query.first().id
    for headers in (contributor, viewer):
        assert client.patch(f"/api/projects/{pid}", json={"name": "x"}, headers=headers).status_code == 403
        assert client.post(f"/api/projects/{pid}/archive", headers=headers).status_code == 403


def test_viewer_can_read(client):
    h, org_id = make_org(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    assert client.get(f"/api/projects/{pid}", headers=viewer).status_code == 200
    assert len(client.get(f"/api/organizations/{org_id}/projects", headers=viewer).get_json()["projects"]) == 1
    assert client.get(f"/api/organizations/{org_id}/dashboard", headers=viewer).status_code == 200


def test_outsider_gets_404_everywhere(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    outsider = auth_headers(client, email="out@example.com")

    assert client.get(f"/api/projects/{pid}", headers=outsider).status_code == 404
    assert client.patch(f"/api/projects/{pid}", json={"name": "x"}, headers=outsider).status_code == 404
    assert client.post(f"/api/projects/{pid}/archive", headers=outsider).status_code == 404
    assert client.get(f"/api/organizations/{org_id}/projects", headers=outsider).status_code == 404
    assert client.get(f"/api/organizations/{org_id}/dashboard", headers=outsider).status_code == 404
    assert create_project(client, outsider, org_id).status_code == 404
    # Same answer as a project that doesn't exist.
    assert client.get("/api/projects/99999", headers=outsider).status_code == 404


def test_projects_are_scoped_to_their_organization(client):
    a, org_a = make_org(client, "a@example.com", "A Corp")
    b, org_b = make_org(client, "b@example.com", "B Corp")
    create_project(client, a, org_a, name="A project")
    create_project(client, b, org_b, name="B project")
    names = [p["name"] for p in client.get(f"/api/organizations/{org_a}/projects", headers=a).get_json()["projects"]]
    assert names == ["A project"]


# ---------- metrics ----------


def test_metrics_exclude_voided_and_refunded_expenses(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, budget="1000").get_json()["project"]["id"]
    add_expense(pid, "400.00")
    add_expense(pid, "100.50")
    add_expense(pid, "999.00", status=ExpenseStatus.VOIDED)
    add_expense(pid, "50.00", status=ExpenseStatus.REFUNDED)

    p = client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]
    assert p["actual"] == "500.50"
    assert p["remaining"] == "499.50"
    assert p["variance"] == "-499.50"
    assert p["consumed_pct"] == "50.05"
    assert p["over_budget"] is False


def test_over_budget_project(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, budget="100").get_json()["project"]["id"]
    add_expense(pid, "130.00")
    p = client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]
    assert p["variance"] == "30.00" and p["remaining"] == "-30.00"
    assert p["consumed_pct"] == "130.00" and p["over_budget"] is True


def test_task_metrics(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    yesterday = date.today() - timedelta(days=2)  # two days back avoids timezone edge cases
    add_task(pid, TaskStatus.DONE)
    add_task(pid, TaskStatus.TODO, due=yesterday)
    add_task(pid, TaskStatus.CANCELLED, due=yesterday)
    add_task(pid, TaskStatus.IN_PROGRESS)
    p = client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]
    assert p["task_completion_pct"] == "33.33"  # 1 of 3 non-cancelled
    assert p["overdue_task_count"] == 1


def test_no_tasks_gives_null_completion(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    assert client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]["task_completion_pct"] is None


# ---------- list / dashboard ----------


def test_list_hides_archived_unless_asked(client):
    h, org_id = make_org(client)
    keep = create_project(client, h, org_id, name="Keep").get_json()["project"]["id"]
    gone = create_project(client, h, org_id, name="Gone").get_json()["project"]["id"]
    client.post(f"/api/projects/{gone}/archive", headers=h)

    url = f"/api/organizations/{org_id}/projects"
    assert [p["id"] for p in client.get(url, headers=h).get_json()["projects"]] == [keep]
    both = client.get(url + "?include_archived=true", headers=h).get_json()["projects"]
    assert {p["id"] for p in both} == {keep, gone}
    only = client.get(url + "?status=archived", headers=h).get_json()["projects"]
    assert [p["id"] for p in only] == [gone]
    assert client.get(url + "?status=nope", headers=h).status_code == 400


def test_dashboard_totals_group_by_currency_and_skip_archived(client):
    h, org_id = make_org(client)
    p1 = create_project(client, h, org_id, budget="1000").get_json()["project"]["id"]
    p2 = create_project(client, h, org_id, budget="500.50").get_json()["project"]["id"]
    p3 = create_project(client, h, org_id, budget="200", currency="eur").get_json()["project"]["id"]
    archived = create_project(client, h, org_id, budget="9999").get_json()["project"]["id"]
    add_expense(p1, "1100.00")  # over budget
    add_expense(p2, "100.25")
    add_expense(p3, "50.00")
    add_expense(archived, "5.00")
    client.post(f"/api/projects/{archived}/archive", headers=h)

    s = client.get(f"/api/organizations/{org_id}/dashboard", headers=h).get_json()["summary"]
    assert s["project_count"] == 3
    assert s["over_budget_project_count"] == 1
    assert s["totals"] == [
        {"currency": "EUR", "budget": "200.00", "actual": "50.00", "remaining": "150.00"},
        {"currency": "MAD", "budget": "1500.50", "actual": "1200.25", "remaining": "300.25"},
    ]


def test_dashboard_for_org_without_projects(client):
    h, org_id = make_org(client)
    s = client.get(f"/api/organizations/{org_id}/dashboard", headers=h).get_json()["summary"]
    assert s == {"totals": [], "project_count": 0, "over_budget_project_count": 0, "overdue_task_count": 0}


# ---------- update / archive ----------


def test_update_changes_fields_and_audits_budget(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, budget="1000").get_json()["project"]["id"]
    r = client.patch(
        f"/api/projects/{pid}",
        json={"name": "Renamed", "budget": "1500.00", "status": "active"},
        headers=h,
    )
    assert r.status_code == 200
    p = r.get_json()["project"]
    assert p["name"] == "Renamed" and p["budget"] == "1500.00" and p["status"] == "active"

    entry = AuditLog.query.filter_by(action="project.updated", entity_id=pid).one()
    assert entry.meta["budget"] == ["1000.00", "1500.00"]
    assert entry.meta["status"] == ["planned", "active"]
    assert entry.meta["name"] == "changed"  # the new name itself is not logged


def test_update_with_no_real_change_writes_no_audit_entry(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, budget="1000").get_json()["project"]["id"]
    assert client.patch(f"/api/projects/{pid}", json={"budget": "1000"}, headers=h).status_code == 200
    assert AuditLog.query.filter_by(action="project.updated").count() == 0


def test_update_validates_dates_against_existing_values(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, start_date="2026-11-01", end_date="2026-12-01").get_json()["project"]["id"]
    r = client.patch(f"/api/projects/{pid}", json={"end_date": "2026-10-01"}, headers=h)
    assert r.status_code == 400 and r.get_json()["error"]["details"]["field"] == "end_date"
    assert client.patch(f"/api/projects/{pid}", json={"budget": None}, headers=h).status_code == 400


def test_currency_locked_once_expenses_exist(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    assert client.patch(f"/api/projects/{pid}", json={"currency": "USD"}, headers=h).status_code == 200
    add_expense(pid, "10.00")
    r = client.patch(f"/api/projects/{pid}", json={"currency": "EUR"}, headers=h)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "currency_locked"
    # Re-sending the current currency is not a change.
    assert client.patch(f"/api/projects/{pid}", json={"currency": "usd"}, headers=h).status_code == 200


def test_archive_is_idempotent_and_audited_once(client):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    for _ in range(2):
        r = client.post(f"/api/projects/{pid}/archive", headers=h)
        assert r.status_code == 200 and r.get_json()["project"]["status"] == "archived"
    assert AuditLog.query.filter_by(action="project.archived", entity_id=pid).count() == 1
