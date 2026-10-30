from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.services import metrics as m

TODAY = date(2026, 10, 28)


def exp(amount, d=date(2026, 10, 1), status="valid"):
    return NS(amount=Decimal(amount), expense_date=d, status=status)


def task(status, due=None):
    return NS(status=status, due_date=due)


def test_total_excludes_voided_and_refunded():
    es = [exp("100.10"), exp("50", status="voided"), exp("20", status="refunded"), exp("0.20")]
    assert m.total_actual_expenses(es) == Decimal("100.30")


def test_total_date_range_inclusive():
    es = [exp("10", date(2026, 10, 1)), exp("20", date(2026, 10, 15)), exp("30", date(2026, 11, 1))]
    assert m.total_actual_expenses(es, date(2026, 10, 1), date(2026, 10, 15)) == Decimal("30.00")


def test_budget_metrics_over_budget():
    r = m.calculate_budget_metrics("1000", [exp("1250")])
    assert r.remaining == Decimal("-250.00")
    assert r.variance == Decimal("250.00")
    assert r.consumed_pct == Decimal("125.00")


def test_zero_budget_gives_na():
    assert m.budget_consumed_pct("0", "50") is None


def test_empty_project():
    r = m.calculate_budget_metrics("500", [])
    assert r.actual == Decimal("0.00") and r.consumed_pct == Decimal("0.00")


def test_rounding_half_up():
    assert m.budget_consumed_pct("3", "1") == Decimal("33.33")
    assert m.budget_consumed_pct("8", "1") == Decimal("12.50")
    assert m.q(Decimal("0.005")) == Decimal("0.01")


def test_task_completion_ignores_cancelled():
    ts = [task("done"), task("todo"), task("cancelled"), task("in_progress")]
    assert m.task_completion_pct(ts) == Decimal("33.33")
    assert m.task_completion_pct([task("cancelled")]) is None
    assert m.task_completion_pct([]) is None


def test_overdue_boundaries():
    assert not m.is_overdue(task("todo", TODAY), TODAY)  # due today is not overdue
    assert m.is_overdue(task("todo", date(2026, 10, 27)), TODAY)
    assert not m.is_overdue(task("done", date(2026, 1, 1)), TODAY)
    assert not m.is_overdue(task("cancelled", date(2026, 1, 1)), TODAY)
    assert not m.is_overdue(task("todo", None), TODAY)
    assert m.is_overdue(task("blocked", date(2026, 10, 1)), TODAY)


def test_spend_rate():
    es = [exp("70", date(2026, 10, 25)), exp("70", date(2026, 10, 1))]
    assert m.spend_rate_per_day(es, 7, TODAY) == Decimal("10.00")
    with pytest.raises(ValueError):
        m.spend_rate_per_day(es, 0, TODAY)


def cat_exp(amount, category, d=date(2026, 10, 1), status="valid"):
    return NS(amount=Decimal(amount), expense_date=d, status=status, category=category)


def test_breakdown_by_category_largest_first_and_valid_only():
    es = [
        cat_exp("100", "Design"),
        cat_exp("300", "Travel"),
        cat_exp("50.25", "Design"),
        cat_exp("999", "Travel", status="voided"),
    ]
    rows = m.expense_breakdown(es, "category")
    assert rows == [
        {"key": "Travel", "total": Decimal("300.00"), "count": 1},
        {"key": "Design", "total": Decimal("150.25"), "count": 2},
    ]


def test_breakdown_by_month_with_range():
    es = [
        cat_exp("10", "A", date(2026, 9, 30)),
        cat_exp("20", "A", date(2026, 10, 1)),
        cat_exp("30", "B", date(2026, 11, 2)),
    ]
    rows = m.expense_breakdown(es, "month", date(2026, 10, 1), date(2026, 12, 31))
    assert [(r["key"], r["total"]) for r in rows] == [("2026-10", Decimal("20.00")), ("2026-11", Decimal("30.00"))]


def test_breakdown_rejects_unknown_grouping():
    with pytest.raises(ValueError):
        m.expense_breakdown([], "week")


def test_days_until_budget_exhausted():
    assert m.days_until_budget_exhausted("1000", "30") == 33
    assert m.days_until_budget_exhausted("0", "30") is None
    assert m.days_until_budget_exhausted("-5", "30") is None
    assert m.days_until_budget_exhausted("1000", "0") is None
