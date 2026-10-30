import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from app.models import ExpenseStatus, Role, TaskStatus
from app.services import metrics

from .test_expenses import post_expense, setup_project
from .test_projects import add_expense, add_member, create_project, make_org


def report(client, h, pid):
    r = client.get(f"/api/projects/{pid}/report", headers=h)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["report"]


def rows(response):
    text = response.get_data(as_text=True)
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_report_figures_match_project_endpoint(client):
    h, _, pid = setup_project(client, "1000")
    post_expense(client, h, pid, category="Design", amount="600", expense_date="2026-09-10")
    post_expense(client, h, pid, category="Travel", amount="200", expense_date="2026-10-02")
    post_expense(client, h, pid, category="Design", amount="400", expense_date="2026-10-12")
    add_expense(pid, Decimal("999"), status=ExpenseStatus.VOIDED)

    rep = report(client, h, pid)
    project = client.get(f"/api/projects/{pid}", headers=h).get_json()["project"]
    b = rep["budget"]
    assert (b["approved"], b["actual"], b["remaining"], b["variance"]) == (
        project["budget"], project["actual"], project["remaining"], project["variance"]
    ) == ("1000.00", "1200.00", "-200.00", "200.00")
    assert b["over_budget"] is True and (b["valid_expense_count"], b["excluded_expense_count"]) == (3, 1)

    assert rep["spending_by_category"] == [
        {"group": "Design", "total": "1000.00", "expense_count": 2, "share_pct": "83.33"},
        {"group": "Travel", "total": "200.00", "expense_count": 1, "share_pct": "16.67"},
    ]
    assert [(r["group"], r["total"]) for r in rep["spending_by_month"]] == [("2026-09", "600.00"), ("2026-10", "600.00")]
    assert rep["project"]["owner"] == "Alex Doe" and rep["organization"]["name"] == "Acme"


def test_report_tasks_and_milestones(client):
    h, _, pid = setup_project(client)
    today = date.today()
    mid = client.post(f"/api/projects/{pid}/milestones", json={"title": "Beta"}, headers=h).get_json()["milestone"]["id"]
    for title, due, status in [
        ("Late", today - timedelta(days=2), "todo"),
        ("Soon", today + timedelta(days=3), "in_progress"),
        ("Far", today + timedelta(days=40), "todo"),
        ("Done", today - timedelta(days=9), "done"),
    ]:
        client.post(
            f"/api/projects/{pid}/tasks",
            json={"title": title, "due_date": due.isoformat(), "status": status, "milestone_id": mid},
            headers=h,
        )
    t = report(client, h, pid)["tasks"]
    assert [x["title"] for x in t["overdue"]] == ["Late"] and t["overdue"][0]["days_overdue"] == 2
    assert [x["title"] for x in t["upcoming"]] == ["Soon"]
    assert t["overdue"][0]["milestone"] == "Beta"
    assert t["completion_pct"] == "25.00" and t["by_status"] == {"todo": 2, "in_progress": 1, "done": 1}
    [m] = report(client, h, pid)["milestones"]
    assert (m["title"], m["task_count"], m["task_completion_pct"]) == ("Beta", 4, "25.00")


def test_empty_project_report(client):
    h, _, pid = setup_project(client, "0")
    rep = report(client, h, pid)
    assert rep["budget"]["consumed_pct"] is None
    assert rep["spending_by_category"] == [] and rep["tasks"]["completion_pct"] is None


def test_expenses_csv(client):
    h, _, pid = setup_project(client)
    post_expense(client, h, pid, category="Design", amount="250.50", expense_date="2026-10-20", description="Logo, v2")
    post_expense(client, h, pid, category="Travel", amount="10", expense_date="2026-10-01", description="=HYPERLINK(\"x\")")
    r = client.get(f"/api/projects/{pid}/expenses.csv", headers=h)
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert 'filename="website-redesign-expenses-' in r.headers["Content-Disposition"]
    data = rows(r)
    assert data[0] == ["date", "category", "amount", "currency", "status", "description", "recorded_by"]
    assert data[1][:5] == ["2026-10-01", "Travel", "10.00", "MAD", "valid"]
    assert data[1][5] == "'=HYPERLINK(\"x\")"  # neutralised formula
    assert data[2][5] == "Logo, v2"  # commas quoted correctly


def test_tasks_csv(client):
    h, _, pid = setup_project(client)
    client.post(f"/api/projects/{pid}/tasks", json={"title": "@sum", "due_date": "2020-01-01"}, headers=h)
    data = rows(client.get(f"/api/projects/{pid}/tasks.csv", headers=h))
    assert data[0][0] == "title" and data[1][0] == "'@sum" and data[1][-1] == "yes"


def test_reports_are_permission_checked(client):
    h, org_id, pid = setup_project(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    assert client.get(f"/api/projects/{pid}/report", headers=viewer).status_code == 200
    for path in ("report", "expenses.csv", "tasks.csv"):
        assert client.get(f"/api/projects/{pid}/{path}", headers=outsider).status_code == 404
        assert client.get(f"/api/projects/{pid}/{path}").status_code == 401


def test_filename_falls_back_for_non_latin_names(client):
    h, org_id, _ = setup_project(client)
    pid = create_project(client, h, org_id, name="مشروع").get_json()["project"]["id"]
    r = client.get(f"/api/projects/{pid}/tasks.csv", headers=h)
    assert f'filename="project-{pid}-tasks-' in r.headers["Content-Disposition"]


def test_share_pct():
    assert metrics.share_pct("1", "3") == Decimal("33.33")
    assert metrics.share_pct("5", "0") is None
