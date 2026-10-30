"""Deterministic business metrics (spec Section 7). Pure functions, Decimal arithmetic.

Conventions (also in docs/open-items.md):
- variance = actual - budget (positive means over budget)
- percentages return None (shown as "N/A") when the denominator is zero
- rounding: ROUND_HALF_UP to 2 decimals
"""
from __future__ import annotations

import math
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


def sum_money(values: Iterable) -> Decimal:
    """Sum of amounts, rounded like every other figure."""
    total = Decimal("0")
    for v in values:
        total += _d(v)
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


def share_pct(part, total) -> Optional[Decimal]:
    """part / total * 100; None when the total is zero."""
    t = _d(total)
    if t == 0:
        return None
    return q(_d(part) / t * 100)


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


MILESTONE_DONE = "done"


def is_milestone_overdue(milestone, today: date) -> bool:
    """Open milestone whose due date is before today (same rule as tasks)."""
    return milestone.status != MILESTONE_DONE and milestone.due_date is not None and milestone.due_date < today


def spend_rate_per_day(expenses: Iterable, period_days: int, today: date) -> Optional[Decimal]:
    """Eligible expenses in the last `period_days` (inclusive of today) / period_days. Indicative only."""
    if period_days <= 0:
        raise ValueError("period_days must be positive")
    from datetime import timedelta

    start = today - timedelta(days=period_days - 1)
    return q(total_actual_expenses(expenses, start, today) / Decimal(period_days))


def days_until_budget_exhausted(remaining, per_day) -> Optional[int]:
    """Whole days the remaining budget lasts at `per_day`. None when nothing remains or nothing is spent."""
    r, rate = _d(remaining), _d(per_day)
    if r <= 0 or rate <= 0:
        return None
    return int(r // rate)


def expense_breakdown(
    expenses: Iterable, group_by: str, start: Optional[date] = None, end: Optional[date] = None
) -> list[dict]:
    """Valid expenses grouped by "category" (largest first) or "month" (YYYY-MM, oldest first)."""
    if group_by not in ("category", "month"):
        raise ValueError("group_by must be 'category' or 'month'")
    groups: dict[str, list] = {}
    for e in expenses:
        if _status(e.status) != VALID_EXPENSE_STATUS:
            continue
        if (start and e.expense_date < start) or (end and e.expense_date > end):
            continue
        key = e.category if group_by == "category" else e.expense_date.strftime("%Y-%m")
        groups.setdefault(key, []).append(e)
    rows = [{"key": k, "total": total_actual_expenses(v), "count": len(v)} for k, v in groups.items()]
    if group_by == "category":
        rows.sort(key=lambda r: (-r["total"], r["key"]))
    else:
        rows.sort(key=lambda r: r["key"])
    return rows


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


# ---------- inventory ----------


def stock_value(quantity, unit_cost) -> Optional[Decimal]:
    """quantity x unit cost; None when the item has no cost."""
    if unit_cost is None:
        return None
    return q(_d(quantity) * _d(unit_cost))


def is_low_stock(quantity, reorder_level) -> bool:
    """At or below the reorder level. Items without a level are never low."""
    return reorder_level is not None and _d(quantity) <= _d(reorder_level)


# ---------- travel ----------

EARTH_RADIUS_KM = Decimal("6371.0")


def straight_line_km(lat1, lng1, lat2, lng2) -> Decimal:
    """Great-circle (haversine) distance in km, to 0.1 km."""
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp, dl = p2 - p1, math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * float(EARTH_RADIUS_KM) * math.asin(math.sqrt(a))
    return Decimal(str(km)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class FuelEstimate:
    distance_km: Decimal  # total driven by each vehicle (both ways if round trip)
    litres_low: Decimal
    litres_expected: Decimal
    litres_high: Decimal
    cost_low: Decimal
    cost_expected: Decimal
    cost_high: Decimal


def fuel_estimate(
    one_way_km,
    l_per_100_low,
    l_per_100_high,
    price_per_litre,
    *,
    round_trip: bool,
    vehicles: int,
    distance_variance_pct=Decimal("10"),
    price_variance_pct=Decimal("3"),
) -> FuelEstimate:
    """Fuel needed and its cost as a range.

    low  = planned distance x lowest consumption x price minus price variance
    high = planned distance plus distance variance (detours, traffic) x highest consumption x price plus price variance
    expected = middle of each range. Litres and costs cover all vehicles.
    """
    if vehicles < 1:
        raise ValueError("vehicles must be at least 1")
    km = _d(one_way_km) * (2 if round_trip else 1)
    dv, pv = _d(distance_variance_pct) / 100, _d(price_variance_pct) / 100
    lo_c, hi_c = _d(l_per_100_low), _d(l_per_100_high)
    price = _d(price_per_litre)
    n = Decimal(vehicles)

    litres_low = km * lo_c / 100 * n
    litres_high = km * (1 + dv) * hi_c / 100 * n
    litres_mid = km * (1 + dv / 2) * (lo_c + hi_c) / 2 / 100 * n
    return FuelEstimate(
        distance_km=km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        litres_low=q(litres_low),
        litres_expected=q(litres_mid),
        litres_high=q(litres_high),
        cost_low=q(litres_low * price * (1 - pv)),
        cost_expected=q(litres_mid * price),
        cost_high=q(litres_high * price * (1 + pv)),
    )


# ---------- general calculations for the assistant ----------


def vat(amount, rate_pct, mode: str) -> dict:
    """mode "add": amount is net, VAT is added. mode "extract": amount is gross (VAT included)."""
    a, r = _d(amount), _d(rate_pct) / 100
    if mode == "add":
        net, tax = a, a * r
        return {"net": q(net), "vat": q(tax), "gross": q(net + tax)}
    if mode == "extract":
        net = a / (1 + r)
        return {"net": q(net), "vat": q(a - net), "gross": q(a)}
    raise ValueError("mode must be add or extract")
