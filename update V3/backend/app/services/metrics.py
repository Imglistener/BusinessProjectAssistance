"""Deterministic business metrics (spec Section 7). Pure functions, Decimal arithmetic.

Conventions (also in docs/open-items.md):
- variance = actual - budget (positive means over budget)
- percentages return None (shown as "N/A") when the denominator is zero
- rounding: ROUND_HALF_UP to 2 decimals
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

TWOPLACES = Decimal("0.01")
VALID_EXPENSE_STATUS = "valid"
DONE = "done"
CANCELLED = "cancelled"


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _status(value) -> str:
    return getattr(value, "value", value)


def total_actual_expenses(expenses: Iterable, start: Optional[date] = None, end: Optional[date] = None) -> Decimal:
    """Sum of valid expenses; each item needs .amount, .status, .expense_date."""
    total = Decimal("0")
    for e in expenses:
        if _status(e.status) != VALID_EXPENSE_STATUS:
            continue
        if start and e.expense_date < start:
            continue
        if end and e.expense_date > end:
            continue
        total += _d(e.amount)
    return q(total)


def remaining_budget(budget, actual) -> Decimal:
    return q(_d(budget) - _d(actual))


def budget_variance(budget, actual) -> Decimal:
    return q(_d(actual) - _d(budget))


def budget_consumed_pct(budget, actual) -> Optional[Decimal]:
    b = _d(budget)
    if b == 0:
        return None
    return q(_d(actual) / b * 100)


def task_completion_pct(tasks: Iterable) -> Optional[Decimal]:
    """Completed / non-cancelled tasks * 100. None when no eligible tasks."""
    eligible = [t for t in tasks if _status(t.status) != CANCELLED]
    if not eligible:
        return None
    done = sum(1 for t in eligible if _status(t.status) == DONE)
    return q(Decimal(done) / Decimal(len(eligible)) * 100)


def is_overdue(task, today: date) -> bool:
    if _status(task.status) in (DONE, CANCELLED):
        return False
    return task.due_date is not None and task.due_date < today


def overdue_tasks(tasks: Iterable, today: date) -> list:
    return [t for t in tasks if is_overdue(t, today)]


def spend_rate_per_day(expenses: Iterable, period_days: int, today: date) -> Optional[Decimal]:
    """Eligible expenses in the last `period_days` (inclusive of today) / period_days. Indicative only."""
    if period_days <= 0:
        raise ValueError("period_days must be positive")
    from datetime import timedelta

    start = today - timedelta(days=period_days - 1)
    return q(total_actual_expenses(expenses, start, today) / Decimal(period_days))


@dataclass
class BudgetMetrics:
    budget: Decimal
    actual: Decimal
    remaining: Decimal
    variance: Decimal
    consumed_pct: Optional[Decimal]


def calculate_budget_metrics(budget, expenses: Iterable) -> BudgetMetrics:
    actual = total_actual_expenses(expenses)
    return BudgetMetrics(
        budget=q(_d(budget)),
        actual=actual,
        remaining=remaining_budget(budget, actual),
        variance=budget_variance(budget, actual),
        consumed_pct=budget_consumed_pct(budget, actual),
    )
