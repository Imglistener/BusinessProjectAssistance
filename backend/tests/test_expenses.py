from app.extensions import db
from app.models import AuditLog, Expense, ExpenseStatus, Role

from .helpers import auth_headers
from .test_projects import add_member, create_project, make_org


def setup_project(client, budget="1000"):
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id, budget=budget).get_json()["project"]["id"]
    return h, org_id, pid


def post_expense(client, headers, pid, **overrides):
    body = {"category": "Design", "amount": "250.50", "expense_date": "2026-10-20"}
    body.update(overrides)
    return client.post(f"/api/projects/{pid}/expenses", json=body, headers=headers)


# ---------- create ----------


def test_create_expense_updates_project_totals(client):
    h, _, pid = setup_project(client, "1000")
    r = post_expense(client, h, pid, description="Logo work")
    assert r.status_code == 201
    body = r.get_json()
    assert body["expense"]["amount"] == "250.50" and body["expense"]["status"] == "valid"
    assert body["expense"]["currency"] == "MAD"  # taken from the project
    assert body["project"]["actual"] == "250.50"
    assert body["project"]["remaining"] == "749.50"

    post_expense(client, h, pid, amount="800")
    p = client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]
    assert p["actual"] == "1050.50" and p["over_budget"] is True and p["variance"] == "50.50"


def test_currency_in_request_is_ignored(client):
    h, _, pid = setup_project(client)
    r = post_expense(client, h, pid, currency="USD")
    assert r.get_json()["expense"]["currency"] == "MAD"


def test_create_expense_audited_with_project_id(client):
    h, org_id, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    entry = AuditLog.query.filter_by(action="expense.created", entity_id=eid).one()
    assert entry.organization_id == org_id
    assert entry.meta == {"project_id": pid, "amount": "250.50", "currency": "MAD", "category": "Design"}


def test_expense_validation(client):
    h, _, pid = setup_project(client)
    bad = [
        {"amount": "0"},
        {"amount": "-10"},
        {"amount": "abc"},
        {"amount": "1.234"},
        {"amount": None},
        {"category": ""},
        {"category": "x" * 81},
        {"expense_date": ""},
        {"expense_date": "20/10/2026"},
    ]
    for override in bad:
        r = post_expense(client, h, pid, **override)
        assert r.status_code == 400, override
        assert r.get_json()["error"]["code"] == "validation_error"
    assert Expense.query.count() == 0


def test_cannot_add_expense_to_archived_project(client):
    h, _, pid = setup_project(client)
    client.post(f"/api/projects/{pid}/archive", headers=h)
    r = post_expense(client, h, pid)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "project_archived"


# ---------- permissions ----------


def test_roles_and_isolation(client):
    h, org_id, pid = setup_project(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider = auth_headers(client, email="out@example.com")

    assert post_expense(client, contributor, pid).status_code == 201
    assert post_expense(client, viewer, pid).status_code == 403
    assert post_expense(client, outsider, pid).status_code == 404

    url = f"/api/projects/{pid}/expenses"
    assert client.get(url, headers=viewer).status_code == 200
    assert client.get(url, headers=outsider).status_code == 404
    eid = Expense.query.first().id
    assert client.patch(f"/api/expenses/{eid}", json={"amount": "1"}, headers=outsider).status_code == 404
    assert client.post(f"/api/expenses/{eid}/void", headers=outsider).status_code == 404
    assert client.patch("/api/expenses/99999", json={}, headers=outsider).status_code == 404


def test_contributor_can_change_only_own_expenses(client):
    h, org_id, pid = setup_project(client)
    c1 = add_member(client, org_id, "c1@example.com", Role.CONTRIBUTOR)
    c2 = add_member(client, org_id, "c2@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    mine = post_expense(client, c1, pid).get_json()["expense"]["id"]
    owners = post_expense(client, h, pid).get_json()["expense"]["id"]

    assert client.patch(f"/api/expenses/{mine}", json={"amount": "10"}, headers=c1).status_code == 200
    assert client.patch(f"/api/expenses/{mine}", json={"amount": "10"}, headers=c2).status_code == 403
    assert client.patch(f"/api/expenses/{owners}", json={"amount": "10"}, headers=c1).status_code == 403
    assert client.post(f"/api/expenses/{owners}/void", headers=c1).status_code == 403
    assert client.post(f"/api/expenses/{mine}/void", headers=viewer).status_code == 403
    # Owners can change anyone's.
    assert client.patch(f"/api/expenses/{mine}", json={"amount": "11"}, headers=h).status_code == 200


# ---------- list ----------


def test_list_orders_filters_and_paginates(client):
    h, _, pid = setup_project(client)
    post_expense(client, h, pid, category="Design", amount="10", expense_date="2026-10-01")
    post_expense(client, h, pid, category="Software", amount="20", expense_date="2026-10-15")
    last = post_expense(client, h, pid, category="Design", amount="30", expense_date="2026-10-28")
    client.post(f"/api/expenses/{last.get_json()['expense']['id']}/void", headers=h)

    url = f"/api/projects/{pid}/expenses"
    body = client.get(url, headers=h).get_json()
    assert [e["amount"] for e in body["expenses"]] == ["30.00", "20.00", "10.00"]  # newest first
    assert body["total"] == 3

    only_valid = client.get(url + "?status=valid", headers=h).get_json()
    assert [e["amount"] for e in only_valid["expenses"]] == ["20.00", "10.00"]
    design = client.get(url + "?category=Design&status=valid", headers=h).get_json()
    assert [e["amount"] for e in design["expenses"]] == ["10.00"]
    ranged = client.get(url + "?from=2026-10-10&to=2026-10-20", headers=h).get_json()
    assert [e["amount"] for e in ranged["expenses"]] == ["20.00"]

    page = client.get(url + "?limit=2&offset=2", headers=h).get_json()
    assert page["total"] == 3 and [e["amount"] for e in page["expenses"]] == ["10.00"]
    assert client.get(url + "?status=nope", headers=h).status_code == 400
    assert client.get(url + "?from=bad", headers=h).status_code == 400
    assert client.get(url + "?limit=abc", headers=h).status_code == 400


# ---------- update / void ----------


def test_update_expense_changes_fields_and_audits(client):
    h, _, pid = setup_project(client, "1000")
    eid = post_expense(client, h, pid, amount="100").get_json()["expense"]["id"]
    r = client.patch(
        f"/api/expenses/{eid}",
        json={"amount": "150.25", "category": "Software", "description": "Licences", "expense_date": "2026-10-21"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["expense"]["amount"] == "150.25" and body["expense"]["category"] == "Software"
    assert body["project"]["actual"] == "150.25"

    meta = AuditLog.query.filter_by(action="expense.updated", entity_id=eid).one().meta
    assert meta["amount"] == ["100.00", "150.25"]
    assert meta["expense_date"] == ["2026-10-20", "2026-10-21"]
    assert meta["description"] == "changed"  # the text itself is not logged


def test_update_without_change_writes_no_audit(client):
    h, _, pid = setup_project(client)
    eid = post_expense(client, h, pid, amount="100").get_json()["expense"]["id"]
    assert client.patch(f"/api/expenses/{eid}", json={"amount": "100"}, headers=h).status_code == 200
    assert AuditLog.query.filter_by(action="expense.updated").count() == 0


def test_update_validation(client):
    h, _, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    for body in ({"amount": "0"}, {"amount": None}, {"category": ""}, {"expense_date": None}):
        assert client.patch(f"/api/expenses/{eid}", json=body, headers=h).status_code == 400, body


def test_void_removes_expense_from_totals_but_keeps_record(client):
    h, _, pid = setup_project(client, "1000")
    keep = post_expense(client, h, pid, amount="100").get_json()["expense"]["id"]
    gone = post_expense(client, h, pid, amount="400").get_json()["expense"]["id"]

    r = client.post(f"/api/expenses/{gone}/void", headers=h)
    assert r.status_code == 200
    assert r.get_json()["expense"]["status"] == "voided"
    assert r.get_json()["project"]["actual"] == "100.00"
    assert db.session.get(Expense, gone).status == ExpenseStatus.VOIDED  # still stored
    assert db.session.get(Expense, keep).status == ExpenseStatus.VALID


def test_void_is_idempotent_and_audited_once(client):
    h, _, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    for _ in range(2):
        assert client.post(f"/api/expenses/{eid}/void", headers=h).status_code == 200
    assert AuditLog.query.filter_by(action="expense.voided", entity_id=eid).count() == 1


def test_voided_expense_cannot_be_edited(client):
    h, _, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    client.post(f"/api/expenses/{eid}/void", headers=h)
    r = client.patch(f"/api/expenses/{eid}", json={"amount": "5"}, headers=h)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "expense_not_editable"


def test_archived_project_blocks_edits_and_voids(client):
    h, _, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert client.patch(f"/api/expenses/{eid}", json={"amount": "5"}, headers=h).status_code == 409
    assert client.post(f"/api/expenses/{eid}/void", headers=h).status_code == 409
    # Reading still works, and restoring the project unlocks it again.
    assert client.get(f"/api/projects/{pid}/expenses", headers=h).status_code == 200
    client.patch(f"/api/projects/{pid}", json={"status": "active"}, headers=h)
    assert client.patch(f"/api/expenses/{eid}", json={"amount": "5"}, headers=h).status_code == 200
