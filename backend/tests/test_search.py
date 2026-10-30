from datetime import date, timedelta
from decimal import Decimal

from app.models import ExpenseStatus, TaskStatus

from .test_expenses import post_expense
from .test_projects import add_expense, add_task, create_project, make_org


def names(client, h, org_id, query=""):
    r = client.get(f"/api/organizations/{org_id}/projects{query}", headers=h)
    assert r.status_code == 200, r.get_json()
    return [p["name"] for p in r.get_json()["projects"]]


def setup_projects(client):
    h, org_id = make_org(client)
    ids = {}
    for name, desc, budget, end in [
        ("Website redesign", "New marketing site", "1000", "2026-12-01"),
        ("Office move", "Relocate to Casablanca", "500", None),
        ("App launch", "100% mobile_first rollout", "2000", "2026-11-15"),
    ]:
        body = {"name": name, "description": desc, "budget": budget}
        if end:
            body["end_date"] = end
        ids[name] = create_project(client, h, org_id, **body).get_json()["project"]["id"]
    return h, org_id, ids


def test_search_matches_name_and_description_case_insensitively(client):
    h, org_id, _ = setup_projects(client)
    assert names(client, h, org_id, "?q=WEBSITE") == ["Website redesign"]
    assert names(client, h, org_id, "?q=casablanca") == ["Office move"]
    assert names(client, h, org_id, "?q=nothing-like-this") == []


def test_search_treats_wildcards_as_text(client):
    h, org_id, _ = setup_projects(client)
    assert names(client, h, org_id, "?q=%25") == ["App launch"]  # literal "%"
    assert names(client, h, org_id, "?q=_") == ["App launch"]  # literal "_"


def test_sorting(client):
    h, org_id, _ = setup_projects(client)
    assert names(client, h, org_id, "?sort=name") == ["App launch", "Office move", "Website redesign"]
    assert names(client, h, org_id, "?sort=end_date") == ["App launch", "Website redesign", "Office move"]
    assert names(client, h, org_id) == ["App launch", "Office move", "Website redesign"]  # newest first
    assert client.get(f"/api/organizations/{org_id}/projects?sort=budget", headers=h).status_code == 400


def test_over_budget_and_overdue_filters(client):
    h, org_id, ids = setup_projects(client)
    add_expense(ids["Office move"], Decimal("600.00"))
    add_task(ids["App launch"], TaskStatus.TODO, due=date.today() - timedelta(days=2))
    assert names(client, h, org_id, "?over_budget=true") == ["Office move"]
    assert names(client, h, org_id, "?has_overdue=true") == ["App launch"]


def test_search_combines_with_status_and_validates_length(client):
    h, org_id, ids = setup_projects(client)
    client.post(f"/api/projects/{ids['Office move']}/archive", headers=h)
    assert names(client, h, org_id, "?q=office") == []
    assert names(client, h, org_id, "?q=office&status=archived") == ["Office move"]
    assert client.get(f"/api/organizations/{org_id}/projects?q={'x' * 101}", headers=h).status_code == 400


# ---------- expenses ----------


def test_expense_filters_report_matching_amount_and_categories(client):
    h, org_id, ids = setup_projects(client)
    pid = ids["Website redesign"]
    post_expense(client, h, pid, category="Design", amount="100", expense_date="2026-10-01")
    post_expense(client, h, pid, category="Travel", amount="250.50", expense_date="2026-10-10")
    post_expense(client, h, pid, category="Design", amount="40", expense_date="2026-10-20")
    add_expense(pid, Decimal("999"), status=ExpenseStatus.VOIDED, day=date(2026, 10, 15))

    r = client.get(f"/api/projects/{pid}/expenses?category=Design", headers=h).get_json()
    # Three Design rows (one voided); only the two valid ones count toward the amount.
    assert r["total"] == 3 and r["matching_amount"] == "140.00" and r["currency"] == "MAD"
    assert r["categories"] == ["Design", "Travel"]

    r = client.get(f"/api/projects/{pid}/expenses?from=2026-10-05&to=2026-10-31", headers=h).get_json()
    # The voided one is listed (no status filter) but not counted in the amount.
    assert r["total"] == 3 and r["matching_amount"] == "290.50"

    r = client.get(f"/api/projects/{pid}/expenses?limit=1", headers=h).get_json()
    assert len(r["expenses"]) == 1 and r["matching_amount"] == "390.50"  # covers every page

    bad = client.get(f"/api/projects/{pid}/expenses?from=2026-10-31&to=2026-10-01", headers=h)
    assert bad.status_code == 400
